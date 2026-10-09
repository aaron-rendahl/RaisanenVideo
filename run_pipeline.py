#!/usr/bin/env python3
"""
run_pipeline.py - Master Orchestrator for Modular Archival Video Pipeline

Usage:
    python run_pipeline.py --vid Raisanen_1987a
    python run_pipeline.py --vid Raisanen_1987a --fps 20000/1001 --resolution 720x480
"""

import argparse
import sys
from pathlib import Path

from pipeline.adapters import to_builder_data
from pipeline.models import ArchiveData
from pipeline.spec import read_tape_spec
from pipeline.mkv import read_mkv_metadata
from pipeline.script_builders import (
    build_concat_manifest,
    build_ffmetadata_file,
    build_webvtt_file,
    write_extract_script,
    write_concat_script,
)


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
        help="Base working directory containing pipeline folders (default: current dir)",
    )
    parser.add_argument(
        "--fps",
        default="30000/1001",
        help="Target framerate string (default: 30000/1001; use 20000/1001 for retimed 8mm)",
    )
    parser.add_argument(
        "--resolution",
        default="720x480",
        help="Target resolution string (default: 720x480)",
    )
    return parser.parse_args()


def setup_directories(base_dir: Path, vid: str) -> dict:
    """Sets up Phase 0 folder layout and returns resolved paths."""
    prep_dir = base_dir / "04_prep" / vid

    dirs = {
        "originals": base_dir / "00_originals",
        "archive": base_dir / "01_archive",
        "clips": base_dir / "02_clips" / vid,
        "specs": base_dir / "03_specs",
        "prep": prep_dir,
        "scenes": prep_dir / "scenes",
        "scripts": prep_dir / "scripts",
        "metadata": prep_dir / "metadata",
        "log": prep_dir / "log",
        "frames": prep_dir / "frames",
    }

    for d in [
        dirs["clips"],
        dirs["scenes"],
        dirs["scripts"],
        dirs["metadata"],
        dirs["log"],
        dirs["frames"],
    ]:
        d.mkdir(parents=True, exist_ok=True)

    return dirs


def main():
    args = parse_args()
    vid = args.vid
    base_dir = args.base_dir.resolve()

    print("==================================================================")
    print(f"  Initializing Clip-by-Clip Pipeline Builder for: {vid}")
    print("==================================================================")

    dirs = setup_directories(base_dir, vid)
    master_mkv_path = dirs["archive"] / f"{vid}.mkv"
    spec_path = dirs["specs"] / f"{vid}.txt"

    if not master_mkv_path.exists():
        print(f"❌ Error: Archival master not found at {master_mkv_path}")
        sys.exit(1)

    # 1. Ingest Metadata
    archive_data: ArchiveData = None
    if spec_path.exists():
        print(f"--> Reading LosslessCut spec file: {spec_path}")
        spec_text = spec_path.read_text(encoding="utf-8")
        archive_data = read_tape_spec(spec_text)
        archive_data.print_warnings()
    else:
        print(
            f"--> Spec file not found at {spec_path}. Attempting MKV embedded metadata import..."
        )
        archive_data = read_mkv_metadata(master_mkv_path)

    if not archive_data or not archive_data.clips:
        print(f"❌ Error: Failed to load valid clip/scene metadata for {vid}")
        sys.exit(1)

    # 2. Transform into hierarchical Builder Data
    builder_data = to_builder_data(
        archive=archive_data,
        vid=vid,
        scenes_dir=dirs["scenes"],
        clips_dir=dirs["clips"],
        master_mkv_path=master_mkv_path,
        overall_title=archive_data.global_date or vid,
        fps=args.fps,
        resolution=args.resolution,
    )

    clips = builder_data["clips"]
    total_scenes = sum(len(clip["scenes"]) for clip in clips)
    print(f"--> Parsed {total_scenes} total scene(s) across {len(clips)} clip(s).")

    # 3. Generate individual scene & spacer `.sh` scripts using existing builder
    write_extract_script(
        vid=vid,
        clips=clips,
        script_dir=dirs["scripts"],
        scenes_dir=dirs["scenes"],
    )

    # 4. Generate metadata sidecars, concat scripts, and assemble the master orchestrator body
    master_body_lines = []

    for clip in clips:
        clip_idx = clip["clip_idx"]
        clip_id = f"{vid}-{clip_idx}"
        clip_scenes = clip["scenes"]

        manifest_path = dirs["scripts"] / f"{clip_id}.txt"
        meta_txt_path = dirs["metadata"] / f"{clip_id}.txt"
        meta_vtt_path = dirs["metadata"] / f"{clip_id}.vtt"
        black_spacer_path = Path(clip["black_spacer_path"])
        clean_clip_title = clip.get("title") or f"Clip_{clip_idx}"

        # Sidecar files
        build_concat_manifest(clip_scenes, black_spacer_path, manifest_path)
        build_ffmetadata_file(
            clip_scenes, meta_txt_path, title=clean_clip_title
        )
        build_webvtt_file(clip_scenes, meta_vtt_path)

        # Per-clip concat bash script
        clip_concat_sh = write_concat_script(
            vid=vid,
            clip=clip,
            concat_txt_path=manifest_path,
            meta_txt_path=meta_txt_path,
            meta_vtt_path=meta_vtt_path,
            script_dir=dirs["scripts"],
        )

        # --- Assemble Sequential Clip Workflow Block ---
        master_body_lines.append(f"# " + "-" * 78)
        master_body_lines.append(f"# CLIP {clip_idx}: {clean_clip_title}")
        master_body_lines.append(f"# " + "-" * 78)
        master_body_lines.append("(")
        master_body_lines.append(
            f'  SCRIPT_DIR="{dirs["scripts"].resolve()}"'
        )
        master_body_lines.append(
            f'  echo "==> [START] Processing Clip {clip_idx}/{len(clips)}: {clean_clip_title}"'
        )

        # Step A: Run scene extractions for this clip using $SCRIPT_DIR
        for scene in clip_scenes:
            master_body_lines.append(
                f'  bash "$SCRIPT_DIR/{scene["scene_id"]}.sh"'
            )

        # Step B: Run black spacer generation for this clip using $SCRIPT_DIR
        master_body_lines.append(f'  bash "$SCRIPT_DIR/{clip_id}-black.sh"')

        # Step C: Concatenate scenes + spacer & inject metadata using $SCRIPT_DIR
        master_body_lines.append(
            f'  bash "$SCRIPT_DIR/{clip_concat_sh.name}"'
        )

        master_body_lines.append(
            f'  echo "==> [COMPLETE] Clip {clip_idx} finished successfully!"'
        )
        master_body_lines.append(")")
        master_body_lines.append("")

    # 5. Write single unified master script (01_run_pipeline.sh)
    master_script_path = dirs["scripts"] / "01_run_pipeline.sh"
    master_script_content = (
        f"""#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Master Processing Pipeline for Tape: {vid}
# Generated clip-by-clip orchestrator
# ==============================================================================

echo "==> Launching clip-by-clip pipeline for {vid}..."
echo ""

"""
        + "\n".join(master_body_lines)
        + """
echo "=================================================================="
echo "  [SUCCESS] All clips built, concatenated, and tagged!"
echo "=================================================================="
"""
    )

    master_script_path.write_text(master_script_content)
    master_script_path.chmod(0o755)
    print(f"--> Master pipeline script generated at: {master_script_path}")


if __name__ == "__main__":
    main()
