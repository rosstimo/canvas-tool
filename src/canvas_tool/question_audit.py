from __future__ import annotations

import html
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class QuestionAuditResult:
    markdown_path: Path
    json_path: Path
    finding_count: int
    warning_count: int
    review_count: int


def _load(snapshot: Path, name: str, default: Any) -> Any:
    try:
        return json.loads((snapshot / name).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _groups(snapshot: Path, stem: str) -> list[dict[str, Any]]:
    value = _load(snapshot, f"{stem}.json", [])
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _md(value: Any) -> str:
    return str(value if value is not None else "").replace("\n", " ").replace("\r", " ").replace("|", "\\|")


def _plain(value: Any) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    text = html.unescape(text)
    return " ".join(text.split())


def _fingerprint(value: Any) -> str:
    text = _plain(value).casefold()
    text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def _finding(severity: str, area: str, message: str, item: str = "") -> dict[str, str]:
    return {"severity": severity, "area": area, "item": item, "message": message}


def _answer_text(answer: dict[str, Any]) -> str:
    for key in ("text", "html", "answer_text", "answer_html"):
        if answer.get(key):
            return _plain(answer[key])
    return ""


def audit_questions(snapshot: Path) -> QuestionAuditResult:
    snapshot = snapshot.resolve()
    manifest = _load(snapshot, "manifest.json", {})
    classic_quiz_groups = _groups(snapshot, "classic-quiz-questions")
    bank_groups = _groups(snapshot, "question-bank-questions")
    new_groups = _groups(snapshot, "new-quiz-items")

    findings: list[dict[str, str]] = []
    classic_rows: list[dict[str, Any]] = []
    new_rows: list[dict[str, Any]] = []
    question_types: Counter[str] = Counter()
    new_types: Counter[str] = Counter()
    entry_types: Counter[str] = Counter()
    fingerprints: defaultdict[str, list[str]] = defaultdict(list)

    def add_classic(group: dict[str, Any], question: dict[str, Any], source_type: str) -> None:
        source = str(group.get("title") or group.get("source_id") or source_type)
        name = str(question.get("question_name") or question.get("id") or "unnamed question")
        qtype = str(question.get("question_type") or "Unknown")
        body = question.get("question_text")
        answers = [item for item in (question.get("answers") or []) if isinstance(item, dict)]
        question_types[qtype] += 1

        fp = _fingerprint(body)
        if fp:
            fingerprints[fp].append(f"{source_type}: {source} → {name}")
        else:
            findings.append(_finding("review", "question body", "Question body is empty.", f"{source} → {name}"))

        answer_texts = Counter(_fingerprint(_answer_text(item)) for item in answers if _answer_text(item))
        duplicate_answers = [text for text, count in answer_texts.items() if text and count > 1]
        if duplicate_answers:
            findings.append(_finding("review", "answer choices", "Contains duplicate answer text.", f"{source} → {name}"))

        positive_answers = sum(1 for item in answers if float(item.get("weight") or 0) > 0)
        if qtype in {"multiple_choice_question", "true_false_question"}:
            if not answers:
                findings.append(_finding("review", "answer choices", "Single-answer question has no captured answers.", f"{source} → {name}"))
            elif positive_answers != 1:
                findings.append(_finding("review", "answer key", f"Single-answer question has {positive_answers} positively weighted answers; expected one.", f"{source} → {name}"))
        elif qtype == "multiple_answers_question" and answers and positive_answers == 0:
            findings.append(_finding("review", "answer key", "Multiple-answer question has no positively weighted answers.", f"{source} → {name}"))

        classic_rows.append({
            "source_type": source_type,
            "source": source,
            "id": question.get("id"),
            "position": question.get("position"),
            "name": name,
            "question_type": qtype,
            "points": question.get("points_possible"),
            "answer_count": len(answers),
            "positive_answer_count": positive_answers,
            "bank_id": question.get("assessment_question_bank_id"),
            "body_preview": _plain(body)[:160],
        })

    for group in classic_quiz_groups:
        positions: Counter[Any] = Counter()
        for question in group.get("items") or []:
            if not isinstance(question, dict):
                continue
            add_classic(group, question, "Classic Quiz")
            if question.get("position") is not None:
                positions[question.get("position")] += 1
        for position, count in positions.items():
            if count > 1:
                findings.append(_finding("review", "question position", f"Position {position} appears {count} times in this quiz.", str(group.get("title") or group.get("source_id") or "Classic Quiz")))

    for group in bank_groups:
        for question in group.get("items") or []:
            if isinstance(question, dict):
                add_classic(group, question, "Classic Question Bank")

    for group in new_groups:
        source = str(group.get("title") or group.get("source_id") or "New Quiz")
        items = [item for item in (group.get("items") or []) if isinstance(item, dict)]
        item_ids = {str(item.get("id")) for item in items if item.get("id") is not None}
        positions: Counter[Any] = Counter()

        for item in items:
            entry_type = str(item.get("entry_type") or "Unknown")
            entry_types[entry_type] += 1
            entry = item.get("entry") if isinstance(item.get("entry"), dict) else {}
            interaction_type = str(entry.get("interaction_type_slug") or "")
            title = str(entry.get("title") or item.get("id") or entry_type)
            body = entry.get("item_body")

            if interaction_type:
                new_types[interaction_type] += 1

            if entry_type == "Item":
                if not interaction_type:
                    findings.append(_finding("review", "New Quiz question type", "Direct question item has no interaction_type_slug.", f"{source} → {title}"))
                fp = _fingerprint(body)
                if fp:
                    fingerprints[fp].append(f"New Quiz: {source} → {title}")
                else:
                    findings.append(_finding("review", "New Quiz question body", "Direct question item has an empty question body.", f"{source} → {title}"))
                points = item.get("points_possible")
                if points is not None and float(points) <= 0:
                    findings.append(_finding("review", "New Quiz points", f"Direct question item has {_md(points)} points possible.", f"{source} → {title}"))
            elif entry_type in {"Bank", "BankEntry"} and entry.get("archived") is True:
                findings.append(_finding("review", "New Quiz item bank", "Bank-backed item references an archived bank.", f"{source} → {title}"))

            stimulus_raw = item.get("stimulus_quiz_entry_id")
            stimulus_id = str(stimulus_raw).strip() if stimulus_raw is not None else ""
            if stimulus_id and stimulus_id not in item_ids:
                findings.append(_finding("warning", "New Quiz stimulus", f"References stimulus quiz entry ID {stimulus_id}, which is not present in the captured quiz items.", f"{source} → {title}"))

            if item.get("position") is not None:
                positions[item.get("position")] += 1

            new_rows.append({
                "source": source,
                "id": item.get("id"),
                "position": item.get("position"),
                "entry_type": entry_type,
                "title": title,
                "interaction_type": interaction_type or "—",
                "points": item.get("points_possible"),
                "status": item.get("status"),
                "stimulus_quiz_entry_id": stimulus_id or None,
                "body_preview": _plain(body)[:160],
            })

        for position, count in positions.items():
            if count > 1:
                findings.append(_finding("review", "New Quiz item position", f"Position {position} appears {count} times in this quiz.", source))

    duplicate_question_groups = [members for members in fingerprints.values() if len(members) > 1]
    for members in duplicate_question_groups:
        findings.append(_finding(
            "review",
            "duplicate question text",
            f"The same normalized question body appears {len(members)} times: {'; '.join(members)}.",
        ))

    summary = {
        "classic_quiz_questions": sum(1 for item in classic_rows if item["source_type"] == "Classic Quiz"),
        "classic_question_bank_questions": sum(1 for item in classic_rows if item["source_type"] == "Classic Question Bank"),
        "new_quiz_items": len(new_rows),
        "new_direct_questions": sum(1 for item in new_rows if item["entry_type"] == "Item"),
        "new_bank_backed_items": sum(1 for item in new_rows if item["entry_type"] in {"Bank", "BankEntry"}),
        "new_stimulus_items": sum(1 for item in new_rows if item["entry_type"] == "Stimulus"),
        "duplicate_question_text_groups": len(duplicate_question_groups),
    }

    payload = {
        "schema_version": 1,
        "course_id": manifest.get("course_id"),
        "course_name": manifest.get("course_name"),
        "read_only": True,
        "summary": summary,
        "findings": findings,
        "classic_question_types": dict(sorted(question_types.items())),
        "new_quiz_interaction_types": dict(sorted(new_types.items())),
        "new_quiz_entry_types": dict(sorted(entry_types.items())),
        "classic_questions": classic_rows,
        "new_quiz_items": new_rows,
    }
    json_path = snapshot / "question-audit.json"
    markdown_path = snapshot / "question-audit.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "# Quiz question audit",
        "",
        f"- Course: **{manifest.get('course_name', 'unnamed course')}**",
        f"- Course code: `{manifest.get('course_code', '')}`",
        f"- Canvas course ID: `{manifest.get('course_id', '')}`",
        "- Mode: **read-only**. No Canvas content is changed.",
        "",
        "Question-level inventory across Classic Quiz questions, Classic Question Banks, and captured New Quiz items. Type-specific checks are intentionally limited to structures whose scoring meaning is clear from the API.",
        "",
        "## Summary",
        "",
    ]
    for key, value in summary.items():
        lines.append(f"- {key.replace('_', ' ').title()}: **{value}**")

    lines.extend(["", "## Attention / review", ""])
    actionable = [item for item in findings if item["severity"] in {"warning", "review"}]
    if actionable:
        for item in actionable:
            label = f" **{_md(item['item'])}**:" if item.get("item") else ""
            lines.append(f"- **{item['severity'].upper()} · {_md(item['area'])}**{label} {_md(item['message'])}")
    else:
        lines.append("None found.")

    lines.extend(["", "## Classic question types", "", "| Question type | Count |", "|---|---:|"])
    for key, value in sorted(question_types.items()):
        lines.append(f"| {_md(key)} | {value} |")

    lines.extend(["", "## New Quiz interaction types", "", "| Interaction type | Count |", "|---|---:|"])
    for key, value in sorted(new_types.items()):
        lines.append(f"| {_md(key)} | {value} |")

    lines.extend([
        "",
        "## Classic questions and bank questions",
        "",
        "| Source type | Source | # | Question | Type | Points | Answers | Positive | Bank | Preview |",
        "|---|---|---:|---|---|---:|---:|---:|---|---|",
    ])
    for item in classic_rows:
        lines.append(
            f"| {_md(item['source_type'])} | {_md(item['source'])} | {_md(item['position'] or '')} | {_md(item['name'])} | {_md(item['question_type'])} | "
            f"{_md(item['points'] if item['points'] is not None else '—')} | {item['answer_count']} | {item['positive_answer_count']} | "
            f"{_md(item['bank_id'] if item['bank_id'] is not None else '—')} | {_md(item['body_preview'] or '—')} |"
        )

    lines.extend([
        "",
        "## New Quiz items",
        "",
        "| Quiz | # | Entry | Title | Interaction | Points | Status | Stimulus | Preview |",
        "|---|---:|---|---|---|---:|---|---|---|",
    ])
    for item in new_rows:
        lines.append(
            f"| {_md(item['source'])} | {_md(item['position'] or '')} | {_md(item['entry_type'])} | {_md(item['title'])} | "
            f"{_md(item['interaction_type'])} | {_md(item['points'] if item['points'] is not None else '—')} | {_md(item['status'] or '—')} | "
            f"{_md(item['stimulus_quiz_entry_id'] if item['stimulus_quiz_entry_id'] is not None else '—')} | {_md(item['body_preview'] or '—')} |"
        )
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    counts = Counter(item["severity"] for item in findings)
    return QuestionAuditResult(
        markdown_path=markdown_path,
        json_path=json_path,
        finding_count=len(findings),
        warning_count=counts.get("warning", 0),
        review_count=counts.get("review", 0),
    )
