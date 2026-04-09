#!/usr/bin/env python3
"""
Unzip PLFS archives from data/raw/plfs_zips into data/raw/plfs_extracted/<round>/.

Archives are named like: 204_july2017_june2018_2470 (no .zip suffix).
Each round becomes its own folder (e.g. 204_july2017_june2018).
Writes inventory.json next to the zips.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

# Project root = directory containing this script
ROOT = Path(__file__).resolve().parent
DEFAULT_ZIPS = ROOT / "data" / "raw" / "plfs_zips"
DEFAULT_OUT = ROOT / "data" / "raw" / "plfs_extracted"

# Filename pattern: {catalog}_{slug}_{resource_id}
ROUND_RE = re.compile(r"^(\d+_[a-z0-9_]+)_\d+$", re.I)


def round_folder_name(archive_path: Path) -> str:
    name = archive_path.name
    if name.endswith(".zip"):
        name = name[:-4]
    m = ROUND_RE.match(name)
    if m:
        return m.group(1)
    return name


def main() -> int:
    zips_dir = DEFAULT_ZIPS
    out_root = DEFAULT_OUT
    if not zips_dir.is_dir():
        print(f"Not found: {zips_dir}", file=sys.stderr)
        return 2

    out_root.mkdir(parents=True, exist_ok=True)
    inventory: list = []

    for arch in sorted(zips_dir.iterdir()):
        if not arch.is_file():
            continue
        if arch.name == "download_manifest.json" or arch.name.startswith("."):
            continue

        folder = round_folder_name(arch)
        dest = out_root / folder
        dest.mkdir(parents=True, exist_ok=True)

        print(f"Extracting {arch.name} -> {dest.relative_to(ROOT)}")
        try:
            subprocess.run(
                ["unzip", "-o", "-q", str(arch), "-d", str(dest)],
                check=True,
            )
        except subprocess.CalledProcessError as e:
            print(f"  ERROR unzip: {e}", file=sys.stderr)
            inventory.append(
                {
                    "archive": str(arch.relative_to(ROOT)),
                    "extracted_to": str(dest.relative_to(ROOT)),
                    "error": str(e),
                }
            )
            continue

        inner = sorted(dest.iterdir())
        inventory.append(
            {
                "archive": str(arch.relative_to(ROOT)),
                "extracted_to": str(dest.relative_to(ROOT)),
                "files": [p.name for p in inner if p.is_file()],
            }
        )

    inv_path = out_root / "inventory.json"
    inv_path.write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    print(f"\nWrote {inv_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
