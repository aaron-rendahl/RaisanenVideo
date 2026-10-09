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

# Import from our modular pipeline package
from pipeline.models import ArchiveData, to_builder_scenes
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
        description="Generate Phase 3 and Phase 4 execution scripts for archival video processing."
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

    # Ensure all prep subdirectories and clips output folder exist
    for d in [dirs["clips"], dirs["scenes"], dirs["scripts"], dirs["metadata"], dirs["log"], dirs["frames"]]:
        d.mkdir(parents=True, exist_ok=True)

    return dirs


def main():
    args = parse_args()
    vid = args.vid
    base_dir = args.base_dir.resolve()

    print(f"==================================================================")
    print(f"  Initializing Pipeline Builder for: {vid}")
    print(f"==================================================================")

    # 1. Setup Directories
    dirs = setup_directories(base_dir, vid)
    master_mkv_path = dirs["archive"] / f"{vid}.mkv"
    spec_path = dirs["specs"] / f"{vid}.txt"

    # Verify Archival Master exists
    if not master_mkv_path.exists():
        print(f"❌ Error: Archival master not found at {master_mkv_path}")
        sys.exit(1)

    # 2. Ingest Metadata (Prefer LosslessCut Spec text file, fall back to MKV metadata)
    archive_data: ArchiveData = None

    if spec_path.exists():
        print(f"--> Reading LosslessCut spec file: {spec_path}")
        spec_text = spec_path.read_text(encoding="utf-8")
        archive_data = read_tape_spec(spec_text)
        archive_data.print_warnings()
    else:
        print(f"--> Spec file not found at {spec_path}. Attempting MKV embedded metadata import...")
        archive_data = read_mkv_metadata(master_mkv_path)

    if not archive_data or not archive_data.clips:
        print(f"❌ Error: Failed to load valid clip/scene metadata for {vid}")
        sys.exit(1)

    # 3. Transform ArchiveData into Builder Scene Dictionaries
    scenes = to_builder_scenes(
        archive=archive_data,
        vid=vid,
        prep_dir=dirs["prep"].parent,  # Passes 04_prep path
        master_mkv_path=master_mkv_path,
        overall_title=archive_data.global_date or vid,
        fps=args.fps,
        resolution=args.resolution,
    )

    print(f"--> Parsed {len(scenes)} total scene(s) across {len(archive_data.clips)} clip(s).")

    # 4. Generate Phase 3: Extraction Shell Scripts
    print(f"--> Writing Phase 3 extraction scripts to {dirs['scripts']}...")
    extract_script = write_extract_script(
        vid=vid,
        scenes=scenes,
        script_dir=dirs["scripts"],
    )

    # 5. Generate Phase 4: Concat Manifests, ffmetadata, WebVTT, and Concat Scripts
    print(f"--> Writing Phase 4 manifest and concat scripts...")

    black_spacer_path = dirs["scenes"] / f"{vid}-00-black.mp4"

    if archive_data.is_multi_clip:
        # Group scene dictionaries by clip
        clip_groups = {}
        for scene in scenes:
            # scene_id format: VID-CLIP_IDX-SCENE_IDX-TITLE
            parts = scene["scene_id"].split("-")
            clip_idx = parts[1] if len(parts) >= 2 else "01"
            clip_groups.setdefault(clip_idx, []).append(scene)

        for clip_idx, clip_scenes in clip_groups.items():
            clip_id = f"{vid}-{clip_idx}"
            manifest_path = dirs["scripts"] / f"{clip_id}.txt"
            meta_txt_path = dirs["metadata"] / f"{clip_id}.txt"
            meta_vtt_path = dirs["metadata"] / f"{clip_id}.vtt"

            # Derive clip title safely
            first_scene = clip_scenes[0]
            clean_clip_title = first_scene.get("title", f"Clip_{clip_idx}")
            out_mp4_path = dirs["clips"] / f"{clip_id}-{clean_clip_title}.mp4"

            build_concat_manifest(clip_scenes, black_spacer_path, manifest_path)
            build_ffmetadata_file(clip_scenes, meta_txt_path, title=clean_clip_title)
            build_webvtt_file(clip_scenes, meta_vtt_path)

            write_concat_script(
                vid=vid,
                clip_id=clip_id,
                concat_txt_path=manifest_path,
                meta_txt_path=meta_txt_path,
                meta_vtt_path=meta_vtt_path,
                out_mp4_path=out_mp4_path,
                script_dir=dirs["scripts"],
            )
            print(f"    -> Generated concat script for {clip_id}")
    else:
        # Single-clip reel
        clip_id = vid
        manifest_path = dirs["scripts"] / f"{vid}.txt"
        meta_txt_path = dirs["metadata"] / f"{vid}.txt"
        meta_vtt_path = dirs["metadata"] / f"{vid}.vtt"

        reel_title = archive_data.global_date or vid
        out_mp4_path = dirs["clips"] / f"{vid}.mp4"

        build_concat_manifest(scenes, black_spacer_path, manifest_path)
        build_ffmetadata_file(scenes, meta_txt_path, title=reel_title)
        build_webvtt_file(scenes, meta_vtt_path)

        write_concat_script(
            vid=vid,
            clip_id=clip_id,
            concat_txt_path=manifest_path,
            meta_txt_path=meta_txt_path,
            meta_vtt_path=meta_vtt_path,
            out_mp4_path=out_mp4_path,
            script_dir=dirs["scripts"],
        )
        print(f"    -> Generated concat script for {vid}")

if __name__ == "__main__":
    main()
