from __future__ import annotations

import argparse
import csv
import getpass
import json
import statistics
import os
import time
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


SUPPORTED_EXTENSIONS = {".csv", ".tsv", ".json", ".md", ".txt"}


@dataclass
class FileSummary:
    path: str
    file_type: str
    records: int
    fields: list[str]
    numeric_fields: dict[str, dict[str, float]]
    top_values: dict[str, list[dict[str, Any]]]
    notes: list[str]


@dataclass
class AnalysisIssue:
    issue_id: str
    path: str
    severity: str
    title: str
    evidence: list[str]
    local_recommendation: str
    action_plan: list[str]
    ai_resolution: str | None = None


def read_analysis_goal(args: argparse.Namespace) -> str:
    if args.goal:
        return args.goal.strip()

    if args.prompt_goal:
        print("Analysis goal/context: ", end="", flush=True)
        return input().strip()

    return ""


def find_data_files(input_dir: Path) -> list[Path]:
    if not input_dir.exists():
        return []

    if input_dir.is_file():
        if input_dir.suffix.lower() in SUPPORTED_EXTENSIONS:
            return [input_dir]
        return []

    return sorted(
        path
        for path in input_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )


def parse_number(value: Any) -> float | None:
    if value is None or value == "":
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def numeric_summary(values: list[float]) -> dict[str, float]:
    if not values:
        return {}

    summary = {
        "count": float(len(values)),
        "min": min(values),
        "max": max(values),
        "mean": statistics.fmean(values),
    }

    if len(values) > 1:
        summary["median"] = statistics.median(values)

    return summary


def top_value_summary(values: list[Any], limit: int = 5) -> list[dict[str, Any]]:
    cleaned = [str(value).strip() for value in values if str(value).strip()]
    counts = Counter(cleaned)
    return [{"value": value, "count": count} for value, count in counts.most_common(limit)]


def analyze_records(path: Path, file_type: str, records: list[dict[str, Any]]) -> FileSummary:
    fields = sorted({field for record in records for field in record})
    numeric_fields: dict[str, dict[str, float]] = {}
    top_values: dict[str, list[dict[str, Any]]] = {}

    for field in fields:
        values = [record.get(field) for record in records]
        numbers = [number for value in values if (number := parse_number(value)) is not None]

        if numbers:
            numeric_fields[field] = numeric_summary(numbers)

        top_values[field] = top_value_summary(values)

    return FileSummary(
        path=str(path),
        file_type=file_type,
        records=len(records),
        fields=fields,
        numeric_fields=numeric_fields,
        top_values=top_values,
        notes=[],
    )


def analyze_delimited(path: Path, delimiter: str) -> FileSummary:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file, delimiter=delimiter))

    summary = analyze_records(path, "tsv" if delimiter == "\t" else "csv", rows)

    if not rows:
        summary.notes.append("No data rows found.")

    return summary


def normalize_json_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item if isinstance(item, dict) else {"value": item} for item in payload]

    if isinstance(payload, dict):
        return [payload]

    return [{"value": payload}]


def analyze_json(path: Path) -> FileSummary:
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    return analyze_records(path, "json", normalize_json_records(payload))


def analyze_text(path: Path) -> FileSummary:
    text = path.read_text(encoding="utf-8", errors="replace")
    words = [word.strip(".,;:!?()[]{}\"'").lower() for word in text.split()]
    words = [word for word in words if word]

    records = [
        {
            "line_count": len(text.splitlines()),
            "word_count": len(words),
            "character_count": len(text),
        }
    ]
    summary = analyze_records(path, "text", records)
    summary.top_values["common_words"] = top_value_summary(words, limit=10)
    return summary


def slugify(value: str) -> str:
    cleaned = "".join(character.lower() if character.isalnum() else "_" for character in value)
    return "_".join(part for part in cleaned.split("_") if part)[:80] or "issue"


