#!/usr/bin/env python3
"""
03_make_clips.py

Generates web-ready MP4 derivative clips from clean Matroska (.mkv) archival versions.
Uses a two-stage intermediate file architecture (/tmp/stage1_<clip_id>.mkv with UtVideo/PCM)
to isolate heavy filter chains and prevent pipeline deadlocks. 

Muxes dual chapter metadata: global ISO metadata (;FFMETADATA1) for multi-platform players (VLC, IINA) 
and co-located WebVTT sidecars mapped as 3GPP MOV text tracks (-c:s mov_text) for native macOS 
QuickLook and QuickTime Player chapter navigation.

Usage:
  ./scripts/03_make_clips.py [FLAGS] <TAPE_NAME>

Flags:
  --debug-scripts, --split-scripts
                      Generates standalone multi-line bash scripts (encode_XX_*.sh),
                      FFmetadata text files (meta_XX.txt), and WebVTT chapter files
                      (meta_XX.vtt) for each clip into the log directory, plus a master
                      'run_all.sh'. Does not execute FFmpeg directly.

  --dry-run, --script Generates a single, standalone 'run_encode.sh' bash script in 
                      the log directory instead of executing FFmpeg directly.

  --uncropped-frames  Extracts uncropped PNG snapshots ('a.png') for crop evaluation.
                      Clears previous 'a.png' files; leaves 'b.png' intact.

  --cropped-frames    Extracts cropped PNG snapshots ('b.png') using current spec crop parameters.
                      Clears previous 'b.png' files; leaves 'a.png' intact for side-by-side review.

  --frames-only       Shortcut flag to generate both uncropped ('a') and cropped ('b') PNG snapshots.

  --test, --test-clips Encodes 10-second sample preview MP4s per subchapter into the log folder to 
                      quickly verify macOS Finder previews, QuickTime chapter tracks, and cut quality.

  --clean, --clean-log Removes the entire diagnostic directory (<TAPE_NAME>-log) and exits.

  (No Flags)         Runs full derivative clip MP4 encoding pipeline. Does not extract PNGs.

Directory Structure:
  Input Archival:     01_archive/<TAPE_NAME>.mkv
  Output Clips:       02_clips/<TAPE_NAME>/<TAPE_NAME>_<CLIP_IDX>_<TITLE>.mp4
  Diagnostics & Log:  02_clips/<TAPE_NAME>-log/ (contains meta_XX.txt, meta_XX.vtt, logs, scripts)
"""

import os
import shlex
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# Base Directory Paths
BASE_DIR = Path(__file__).resolve().parent.parent
ARCHIVE_DIR = BASE_DIR / "01_archive"
CLIPS_DIR = BASE_DIR / "02_clips"
SRC_DIR = BASE_DIR / "src"

# Add src/ to sys.path for mkv_reader and video_duration imports
sys.path.insert(0, str(SRC_DIR))

# Import execution helpers from sidecar module
from mkv_reader import read_mkv_metadata
from video_duration import get_video_duration
from ffmpeg_utils import (
    build_clip_pipeline,
    build_crop_filter,
    clean_directory,
    convert_ffmetadata_to_vtt,
    format_pipeline_to_bash,
    generate_concat_ffmetadata,
)
from segment_utils import (
    has_gaps,
    resolve_clip_subchapters,
    resolve_subsegments,
)
from time_utils import (
    format_elapsed_time,
    parse_timestamp_to_seconds,
)

ACTIVE_TEMP_FILES = set()


def register_cleanup_signals() -> None:
    """Ensures temporary MKV files are unlinked if the script is interrupted (Ctrl+C)."""

    def handle_signal(sig, frame):
        print("\nProcess interrupted. Cleaning temporary files...")
        for tmp_file in list(ACTIVE_TEMP_FILES):
            if os.path.exists(tmp_file):
                try:
                    os.remove(tmp_file)
                except OSError:
                    pass
        sys.exit(130)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)


