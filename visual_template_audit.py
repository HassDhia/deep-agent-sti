"""CLI to audit template versions inside STI report manifests."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable, List

from image_generator import TEMPLATE_VERSION


def _load_manifest(path: Path) -> List[dict]:
    if path.is_dir():
        path = path / "images" / "manifest.json"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path} is not a manifest list")
    return data


def _audit_manifest(path: Path) -> List[str]:
    try:
        entries = _load_manifest(path)
    except Exception as exc:
        return [f"{path}: ERROR: {exc}"]
    issues: List[str] = []
    for idx, entry in enumerate(entries):
        version = entry.get("template_version")
        slot = entry.get("slot") or entry.get("section") or entry.get("type")
        if version != TEMPLATE_VERSION:
            issues.append(
                f"{path} [#{idx} slot={slot}]: ERROR: template_version {version!r} != {TEMPLATE_VERSION!r}"
            )
    if not issues:
        issues.append(f"{path}: Template versions OK ({TEMPLATE_VERSION})")
    return issues


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check manifest template versions.")
    parser.add_argument(
        "paths",
        nargs="+",
        help="One or more report directories or manifest.json files.",
    )
    args = parser.parse_args(argv)

    exit_code = 0
    for raw in args.paths:
        path = Path(raw)
        results = _audit_manifest(path)
        for line in results:
            print(line)
            if "ERROR" in line:
                exit_code = 1
    return exit_code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