def detect_issues(summaries: list[FileSummary]) -> list[AnalysisIssue]:
    issues: list[AnalysisIssue] = []
    successful_statuses = {
        "complete",
        "completed",
        "done",
        "closed",
        "resolved",
        "success",
        "succeeded",
        "ok",
        "pass",
        "passed",
        "exitcode_0",
        "0",
        "false",
    }

    if not summaries:
        return [
            AnalysisIssue(
                issue_id="no_supported_data_files",
                path="",
                severity="high",
                title="No supported data files were found",
                evidence=["The input folder did not contain CSV, TSV, JSON, Markdown, or text files."],
                local_recommendation=(
                    "Confirm the input path and place synthesized analysis exports in a supported format."
                ),
                action_plan=[
                    "Verify the input path used for the analyzer run.",
                    "Export the synthesized analysis data as CSV, TSV, JSON, Markdown, or text.",
                    "Rerun the analyzer and confirm the summary report lists at least one file.",
                ],
            )
        ]

    for summary in summaries:
        base_id = slugify(summary.path)

        if summary.records == 0:
            issues.append(
                AnalysisIssue(
                    issue_id=f"{base_id}_empty_file",
                    path=summary.path,
                    severity="high",
                    title="File has no analyzable records",
                    evidence=[f"{summary.path} produced 0 records."],
                    local_recommendation=(
                        "Regenerate the synthesized export or check whether headers/data rows were omitted."
                    ),
                    action_plan=[
                        "Open the source file and confirm it has headers and data rows.",
                        "Regenerate the export from the source application if the file is empty.",
                        "Rerun the analyzer and confirm the record count is greater than zero.",
                    ],
                )
            )

        if summary.records > 0 and not summary.fields:
            issues.append(
                AnalysisIssue(
                    issue_id=f"{base_id}_no_fields",
                    path=summary.path,
                    severity="medium",
                    title="No fields were detected",
                    evidence=[f"{summary.path} has records but no named fields."],
                    local_recommendation=(
                        "Check the export structure and make sure the first row or JSON keys preserve field names."
                    ),
                    action_plan=[
                        "Inspect the source file for missing headers or unnamed JSON keys.",
                        "Regenerate or transform the export so fields have stable names.",
                        "Rerun the analyzer and verify the field list is populated.",
                    ],
                )
            )

        for note in summary.notes:
            issues.append(
                AnalysisIssue(
                    issue_id=f"{base_id}_{slugify(note)}",
                    path=summary.path,
                    severity="medium",
                    title="Analyzer note needs review",
                    evidence=[note],
                    local_recommendation="Review the source file and rerun the analyzer after correcting the data.",
                    action_plan=[
                        "Review the analyzer note and the matching source file.",
                        "Correct the source data or document why the note is expected.",
                        "Rerun the analyzer and compare the new issue report.",
                    ],
                )
            )

        for field, stats in summary.numeric_fields.items():
            count = int(stats.get("count", 0))
            if summary.records and count < summary.records:
                missing_count = summary.records - count
                issues.append(
                    AnalysisIssue(
                        issue_id=f"{base_id}_{slugify(field)}_partial_numeric_values",
                        path=summary.path,
                        severity="low",
                        title=f"`{field}` has non-numeric or missing values",
                        evidence=[
                            f"{count} of {summary.records} records were numeric.",
                            f"{missing_count} record(s) were blank or not parseable as numbers.",
                        ],
                        local_recommendation=(
                            "Normalize this column before analysis or document why mixed values are expected."
                        ),
                        action_plan=[
                            f"Filter records in `{field}` that are blank or not numeric.",
                            "Correct malformed values or split mixed text/numeric meanings into separate fields.",
                            "Rerun the analyzer and confirm the numeric count matches the record count.",
                        ],
                    )
                )

            if stats.get("min", 0) < 0:
                issues.append(
                    AnalysisIssue(
                        issue_id=f"{base_id}_{slugify(field)}_negative_values",
                        path=summary.path,
                        severity="medium",
                        title=f"`{field}` contains negative values",
                        evidence=[f"Minimum value is {stats['min']:.2f}."],
                        local_recommendation=(
                            "Verify whether negative values are valid for this measure or correct the source data."
                        ),
                        action_plan=[
                            f"Filter `{field}` for values below 0 and identify the affected records.",
                            "Compare before/after source measurements for those records.",
                            "Fix collection math, timing drift, or source values if negative recovery is invalid.",
                            "Rerun the operation for affected records and confirm the minimum value is 0 or higher.",
                        ],
                    )
                )

        status_values = summary.top_values.get("status", [])
        incomplete_statuses = {
            item["value"]: item["count"]
            for item in status_values
            if str(item["value"]).strip().lower() not in successful_statuses
        }
        if incomplete_statuses:
            formatted = ", ".join(f"{value} ({count})" for value, count in incomplete_statuses.items())
            issues.append(
                AnalysisIssue(
                    issue_id=f"{base_id}_unresolved_status_values",
                    path=summary.path,
                    severity="medium",
                    title="Unresolved status values were found",
                    evidence=[f"Unresolved statuses: {formatted}."],
                    local_recommendation=(
                        "Prioritize these records for follow-up and capture the blocker, owner, and next action."
                    ),
                    action_plan=[
                        "Filter the dataset to the unresolved status values listed in the evidence.",
                        "Assign each affected record an owner and a next action.",
                        "Resolve or reprocess the blocked records.",
                        "Rerun the analyzer and confirm only successful status values remain.",
                    ],
                )
            )

        for field in summary.fields:
            if "status" not in field.lower() or field.lower() == "status":
                continue

            field_values = summary.top_values.get(field, [])
            failed_values = {
                item["value"]: item["count"]
                for item in field_values
                if str(item["value"]).strip().lower() not in successful_statuses
            }
            if not failed_values:
                continue

            formatted = ", ".join(f"{value} ({count})" for value, count in failed_values.items())
            issues.append(
                AnalysisIssue(
                    issue_id=f"{base_id}_{slugify(field)}_non_success_status_values",
                    path=summary.path,
                    severity="medium",
                    title=f"`{field}` has non-success status values",
                    evidence=[f"Non-success values: {formatted}."],
                    local_recommendation=(
                        "Review the affected records, group them by failure reason, and rerun the operation "
                        "after correcting access, service, or script errors."
                    ),
                    action_plan=[
                        f"Filter `{field}` to the non-success values listed in the evidence.",
                        "Group affected records by status code and failure message if available.",
                        "Resolve the highest-count failure group first.",
                        "Rerun the source operation for affected records.",
                        "Rerun the analyzer and confirm the non-success count is reduced or cleared.",
                    ],
                )
            )

    return issues


