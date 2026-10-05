#!/usr/bin/env python3
import sys
from pathlib import Path

# Project Paths
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

ARCHIVE_DIR = PROJECT_ROOT / "01_archive"
SPECS_DIR = PROJECT_ROOT / "03_specs"
SRC_DIR = PROJECT_ROOT / "src"

# Add src/ to Python path for imports
sys.path.insert(0, str(SRC_DIR))

from spec_reader import read_tape_spec
from mkv_writer import write_mkv_metadata


def resolve_tape_name(input_str: str) -> str:
    """Extract bare tape name from full path or plain string."""
    return Path(input_str).stem


def main():
    if len(sys.argv) < 2:
        print("Usage: ./scripts/02_write_metadata.py <TAPE_NAME_OR_PATH>")
        sys.exit(1)

    tape_name = resolve_tape_name(sys.argv[1])
    spec_path = SPECS_DIR / f"{tape_name}.txt"
    mkv_path = ARCHIVE_DIR / f"{tape_name}.mkv"

    if not spec_path.exists():
        print(f"Error: Spec file not found at '{spec_path}'")
        sys.exit(1)

    if not mkv_path.exists():
        print(f"Error: Archival MKV file not found at '{mkv_path}'")
        sys.exit(1)

    print(f"Parsing spec file: {spec_path.name}")
    data = read_tape_spec(spec_path.read_text())

    write_mkv_metadata(str(mkv_path), data)


if __name__ == "__main__":
    main()
