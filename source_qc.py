"""CLI to validate per-report source coverage."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

from config import STIConfig


def _load_stats(path: Path) -> tuple[Path, dict]:
    target = path
    if target.is_dir():
        target = target / "source_stats.json"
    if not target.exists():
        raise FileNotFoundError(f"{target} does not exist")
    data = json.loads(target.read_text(encoding="utf-8"))
    return target, data


def _lint_stats(stats: dict) -> List[str]:
    issues: List[str] = []
    total = int(stats.get("total") or 0)
    core = int(stats.get("core") or 0)
    unique_domains = int(stats.get("unique_domains") or 0)
    data_heavy = int(stats.get("data_heavy") or 0)
    tier_counts = stats.get("tier_counts") or {}
    in_window = int(tier_counts.get("core") or 0)
    background = int(tier_counts.get("context") or 0)
    domain_counts = stats.get("domain_counts") or {}
    dominant_ratio = float(stats.get("dominant_ratio") or 0.0)
    support_coverage = stats.get("support_coverage")

    def _require(condition: bool, label: str, actual: int, target: int) -> None:
        if not condition:
            issues.append(f"ERROR: {label} {actual} < required {target}")

    _require(total >= STIConfig.SOURCE_MIN_TOTAL, "total sources", total, STIConfig.SOURCE_MIN_TOTAL)
    _require(core >= STIConfig.SOURCE_MIN_CORE, "core sources", core, STIConfig.SOURCE_MIN_CORE)
    _require(
        unique_domains >= STIConfig.SOURCE_MIN_UNIQUE_DOMAINS,
        "unique domains",
        unique_domains,
        STIConfig.SOURCE_MIN_UNIQUE_DOMAINS,
    )
    _require(
        data_heavy >= STIConfig.SOURCE_MIN_DATA_HEAVY,
        "data-heavy sources",
        data_heavy,
        STIConfig.SOURCE_MIN_DATA_HEAVY,
    )
    _require(
        in_window >= STIConfig.SOURCE_MIN_IN_WINDOW,
        "in-window sources",
        in_window,
        STIConfig.SOURCE_MIN_IN_WINDOW,
    )
    _require(
        background >= STIConfig.SOURCE_MIN_BACKGROUND,
        "background sources",
        background,
        STIConfig.SOURCE_MIN_BACKGROUND,
    )
    if domain_counts and total:
        if dominant_ratio > STIConfig.SOURCE_MAX_DOMAIN_RATIO:
            issues.append(
                f"ERROR: dominant domain ratio {dominant_ratio:.2f} exceeds allowed {STIConfig.SOURCE_MAX_DOMAIN_RATIO:.2f}"
            )
        elif dominant_ratio > (STIConfig.SOURCE_MAX_DOMAIN_RATIO * 0.9):
            issues.append(
                f"WARN: dominant domain ratio {dominant_ratio:.2f} approaching limit {STIConfig.SOURCE_MAX_DOMAIN_RATIO:.2f}"
            )
    if support_coverage is not None and support_coverage < STIConfig.SIGNAL_SUPPORT_COVERAGE_MIN:
        issues.append(
            f"WARN: signal support coverage {support_coverage:.2f} < required {STIConfig.SIGNAL_SUPPORT_COVERAGE_MIN:.2f}"
        )
    if stats.get("thin_evidence"):
        issues.append("WARN: thin_evidence flag set in stats")
    return issues


def _check_path(raw_path: str) -> List[str]:
    path = Path(raw_path)
    try:
        target, stats = _load_stats(path)
    except FileNotFoundError as exc:
        return [f"{raw_path}: ERROR: {exc}"]
    except Exception as exc:  # pragma: no cover - safety net
        return [f"{raw_path}: ERROR: unable to read stats ({exc})"]
    issues = _lint_stats(stats)
    if not issues:
        return [f"{target}: Source coverage OK"]
    return [f"{target}: {issue}" for issue in issues]


def _gather_records(paths: Sequence[str]) -> List[Tuple[str, dict]]:
    records: List[Tuple[str, dict]] = []
    for raw in paths:
        try:
            target, stats = _load_stats(Path(raw))
        except Exception:
            continue
        records.append((str(target), stats))
    return records


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = pct / 100.0 * (len(ordered) - 1)
    lower = int(rank)
    upper = min(lower + 1, len(ordered) - 1)
    weight = rank - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _print_dashboard(records: List[Tuple[str, dict]]) -> None:
    if not records:
        print("\nHarvest dashboard: no reports found.")
        return
    print("\nHarvest dashboard:")
    metrics = [
        ("total", [rec[1].get("total", 0) for rec in records]),
        ("core", [rec[1].get("core", 0) for rec in records]),
        ("unique_domains", [rec[1].get("unique_domains", 0) for rec in records]),
        (
            "in_window",
            [rec[1].get("tier_counts", {}).get("core", 0) for rec in records],
        ),
    ]
    for label, values in metrics:
        numeric_values = [float(v) for v in values if isinstance(v, (int, float))]
        if not numeric_values:
            continue
        print(
            f"  {label}: min={min(numeric_values):.1f} "
            f"median={statistics.median(numeric_values):.1f} "
            f"p75={_percentile(numeric_values, 75):.1f} "
            f"p90={_percentile(numeric_values, 90):.1f} "
            f"max={max(numeric_values):.1f}"
        )
    thin_reports = [path for path, data in records if data.get("thin_evidence")]
    if thin_reports:
        print(f"  Thin evidence reports: {len(thin_reports)} (showing up to 5)")
        for entry in thin_reports[:5]:
            print(f"    - {entry}")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate STI source coverage sidecars.")
    parser.add_argument("paths", nargs="+", help="Report directories or source_stats.json files.")
    parser.add_argument(
        "--dashboard",
        action="store_true",
        help="After validation, print percentile summaries across all provided reports.",
    )
    args = parser.parse_args(argv)

    exit_code = 0
    for raw_path in args.paths:
        messages = _check_path(raw_path)
        for message in messages:
            print(message)
            if "ERROR:" in message:
                exit_code = 1
    if args.dashboard:
        records = _gather_records(args.paths)
        _print_dashboard(records)
    return exit_code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))