def summarize_for_ai(issue: AnalysisIssue, summary: FileSummary | None) -> dict[str, Any] | None:
    if not summary:
        return None

    relevant_fields = {
        field
        for field in summary.fields
        if field.lower() in issue.title.lower() or field.lower() in " ".join(issue.evidence).lower()
    }
    relevant_fields.update(field for field in summary.fields if "status" in field.lower())

    return {
        "path": summary.path,
        "file_type": summary.file_type,
        "records": summary.records,
        "fields": summary.fields,
        "relevant_numeric_fields": {
            field: stats
            for field, stats in summary.numeric_fields.items()
            if field in relevant_fields or field.lower() in issue.title.lower()
        },
        "relevant_top_values": {
            field: values
            for field, values in summary.top_values.items()
            if field in relevant_fields or field.lower() in issue.title.lower()
        },
    }


def build_ai_prompt(issue: AnalysisIssue, summary: FileSummary | None, analysis_goal: str) -> str:
    context = {
        "analysis_goal": analysis_goal,
        "issue": asdict(issue),
        "file_summary": summarize_for_ai(issue, summary),
    }
    return (
        "You are helping analyze an operational report and recommend practical next actions.\n"
        "Frame the answer around the analysis_goal. If the goal is about C drive filling up, "
        "focus on root causes, affected machine triage, cleanup/remediation steps, and prevention.\n"
        "Given this issue context, propose a practical resolution report entry.\n"
        "Use plain ASCII only. Return concise Markdown under 220 words with: likely cause, "
        "prioritized action plan, validation step, owner/team recommendation, and residual risk.\n\n"
        f"{json.dumps(context, indent=2)}"
    )