@dataclass
class CLIConfig:
    tape_name: str
    do_clean: bool = False
    do_test: bool = False
    do_dry_run: bool = False
    do_split_scripts: bool = False
    do_uncropped: bool = False
    do_cropped: bool = False

    @property
    def frames_mode(self) -> bool:
        return self.do_uncropped or self.do_cropped


def parse_cli_args(argv: list[str]) -> CLIConfig:
    if len(argv) < 2:
        print(
            "Usage: ./scripts/03_make_clips.py [--clean | --test |"
            " --uncropped-frames | --cropped-frames | --frames-only | --dry-run"
            " | --debug-scripts] <TAPE_NAME>"
        )
        sys.exit(1)

    tape_args = [arg for arg in argv[1:] if not arg.startswith("--")]
    if not tape_args:
        print("Error: Missing tape name argument.")
        sys.exit(1)

    return CLIConfig(
        tape_name=Path(tape_args[0]).stem,
        do_clean="--clean" in argv or "--clean-log" in argv,
        do_test="--test" in argv or "--test-clips" in argv,
        do_dry_run="--dry-run" in argv or "--script" in argv,
        do_split_scripts="--debug-scripts" in argv or "--split-scripts" in argv,
        do_uncropped="--uncropped-frames" in argv or "--frames-only" in argv,
        do_cropped="--cropped-frames" in argv or "--frames-only" in argv,
    )


def capture_diagnostic_frames(
    clip,
    chapter_targets: list[tuple[str, str, float, float]],
    mkv_path: Path,
    tape_log_dir: Path,
    ffmpeg_crop: str,
    cfg: CLIConfig,
    log_file,
    single_script_lines: list[str],
    debug: bool = False,
) -> None:
    """Captures diagnostic frame snapshots (1=start, 2=mid, 3=end) using pre-resolved chapter bounds."""
    tape_stem = tape_log_dir.name.replace("-log", "")

    if debug:
        print(f"\n  [DEBUG] Clip [{getattr(clip, 'idx', '?')}] '{getattr(clip, 'title', '')}' has {len(chapter_targets)} subchapter target(s):")

    for sub_tag, sub_title, s_sec, e_sec in chapter_targets:
        duration = max(0.1, e_sec - s_sec)
        mid_sec = s_sec + (duration / 2.0)
        end_sec = max(s_sec, e_sec - 0.2)

        print(f"    -> Subchapter [{sub_tag}] '{sub_title}': start={s_sec:.3f}s, mid={mid_sec:.3f}s, end={end_sec:.3f}s (dur={duration:.1f}s)")

        timestamps = [("1", s_sec), ("2", mid_sec), ("3", end_sec)]

        if hasattr(clip, "subchapters") and clip.subchapters:
            snapshot_prefix = f"{tape_stem}_{sub_tag}_{sub_title}"
        else:
            snapshot_prefix = f"{tape_stem}_{clip.idx}_{sub_title}"

        for pos_code, t_sec in timestamps:
            frame_stem = f"{snapshot_prefix}_{pos_code}"

            if cfg.do_uncropped:
                out_png = tape_log_dir / f"{frame_stem}a.png"
                cmd = [
                    "ffmpeg", "-y", "-loglevel", "warning",
                    "-apply_cropping", "0",
                    "-ss", f"{t_sec:.3f}", "-i", str(mkv_path),
                    "-vf", "format=rgb24", "-vframes", "1", "-update", "1",
                    str(out_png)
                ]
                if debug:
                    print(f"       [RUN UNCROPPED] t={t_sec:.3f}s -> {out_png.name}")
                if cfg.do_dry_run or cfg.do_split_scripts:
                    single_script_lines.append(" ".join(shlex.quote(c) for c in cmd) + "\n")
                else:
                    subprocess.run(cmd, stdout=log_file, stderr=log_file, check=True)

            if cfg.do_cropped and ffmpeg_crop:
                out_png = tape_log_dir / f"{frame_stem}b.png"
                cmd = [
                    "ffmpeg", "-y", "-loglevel", "warning",
                    "-apply_cropping", "0",
                    "-ss", f"{t_sec:.3f}", "-i", str(mkv_path),
                    "-vf", f"{ffmpeg_crop},format=rgb24", "-vframes", "1", "-update", "1",
                    str(out_png)
                ]
                if debug:
                    print(f"       [RUN CROPPED]   t={t_sec:.3f}s -> {out_png.name}")
                if cfg.do_dry_run or cfg.do_split_scripts:
                    single_script_lines.append(" ".join(shlex.quote(c) for c in cmd) + "\n")
                else:
                    subprocess.run(cmd, stdout=log_file, stderr=log_file, check=True)
                    
