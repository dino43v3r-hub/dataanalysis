from __future__ import annotations

import argparse
import csv
import json
import statistics
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


def find_data_files(input_dir: Path) -> list[Path]:
    if not input_dir.exists():
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


def analyze_file(path: Path) -> FileSummary:
    suffix = path.suffix.lower()

    if suffix == ".csv":
        return analyze_delimited(path, ",")

    if suffix == ".tsv":
        return analyze_delimited(path, "\t")

    if suffix == ".json":
        return analyze_json(path)

    return analyze_text(path)


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


def save_reports(summaries: list[FileSummary], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "files_analyzed": len(summaries),
        "files": [asdict(summary) for summary in summaries],
    }

    (output_dir / "analysis_summary.json").write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )
    (output_dir / "analysis_summary.md").write_text(
        build_markdown_report(summaries),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze local data files.")
    parser.add_argument("--input", default="data", help="Input folder to scan.")
    parser.add_argument("--output", default="reports", help="Output folder for reports.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_dir = Path(args.input)
    output_dir = Path(args.output)

    summaries = [analyze_file(path) for path in find_data_files(input_dir)]
    save_reports(summaries, output_dir)

    print(f"Analyzed {len(summaries)} file(s). Reports written to {output_dir}.")


if __name__ == "__main__":
    main()