def clean_ai_text(text: str) -> str:
    replacements = {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2265": ">=",
        "\u2264": "<=",
        "\u2248": "approx.",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text.encode("ascii", errors="ignore").decode("ascii")


def request_groq_resolution(
    issue: AnalysisIssue,
    summary: FileSummary | None,
    model: str,
    api_key: str,
    analysis_goal: str,
) -> str:
    if not api_key:
        return "Groq resolution was skipped because GROQ_API_KEY is not set."

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": build_ai_prompt(issue, summary, analysis_goal),
            }
        ],
        "temperature": 0.2,
        "max_completion_tokens": 650,
    }
    request = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "dataanalysis-issue-resolver/1.0",
        },
        method="POST",
    )

    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = json.loads(response.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            if error.code == 429 and attempt == 0:
                time.sleep(35)
                continue
            return f"Groq request failed with HTTP {error.code}: {detail}"
        except urllib.error.URLError as error:
            return f"Groq request failed: {error.reason}"
    else:
        return "Groq request failed after retrying a rate limit."

    if "output_text" in body:
        return str(body["output_text"]).strip()

    choices = body.get("choices", [])
    if choices:
        message = choices[0].get("message", {})
        content = message.get("content")
        if content:
            return clean_ai_text(str(content).strip())

    text_parts: list[str] = []
    for item in body.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                text_parts.append(str(content["text"]))

    text = "\n".join(text_parts).strip()
    return clean_ai_text(text) if text else "Groq returned no text output."


def resolve_issues_with_groq(
    issues: list[AnalysisIssue],
    summaries: list[FileSummary],
    model: str,
    api_key: str,
    analysis_goal: str,
) -> list[AnalysisIssue]:
    summaries_by_path = {summary.path: summary for summary in summaries}
    for issue in issues:
        issue.ai_resolution = request_groq_resolution(
            issue,
            summaries_by_path.get(issue.path),
            model,
            api_key,
            analysis_goal,
        )
    return issues


def analyze_file(path: Path) -> FileSummary:
    suffix = path.suffix.lower()

    if suffix == ".csv":
        return analyze_delimited(path, ",")

    if suffix == ".tsv":
        return analyze_delimited(path, "\t")

    if suffix == ".json":
        return analyze_json(path)

    return analyze_text(path)


def build_issue_resolution_report(
    issues: list[AnalysisIssue],
    ai_provider: str | None,
    analysis_goal: str,
) -> str:
    lines = [
        "# Issue Resolution Report",
        "",
        f"Issues found: {len(issues)}",
        f"AI-assisted resolutions: {ai_provider if ai_provider else 'disabled'}",
    ]
    if analysis_goal:
        lines.extend(["", f"Analysis goal: {analysis_goal}"])
    lines.append("")

    if not issues:
        lines.extend(["No issues were detected in the analyzed data.", ""])
        return "\n".join(lines)

    for issue in issues:
        lines.extend(
            [
                f"## {issue.title}",
                "",
                f"- ID: `{issue.issue_id}`",
                f"- Severity: {issue.severity}",
                f"- File: {issue.path or 'input folder'}",
                "",
                "### Evidence",
                "",
            ]
        )
        lines.extend(f"- {item}" for item in issue.evidence)
        lines.extend(
            [
                "",
                "### Local Recommendation",
                "",
                issue.local_recommendation,
                "",
                "### Action Plan",
                "",
            ]
        )
        lines.extend(f"{index}. {step}" for index, step in enumerate(issue.action_plan, start=1))
        lines.append("")

        if issue.ai_resolution:
            lines.extend(
                [
                    "### AI-Generated Action Plan",
                    "",
                    issue.ai_resolution,
                    "",
                ]
            )

    return "\n".join(lines)


def build_markdown_report(summaries: list[FileSummary]) -> str:
    lines = [
        "# Analysis Summary",
        "",
        f"Files analyzed: {len(summaries)}",
        "",
    ]

    if not summaries:
        lines.extend(["No supported data files were found.", ""])
        return "\n".join(lines)

    for summary in summaries:
        lines.extend(
            [
                f"## {summary.path}",
                "",
                f"- Type: {summary.file_type}",
                f"- Records: {summary.records}",
                f"- Fields: {', '.join(summary.fields) if summary.fields else 'none'}",
                "",
            ]
        )

        if summary.numeric_fields:
            lines.append("### Numeric Fields")
            lines.append("")
            for field, stats in summary.numeric_fields.items():
                formatted = ", ".join(f"{key}: {value:.2f}" for key, value in stats.items())
                lines.append(f"- `{field}`: {formatted}")
            lines.append("")

        if summary.top_values:
            lines.append("### Top Values")
            lines.append("")
            for field, values in summary.top_values.items():
                if not values:
                    continue
                formatted = ", ".join(f"{item['value']} ({item['count']})" for item in values)
                lines.append(f"- `{field}`: {formatted}")
            lines.append("")

        for note in summary.notes:
            lines.append(f"- Note: {note}")
        if summary.notes:
            lines.append("")

    return "\n".join(lines)


def save_reports(
    summaries: list[FileSummary],
    output_dir: Path,
    issues: list[AnalysisIssue],
    ai_provider: str | None,
    analysis_goal: str,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "files_analyzed": len(summaries),
        "files": [asdict(summary) for summary in summaries],
        "issues_found": len(issues),
        "analysis_goal": analysis_goal,
        "issues": [asdict(issue) for issue in issues],
    }

    (output_dir / "analysis_summary.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )
    (output_dir / "analysis_summary.md").write_text(
        build_markdown_report(summaries),
        encoding="utf-8",
    )
    (output_dir / "issue_resolution_report.json").write_text(
        json.dumps(
            {
                "analysis_goal": analysis_goal,
                "issues": [asdict(issue) for issue in issues],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (output_dir / "issue_resolution_report.md").write_text(
        build_issue_resolution_report(issues, ai_provider, analysis_goal),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze local data files.")
    parser.add_argument("--input", default="data", help="Input folder to scan.")
    parser.add_argument("--output", default="reports", help="Output folder for reports.")
    parser.add_argument(
        "--goal",
        default="",
        help="Analysis goal/context to frame local and AI-generated recommendations.",
    )
    parser.add_argument(
        "--prompt-goal",
        action="store_true",
        help="Ask for the analysis goal before analyzing the data.",
    )
    parser.add_argument(
        "--resolve-with-groq",
        action="store_true",
        help="Ask Groq to draft a resolution for each detected issue.",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
        help="Groq model to use when --resolve-with-groq is enabled.",
    )
    parser.add_argument(
        "--prompt-groq-key",
        action="store_true",
        help="Prompt for the Groq API key without echoing it or saving it to disk.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_dir = Path(args.input)
    output_dir = Path(args.output)
    analysis_goal = read_analysis_goal(args)

    summaries = [analyze_file(path) for path in find_data_files(input_dir)]
    issues = detect_issues(summaries)
    ai_provider = "groq" if args.resolve_with_groq else None

    if args.resolve_with_groq:
        if not args.model:
            raise SystemExit("Set GROQ_MODEL or pass --model when using --resolve-with-groq.")

        api_key = os.getenv("GROQ_API_KEY", "").strip()
        if args.prompt_groq_key:
            print("Groq API key (input hidden): ", end="", flush=True)
            api_key = getpass.getpass("").strip()

        issues = resolve_issues_with_groq(issues, summaries, args.model, api_key, analysis_goal)

    save_reports(summaries, output_dir, issues, ai_provider, analysis_goal)

    print(
        f"Analyzed {len(summaries)} file(s), found {len(issues)} issue(s). "
        f"Reports written to {output_dir}."
    )


if __name__ == "__main__":
    main()