def process_clip_pipeline(
    clip,
    pipe: dict,
    cfg: CLIConfig,
    tape_log_dir: Path,
    safe_title: str,
    log_file,
    run_all_lines: list[str],
    single_script_lines: list[str],
) -> None:
    """Dispatches pipeline execution to script generator or direct subprocess."""
    multiline_cmd = format_pipeline_to_bash(
        pipe["stage1"], pipe["stage2"], pipe["tmp_mkv"]
    )

    if cfg.do_split_scripts:
        print(
            f"[{clip.idx}] Writing multi-line debug script for:"
            f" {clip.title}...",
            end="",
            flush=True,
        )
        script_filename = f"encode_{clip.idx}_{safe_title}.sh"
        sub_script_path = tape_log_dir / script_filename

        script_body = [
            "#!/usr/bin/env bash",
            "set -e\n",
            f"# Clip [{clip.idx}]: {clip.title}",
            multiline_cmd + "\n",
        ]
        sub_script_path.write_text("\n".join(script_body), encoding="utf-8")
        sub_script_path.chmod(0o755)
        run_all_lines.append(f"./{script_filename}")

    elif cfg.do_dry_run:
        single_script_lines.append(
            f"# --- Clip [{clip.idx}]: {clip.title} ---"
        )
        single_script_lines.append(multiline_cmd + "\n")

    else:
        print(
            f"[{clip.idx}] Encoding {'TEST ' if cfg.do_test else ''}clip:"
            f" {clip.title}...",
            end="",
            flush=True,
        )
        log_file.write(f"\n--- Encoding Clip [{clip.idx}]: {clip.title} ---\n")
        log_file.flush()

        subprocess.run(
            pipe["stage1"], stdout=log_file, stderr=log_file, check=True
        )
        subprocess.run(
            pipe["stage2"], stdout=log_file, stderr=log_file, check=True
        )


