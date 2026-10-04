#!/usr/bin/env python3
"""
03_make_clips.py

Generates web-ready MP4 derivative clips from clean Matroska (.mkv) archival versions.
Uses a two-stage piped architecture (NUT RAM pipe) with normalized PTS timestamps and
forced initial keyframes (IDR) for robust macOS Finder preview generation, Apple AVC1
compatibility, and precise audio/video sync.

Usage:
  ./scripts/03_make_clips.py [FLAGS] <TAPE_NAME>

Flags:
  --debug-scripts, --split-scripts
                      Generates standalone multi-line bash scripts (encode_XX_*.sh) and
                      persistent metadata text files (meta_XX.txt) for each clip into the
                      log directory, plus a master 'run_all.sh'. Does not execute FFmpeg.

  --dry-run, --script Generates a single, standalone 'run_encode.sh' bash script in 
                      the log directory instead of executing FFmpeg directly.

  --uncropped-frames  Extracts uncropped PNG snapshots ('a.png') for crop evaluation.
                      Clears previous 'a.png' files; leaves 'b.png' intact.

  --cropped-frames    Extracts cropped PNG snapshots ('b.png') using current spec crop parameters.
                      Clears previous 'b.png' files; leaves 'a.png' intact for side-by-side review.

  --frames-only       Shortcut flag to generate both uncropped ('a') and cropped ('b') PNG snapshots.

  --test, --test-clips Encodes 10-second sample preview MP4s per subchapter into the log folder to 
                      quickly verify macOS Finder previews and cut quality without full encoding.

  --clean, --clean-log Removes the entire diagnostic directory (<TAPE_NAME>-log) and exits.

  (No Flags)          Runs full derivative clip MP4 encoding pipeline. Does not extract PNGs.

Directory Structure:
  Input Archival:     01_archive/<TAPE_NAME>.mkv
  Input Spec:         03_specs/<TAPE_NAME>.txt
  Output Clips:       02_clips/<TAPE_NAME>/<TAPE_NAME>_<CLIP_IDX>_<TITLE>.mp4
  Diagnostics & Log:  02_clips/<TAPE_NAME>-log/
"""

import sys
import time
import shutil
import shlex
import tempfile
import subprocess
import os
import re
from pathlib import Path

# Project Paths
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

ARCHIVE_DIR = PROJECT_ROOT / "01_archive"
SPECS_DIR = PROJECT_ROOT / "03_specs"
CLIPS_DIR = PROJECT_ROOT / "02_clips"
SRC_DIR = PROJECT_ROOT / "src"

sys.path.insert(0, str(SRC_DIR))

from spec_reader import read_tape_spec
from video_duration import get_video_duration


def parse_timestamp_to_seconds(ts_str: str) -> float:
    """Convert HH:MM:SS.mmm or seconds string to total seconds float."""
    if not ts_str:
        return 0.0
    parts = ts_str.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    return float(ts_str)


