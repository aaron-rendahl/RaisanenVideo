#!/usr/bin/env python3
"""run_pipeline.py - Master Orchestrator for Modular Archival Video Pipeline"""

import argparse
import sys
from pathlib import Path

from pipeline.orchestrator import generate_pipeline


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate unified clip-by-clip execution script for archival video processing."
    )
    parser.add_argument(
        "--vid",
        required=True,
        help="Unique tape identifier (e.g., Raisanen_1987a)",
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path("."),
        help="Base working directory containing pipeline folders",
    )
    parser.add_argument(
        "--fps",
        default="30000/1001",
        help="Target framerate string (default: 30000/1001)",
    )
    parser.add_argument(
        "--resolution",
        default="720x480",
        help="Target resolution string (default: 720x480)",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    print("==================================================================")
    print(f"  Initializing Clip-by-Clip Pipeline Builder for: {args.vid}")
    print("==================================================================")

    try:
        generate_pipeline(
            vid=args.vid,
            base_dir=args.base_dir,
            fps=args.fps,
            resolution=args.resolution,
        )
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