def main():
    register_cleanup_signals()
    cfg = parse_cli_args(sys.argv)

    CLIPS_DIR.mkdir(parents=True, exist_ok=True)
    tape_output_dir = CLIPS_DIR / cfg.tape_name
    tape_log_dir = CLIPS_DIR / f"{cfg.tape_name}-log"

    if cfg.do_clean:
        if tape_log_dir.exists():
            print(f"Removing diagnostic log directory: {tape_log_dir}")
            shutil.rmtree(tape_log_dir)
            print("Clean complete!")
        sys.exit(0)

    tape_output_dir.mkdir(exist_ok=True)
    tape_log_dir.mkdir(exist_ok=True)

    mkv_path = ARCHIVE_DIR / f"{cfg.tape_name}.mkv"

    if not mkv_path.exists():
        print(f"Error: Archival MKV missing at '{mkv_path}'.")
        sys.exit(1)

    print(f"Reading master metadata directly from container: {mkv_path.name}")
    data = read_mkv_metadata(str(mkv_path))
    
    total_duration_str = get_video_duration(str(mkv_path))
    data.resolve_missing_end_times(total_duration_str)
    total_duration_sec = parse_timestamp_to_seconds(total_duration_str)

    clean_directory(
        tape_log_dir,
        cfg.do_uncropped,
        cfg.do_cropped,
        cfg.frames_mode,
        cfg.do_test,
    )

    log_file_path = tape_log_dir / "ffmpeg_encode.log"
    tape_start_time = time.perf_counter()
    single_script_lines = ["#!/usr/bin/env bash", "set -e\n"]
    run_all_lines = ["#!/usr/bin/env bash", "set -e\n"]

    with open(log_file_path, "a", encoding="utf-8") as log_file:
        for clip in data.clips:
            clip_start_time = time.perf_counter()
            # Single source of truth for subchapter resolution
            chapter_targets = resolve_clip_subchapters(clip, total_duration_sec)
            segments = resolve_subsegments(clip, total_duration_sec)
            
            safe_title = (
                "".join(
                    c if c.isalnum() or c in (" ", "-", "_") else ""
                    for c in clip.title
                )
                .strip()
                .replace(" ", "_")
            )

            crop_val = clip.crop if clip.crop else data.global_crop
            ffmpeg_crop = build_crop_filter(crop_val)

            if cfg.frames_mode:
                print(
                    f"[{clip.idx}] Capturing diagnostic frames for:"
                    f" {clip.title}...",
                    end="",
                    flush=True,
                )
                capture_diagnostic_frames(
                    clip,
                    chapter_targets,
                    mkv_path,
                    tape_log_dir,
                    ffmpeg_crop,
                    cfg,
                    log_file,
                    single_script_lines,
                )
                print(
                    " Done"
                    f" ({format_elapsed_time(time.perf_counter() - clip_start_time)})"
                )
                continue

            # 1. Determine base file stem
            if len(data.clips) == 1:
                base_stem = cfg.tape_name
            else:
                base_stem = f"{cfg.tape_name}_{clip.idx}_{safe_title}"
            
            # 2. Resolve output directory and filename based on test mode
            if cfg.do_test:
                output_mp4 = tape_log_dir / f"{base_stem}_test.mp4"
            else:
                output_mp4 = tape_output_dir / f"{base_stem}.mp4"

            meta_file_path = tape_log_dir / f"meta_{clip.idx}.txt"
            vtt_file_path = tape_log_dir / f"meta_{clip.idx}.vtt"

            generate_concat_ffmetadata(clip, segments, str(meta_file_path), is_test=cfg.do_test)
            convert_ffmetadata_to_vtt(str(meta_file_path), str(vtt_file_path))

            vf_base = (
                "bwdif=mode=send_field:deint=all"
                + (f",{ffmpeg_crop}" if ffmpeg_crop else "")
                + ",setpts=PTS-STARTPTS"
            )
            pipe = build_clip_pipeline(
                mkv_path=mkv_path,
                output_mp4=output_mp4,
                meta_file_path=meta_file_path,
                vtt_file_path=vtt_file_path,
                segments=segments,
                vf_base=vf_base,
                is_gapped=has_gaps(segments),
                do_test=cfg.do_test,
                clip_id=str(clip.idx),
            )

            ACTIVE_TEMP_FILES.add(pipe["tmp_mkv"])

            try:
                process_clip_pipeline(
                    clip,
                    pipe,
                    cfg,
                    tape_log_dir,
                    safe_title,
                    log_file,
                    run_all_lines,
                    single_script_lines,
                )
                print(
                    " Done"
                    f" ({format_elapsed_time(time.perf_counter() - clip_start_time)})"
                )
            finally:
                if os.path.exists(pipe["tmp_mkv"]):
                    os.remove(pipe["tmp_mkv"])
                ACTIVE_TEMP_FILES.discard(pipe["tmp_mkv"])

    if cfg.do_split_scripts:
        master = tape_log_dir / "run_all.sh"
        master.write_text("\n".join(run_all_lines) + "\n", encoding="utf-8")
        master.chmod(0o755)
    elif cfg.do_dry_run:
        script_out = tape_log_dir / "run_encode.sh"
        script_out.write_text("\n".join(single_script_lines), encoding="utf-8")
        script_out.chmod(0o755)

    print(
        f"\nAll operations complete for '{cfg.tape_name}' in"
        f" {format_elapsed_time(time.perf_counter() - tape_start_time)}!"
    )


if __name__ == "__main__":
    main()
