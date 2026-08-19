from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from urllib.request import Request, urlopen

from .course import assert_same_origin


class CanvasApiError(RuntimeError):
    def __init__(self, method: str, url: str, status: int | None, body: str, message: str | None = None):
        self.method = method
        self.url = url
        self.status = status
        self.body = body
        label = f"HTTP {status}" if status is not None else "network error"
        super().__init__(message or f"Canvas API error: {label} for {method} {url}")

    def pretty_body(self) -> str:
        try:
            return json.dumps(json.loads(self.body), indent=2)
        except (json.JSONDecodeError, TypeError):
            return "\n".join(self.body.splitlines()[:20])


@dataclass
class CanvasClient:
    base_url: str
    api_token: str
    max_retries: int = 4
    per_page: int = 100
    timeout: float = 30.0

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")

    def url(self, target: str) -> str:
        if target.startswith("https://"):
            assert_same_origin(target, self.base_url)
            return target
        if target.startswith("/"):
            return self.base_url + target
        return self.base_url + "/" + target

    def request_json(self, method: str, target: str, body: Any | None = None) -> Any:
        url = self.url(target)
        raw_body, _headers = self._request(method.upper(), url, body=body)
        if not raw_body.strip():
            return None
        try:
            return json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise CanvasApiError(method.upper(), url, 200, raw_body, "Canvas returned invalid JSON") from exc

    def paginate(self, target: str) -> list[Any]:
        url = self._with_per_page(self.url(target))
        results: list[Any] = []
        while url:
            raw_body, headers = self._request("GET", url)
            try:
                page = json.loads(raw_body)
            except json.JSONDecodeError as exc:
                raise CanvasApiError("GET", url, 200, raw_body, "Canvas returned invalid JSON") from exc
            if not isinstance(page, list):
                raise CanvasApiError("GET", url, 200, raw_body, "expected an array from paginated endpoint")
            results.extend(page)
            next_url = self._next_link(headers.get("Link", ""))
            if next_url:
                assert_same_origin(next_url, self.base_url)
            url = next_url
        return results

    def _request(self, method: str, url: str, body: Any | None = None) -> tuple[str, dict[str, str]]:
        data: bytes | None = None
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Accept": "application/json+canvas-string-ids, application/json",
            "User-Agent": "canvas-tool/0.2",
        }
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        delay = 1.0
        for attempt in range(self.max_retries + 1):
            request = Request(url, data=data, headers=headers, method=method)
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    text = response.read().decode("utf-8", errors="replace")
                    return text, dict(response.headers.items())
            except HTTPError as exc:
                text = exc.read().decode("utf-8", errors="replace")
                if exc.code in {429, 500, 502, 503, 504} and attempt < self.max_retries:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise CanvasApiError(method, url, exc.code, text) from exc
            except URLError as exc:
                if attempt < self.max_retries:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise CanvasApiError(method, url, None, str(exc.reason)) from exc
        raise AssertionError("retry loop exhausted unexpectedly")

    def _with_per_page(self, url: str) -> str:
        parts = urlsplit(url)
        query = parse_qsl(parts.query, keep_blank_values=True)
        if not any(key == "per_page" for key, _value in query):
            query.append(("per_page", str(self.per_page)))
        return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query, doseq=True), parts.fragment))

    @staticmethod
    def _next_link(link_header: str) -> str:
        for part in link_header.split(","):
            section = part.strip()
            if 'rel="next"' not in section:
                continue
            start = section.find("<")
            end = section.find(">", start + 1)
            if start >= 0 and end > start:
                return section[start + 1 : end]
        return ""
