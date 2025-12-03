"""CLI to evaluate visual QA sidecar files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, List

from visual_lint import REQUIRED_ANCHORS, lint_visual_stats


def _collect_issues(target: Path) -> List[str]:
    if target.is_dir():
        target = target / "visual_stats.json"
    if not target.exists():
        return [f"{target}: ERROR: visual_stats.json not found"]
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - rare
        return [f"{target}: ERROR: could not parse JSON ({exc})"]
    required = data.get("required_anchors") or REQUIRED_ANCHORS
    issues = lint_visual_stats(data, required_anchors=required)
    if not issues:
        return []
    return [f"{target}: {issue}" for issue in issues]


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Visual QA checker for STI reports.")
    parser.add_argument(
        "paths",
        nargs="+",
        help="One or more report directories or visual_stats.json files.",
    )
    args = parser.parse_args(argv)

    exit_code = 0
    for raw_path in args.paths:
        path = Path(raw_path)
        issues = _collect_issues(path)
        if not issues:
            print(f"{path}: Visual QA OK")
            continue
        for issue in issues:
            print(issue)
            if "ERROR:" in issue:
                exit_code = 1
    return exit_code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