def format_elapsed_time(seconds: float) -> str:
    """Formats floating-point seconds into human-readable duration."""
    if seconds < 60:
        return f"{seconds:.2f}s"
    minutes = int(seconds // 60)
    rem_seconds = seconds % 60
    return f"{minutes}m {rem_seconds:.1f}s"


def build_crop_filter(crop_str: str) -> str:
    """
    Convert spec crop 'LEFT RIGHT TOP BOTTOM' into FFmpeg crop filter string.
    FFmpeg crop syntax: crop=out_w:out_h:x:y
    """
    if not crop_str:
        return ""
    parts = crop_str.split()
    if len(parts) == 4:
        left, right, top, bottom = map(int, parts)
        return f"crop=iw-{left}-{right}:ih-{top}-{bottom}:{left}:{top}"
    return ""


def resolve_subsegments(clip, total_duration_sec: float):
    """
    Returns a list of active subsegment tuples: (start_sec, end_sec, title)
    """
    segments = []
    if clip.subchapters:
        for i, sub in enumerate(clip.subchapters):
            s_sec = parse_timestamp_to_seconds(sub.start)
            if sub.end:
                e_sec = parse_timestamp_to_seconds(sub.end)
            elif i + 1 < len(clip.subchapters):
                e_sec = parse_timestamp_to_seconds(clip.subchapters[i + 1].start)
            else:
                e_sec = parse_timestamp_to_seconds(clip.end) if clip.end else total_duration_sec
            segments.append((s_sec, e_sec, sub.title))
    else:
        s_sec = parse_timestamp_to_seconds(clip.start) if clip.start else 0.0
        e_sec = parse_timestamp_to_seconds(clip.end) if clip.end else total_duration_sec
        segments.append((s_sec, e_sec, clip.title))
    return segments


def has_gaps(segments) -> bool:
    """
    Check if there are gaps between segments (threshold = 0.001s / 1ms).
    """
    if len(segments) <= 1:
        return False
    for i in range(len(segments) - 1):
        gap = segments[i + 1][0] - segments[i][1]
        if gap > 0.001:
            return True
    return False


def generate_concat_ffmetadata(clip, segments, is_test: bool = False) -> str:
    """
    Generates FFmetadata text format where subchapter markers are shifted to map
    to the output timeline. In test mode, each segment is allocated exactly 10 seconds.
    """
    lines = [";FFMETADATA1", f"title={clip.title}"]
    if clip.date:
        lines.append(f"date={clip.date}")

    current_timeline_ms = 0

    for s_sec, e_sec, sub_title in segments:
        if is_test:
            duration_sec = min(10.0, max(0.1, e_sec - s_sec))
        else:
            duration_sec = e_sec - s_sec

        duration_ms = int(duration_sec * 1000)
        start_ms = current_timeline_ms
        end_ms = current_timeline_ms + duration_ms

        lines.extend([
            "[CHAPTER]",
            "TIMEBASE=1/1000",
            f"START={start_ms}",
            f"END={end_ms}",
            f"title={sub_title}"
        ])

        current_timeline_ms = end_ms

    return "\n".join(lines) + "\n"

def convert_ffmetadata_to_vtt(meta_path: str, vtt_path: str) -> None:
    """Parses a ;FFMETADATA1 text file and writes a co-located WebVTT file."""
    if not os.path.exists(meta_path):
        return

    chapters = []
    start, end, title = None, None, ""

    with open(meta_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("START="):
                start = int(line.split("=")[1]) / 1000.0
            elif line.startswith("END="):
                end = int(line.split("=")[1]) / 1000.0
            elif line.startswith("title="):
                title = line.split("=", 1)[1]
            elif line == "[CHAPTER]":
                if start is not None and end is not None:
                    chapters.append((start, end, title or "Chapter"))
                start, end, title = None, None, ""

    if start is not None and end is not None:
        chapters.append((start, end, title or "Chapter"))

    def fmt_time(s: float) -> str:
        h = int(s // 3600)
        m = int((s % 3600) // 60)
        sec = s % 60
        return f"{h:02d}:{m:02d}:{sec:06.3f}"

    vtt_lines = ["WEBVTT\n"]
    for idx, (st, en, ti) in enumerate(chapters, 1):
        vtt_lines.append(f"{idx}\n{fmt_time(st)} --> {fmt_time(en)}\n{ti}\n")

    with open(vtt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(vtt_lines))

def build_clip_pipeline(
    mkv_path: Path,
    output_mp4: Path,
    meta_file_path: Path,
    vtt_file_path: Path,
    segments: list,
    vf_base: str,
    is_gapped: bool,
    do_test: bool,
    clip_id: str,
) -> dict:
    """SINGLE SOURCE OF TRUTH: Builds the exact Stage 1 and Stage 2 command lists."""
    tmp_mkv_path = f"/tmp/stage1_{clip_id}.mkv"

    # --- Stage 1: Decode & Filter -> Lossless MKV ---
    cmd_stage1 = [
        "ffmpeg", "-nostdin", "-y", "-loglevel", "warning", "-fflags", "+genpts+discardcorrupt"
    ]
    for s_sec, e_sec, _ in segments:
        cmd_stage1.extend(["-ss", str(s_sec)])
        cmd_stage1.extend(["-to", str(min(e_sec, s_sec + 10.0) if do_test else e_sec)])
        cmd_stage1.extend(["-i", str(mkv_path)])

    if is_gapped or len(segments) > 1:
        filter_lines = []
        for idx in range(len(segments)):
            filter_lines.append(f"[{idx}:v]{vf_base}[v{idx}]")
            filter_lines.append(f"[{idx}:a]asetpts=PTS-STARTPTS,aresample=async=1000:min_hard_comp=0.100000[a{idx}]")
        concat_inputs = "".join(f"[v{idx}][a{idx}]" for idx in range(len(segments)))
        filter_lines.append(f"{concat_inputs}concat=n={len(segments)}:v=1:a=1[outv][outa]")

        cmd_stage1.extend(["-filter_complex", ";".join(filter_lines), "-map", "[outv]", "-map", "[outa]"])
    else:
        cmd_stage1.extend(["-vf", vf_base, "-af", "asetpts=PTS-STARTPTS,aresample=async=1000:min_hard_comp=0.100000"])

    cmd_stage1.extend(["-c:v", "utvideo", "-c:a", "pcm_s16le", tmp_mkv_path])

    # --- Stage 2: Lossless MKV -> Delivery MP4 with Dual Chapters ---
    cmd_stage2 = [
        "ffmpeg", "-nostdin", "-y", "-loglevel", "warning",
        "-analyzeduration", "10M", "-probesize", "10M",
        "-channel_layout", "stereo", "-i", tmp_mkv_path,
        "-f", "ffmetadata", "-i", str(meta_file_path),
        "-i", str(vtt_file_path),
        "-map", "0:v:0", "-map", "0:a:0", "-map", "2:s:0",
        "-map_metadata", "1", "-map_chapters", "1",
        "-movflags", "+faststart",
        "-c:v", "libx264", "-crf", "22", "-preset", "slow",
        "-force_key_frames", "expr:eq(n,0)", "-g", "60",
        "-pix_fmt", "yuv420p", "-tag:v", "avc1",
        "-color_primaries", "smpte170m", "-color_trc", "smpte170m", "-colorspace", "smpte170m",
        "-c:a", "aac", "-b:a", "192k",
        "-c:s", "mov_text", "-shortest",
        str(output_mp4)
    ]

    return {
        "tmp_mkv": tmp_mkv_path,
        "stage1": cmd_stage1,
        "stage2": cmd_stage2,
    }
    
def clean_directory(dir_path: Path, do_uncropped: bool = False, do_cropped: bool = False, frames_mode: bool = False, test_mode: bool = False):
    """Targeted removal of PNG snapshots, test MP4s, and log files based on run mode."""
    if not dir_path.exists():
        return
    for item in dir_path.iterdir():
        if not item.is_file():
            continue
        
        name = item.name.lower()

        # Clear previous test clips when running test mode
        if test_mode and name.endswith("_test.mp4"):
            item.unlink()

        # Clear main log file when running standard full encode
        if not frames_mode and not test_mode and name.endswith(".log"):
            item.unlink()

        # Clear previous 'a.png' files
        if do_uncropped and name.endswith("a.png"):
            item.unlink()

        # Clear previous 'b.png' files
        if do_cropped and name.endswith("b.png"):
            item.unlink()

def format_pipeline_to_bash(stage1_cmd: list[str], stage2_cmd: list[str], tmp_mkv_path: str) -> str:
    """Formats pre-built Stage 1 and Stage 2 command lists into a clean multiline bash script using variables."""
    lines = []

    # Extract paths directly from the structured command arrays
    i_idx = stage1_cmd.index("-i")
    input_mkv = stage1_cmd[i_idx + 1]

    i_indices = [idx for idx, arg in enumerate(stage2_cmd) if arg == "-i"]
    meta_txt = stage2_cmd[i_indices[1] + 1]
    chapters_vtt = stage2_cmd[i_indices[2] + 1]
    output_mp4 = stage2_cmd[-1]

    # 1. Path Declarations
    lines.append(f'INPUT_MKV={shlex.quote(str(input_mkv))}')
    lines.append(f'META_TXT={shlex.quote(str(meta_txt))}')
    lines.append(f'CHAPTERS_VTT={shlex.quote(str(chapters_vtt))}')
    lines.append(f'TMP_MKV={shlex.quote(str(tmp_mkv_path))}')
    lines.append(f'OUTPUT_MP4={shlex.quote(str(output_mp4))}')
    lines.append('trap \'rm -f "$TMP_MKV"\' EXIT\n')

    # 2. Format Stage 1
    s1_quoted = [shlex.quote(arg) for arg in stage1_cmd]
    lines.append("ffmpeg -nostdin -y -loglevel warning -fflags +genpts+discardcorrupt \\")
    
    i = 7
    while i < len(s1_quoted):
        if s1_quoted[i] == "-ss":
            s_val, to_val = s1_quoted[i + 1], s1_quoted[i + 3]
            lines.append(f"  -ss {s_val} -to {to_val} -i \"$INPUT_MKV\" \\")
            i += 6
        elif s1_quoted[i] == "-filter_complex":
            # Extract raw filter string (unquoted) from stage1_cmd array
            fc_raw = stage1_cmd[i + 1]
            filter_clauses = [clause.strip() for clause in fc_raw.split(";") if clause.strip()]
            
            lines.append('  -filter_complex "\\')
            for idx, clause in enumerate(filter_clauses):
                is_last = (idx == len(filter_clauses) - 1)
                semi = "" if is_last else ";"
                closing_quote = '" \\' if is_last else ' \\'
                lines.append(f"    {clause}{semi}{closing_quote}")
            
            # Skip past -filter_complex <str> and process mapping/encoding args
            i += 2
            rest_args = " ".join(s1_quoted[i:-1])
            lines.append(f"  {rest_args} \"$TMP_MKV\"")
            break
        else:
            # Simple -vf / -af path
            rest_args = " ".join(s1_quoted[i:-1])
            lines.append(f"  {rest_args} \"$TMP_MKV\"")
            break

    lines.append("")  # Blank spacer

    # 3. Format Stage 2
    lines.append("ffmpeg -nostdin -y -loglevel warning -analyzeduration 10M -probesize 10M \\")
    lines.append('  -channel_layout stereo -i "$TMP_MKV" \\')
    lines.append('  -f ffmetadata -i "$META_TXT" \\')
    lines.append('  -i "$CHAPTERS_VTT" \\')
    lines.append("  -map 0:v:0 -map 0:a:0 -map 2:s:0 -map_metadata 1 -map_chapters 1 \\")
    lines.append("  -movflags +faststart \\")
    lines.append("  -c:v libx264 -crf 22 -preset slow -force_key_frames 'expr:eq(n,0)' -g 60 \\")
    lines.append("  -pix_fmt yuv420p -tag:v avc1 -color_primaries smpte170m -color_trc smpte170m -colorspace smpte170m \\")
    lines.append("  -c:a aac -b:a 192k -c:s mov_text -shortest \\")
    lines.append('  "$OUTPUT_MP4"')

    return "\n".join(lines)
  
from dataclasses import dataclass

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
        print("Usage: ./scripts/03_make_clips.py [--clean | --test | --uncropped-frames | --cropped-frames | --frames-only | --dry-run | --debug-scripts] <TAPE_NAME>")
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
    segments: list,
    mkv_path: Path,
    tape_log_dir: Path,
    ffmpeg_crop: str,
    cfg: CLIConfig,
    log_file,
    single_script_lines: list[str],
) -> None:
    """Captures uncropped ('a') and cropped ('b') diagnostic frame snapshots."""
    safe_title = "".join(c if c.isalnum() or c in (" ", "-", "_") else "" for c in clip.title).strip().replace(" ", "_")
    clip_prefix = f"{tape_log_dir.name.replace('-log', '')}_{clip.idx}_{safe_title}"

    for sub_idx, (s_sec, e_sec, _) in enumerate(segments, start=1):
        mid_sec = s_sec + ((e_sec - s_sec) / 2.0)
        end_sec = max(s_sec, e_sec - 0.1)
        timestamps = [("1", s_sec), ("2", mid_sec), ("3", end_sec)]

        for pos_code, t_sec in timestamps:
            snapshot_prefix = f"{clip_prefix}_{sub_idx}-{pos_code}"

            if cfg.do_uncropped:
                out_png = tape_log_dir / f"{snapshot_prefix}a.png"
                cmd = [
                    "ffmpeg", "-y", "-loglevel", "warning",
                    "-ss", str(t_sec), "-i", str(mkv_path),
                    "-vf", "format=rgb24", "-vframes", "1", "-update", "1", str(out_png)
                ]
                if cfg.do_dry_run or cfg.do_split_scripts:
                    single_script_lines.append(" ".join(shlex.quote(c) for c in cmd) + "\n")
                else:
                    subprocess.run(cmd, stdout=log_file, stderr=log_file, check=True)

            if cfg.do_cropped and ffmpeg_crop:
                out_png = tape_log_dir / f"{snapshot_prefix}b.png"
                cmd = [
                    "ffmpeg", "-y", "-loglevel", "warning",
                    "-ss", str(t_sec), "-i", str(mkv_path),
                    "-vf", f"{ffmpeg_crop},format=rgb24", "-vframes", "1", "-update", "1", str(out_png)
                ]
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
    """Dispatches the pre-built pipeline to script generation or direct execution."""
    multiline_cmd = format_pipeline_to_bash(pipe["stage1"], pipe["stage2"], pipe["tmp_mkv"])

    if cfg.do_split_scripts:
        print(f"[{clip.idx}] Writing multi-line debug script for: {clip.title}...", end="", flush=True)
        script_filename = f"encode_{clip.idx}_{safe_title}.sh"
        sub_script_path = tape_log_dir / script_filename

        script_body = [
            "#!/usr/bin/env bash",
            "set -e\n",
            f"# Clip [{clip.idx}]: {clip.title}",
            multiline_cmd + "\n"
        ]
        sub_script_path.write_text("\n".join(script_body), encoding="utf-8")
        sub_script_path.chmod(0o755)
        run_all_lines.append(f"./{script_filename}")

    elif cfg.do_dry_run:
        single_script_lines.append(f"# --- Clip [{clip.idx}]: {clip.title} ---")
        single_script_lines.append(multiline_cmd + "\n")

    else:
        print(f"[{clip.idx}] Encoding {'TEST ' if cfg.do_test else ''}clip: {clip.title}...", end="", flush=True)
        log_file.write(f"\n--- Encoding Clip [{clip.idx}]: {clip.title} ---\n")
        log_file.flush()

        subprocess.run(pipe["stage1"], stdout=log_file, stderr=log_file, check=True)
        subprocess.run(pipe["stage2"], stdout=log_file, stderr=log_file, check=True)

def main():
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

    spec_path = SPECS_DIR / f"{cfg.tape_name}.txt"
    mkv_path = ARCHIVE_DIR / f"{cfg.tape_name}.mkv"

    if not spec_path.exists() or not mkv_path.exists():
        print("Error: Spec file or archival MKV missing.")
        sys.exit(1)

    data = read_tape_spec(spec_path.read_text())
    total_duration_str = get_video_duration(str(mkv_path))
    data.resolve_missing_end_times(total_duration_str)
    total_duration_sec = parse_timestamp_to_seconds(total_duration_str)

    clean_directory(tape_log_dir, cfg.do_uncropped, cfg.do_cropped, cfg.frames_mode, cfg.do_test)

    log_file_path = tape_log_dir / "ffmpeg_encode.log"
    tape_start_time = time.perf_counter()
    single_script_lines = ["#!/usr/bin/env bash", "set -e\n"]
    run_all_lines = ["#!/usr/bin/env bash", "set -e\n"]

    with open(log_file_path, "a", encoding="utf-8") as log_file:
        for clip in data.clips:
            clip_start_time = time.perf_counter()
            segments = resolve_subsegments(clip, total_duration_sec)
            safe_title = "".join(c if c.isalnum() or c in (" ", "-", "_") else "" for c in clip.title).strip().replace(" ", "_")
            
            crop_val = clip.crop if clip.crop else data.global_crop
            ffmpeg_crop = build_crop_filter(crop_val)

            # 1. Handle Frame Capture Mode
            if cfg.frames_mode:
                print(f"[{clip.idx}] Capturing diagnostic frames for: {clip.title}...", end="", flush=True)
                capture_diagnostic_frames(clip, segments, mkv_path, tape_log_dir, ffmpeg_crop, cfg, log_file, single_script_lines)
                print(f" Done ({format_elapsed_time(time.perf_counter() - clip_start_time)})")
                continue

            # 2. Sidecar Asset Setup
            output_mp4 = (tape_log_dir / f"{cfg.tape_name}_{clip.idx}_{safe_title}_test.mp4") if cfg.do_test else (tape_output_dir / f"{cfg.tape_name}_{clip.idx}_{safe_title}.mp4")
            meta_file_path = tape_log_dir / f"meta_{clip.idx}.txt"
            vtt_file_path = tape_log_dir / f"meta_{clip.idx}.vtt"

            meta_file_path.write_text(generate_concat_ffmetadata(clip, segments, is_test=cfg.do_test), encoding="utf-8")
            convert_ffmetadata_to_vtt(str(meta_file_path), str(vtt_file_path))

            # 3. Construct Single Source of Truth Commands
            vf_base = "bwdif=mode=send_field:deint=all" + (f",{ffmpeg_crop}" if ffmpeg_crop else "") + ",setpts=PTS-STARTPTS"
            pipe = build_clip_pipeline(
                mkv_path=mkv_path, output_mp4=output_mp4,
                meta_file_path=meta_file_path, vtt_file_path=vtt_file_path,
                segments=segments, vf_base=vf_base, is_gapped=has_gaps(segments),
                do_test=cfg.do_test, clip_id=str(clip.idx)
            )

            # 4. Dispatch Execution Path
            try:
                process_clip_pipeline(clip, pipe, cfg, tape_log_dir, safe_title, log_file, run_all_lines, single_script_lines)
                print(f" Done ({format_elapsed_time(time.perf_counter() - clip_start_time)})")
            finally:
                if os.path.exists(pipe["tmp_mkv"]):
                    os.remove(pipe["tmp_mkv"])

    # Final batch script writing
    if cfg.do_split_scripts:
        master = tape_log_dir / "run_all.sh"
        master.write_text("\n".join(run_all_lines) + "\n", encoding="utf-8")
        master.chmod(0o755)
    elif cfg.do_dry_run:
        script_out = tape_log_dir / "run_encode.sh"
        script_out.write_text("\n".join(single_script_lines), encoding="utf-8")
        script_out.chmod(0o755)

    print(f"\nAll operations complete for '{cfg.tape_name}' in {format_elapsed_time(time.perf_counter() - tape_start_time)}!")

if __name__ == "__main__":
    main()
