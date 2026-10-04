#!/usr/bin/env python3
"""
tape_utils.py - Helper utilities for VHS tape spec parsing, timestamp math,
and sidecar metadata generation.
"""

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ClipSpec:
    idx: str
    title: str
    start: str
    end: str
    crop: str = ""
    subchapters: list = None

    def __post_init__(self):
        if self.subchapters is None:
            self.subchapters = []


@dataclass
class TapeSpec:
    global_crop: str = ""
    clips: list = None

    def __post_init__(self):
        if self.clips is None:
            self.clips = []

    def resolve_missing_end_times(self, total_duration_str: str) -> None:
        """Resolves empty end timestamps for clips using the start time of the subsequent clip or total duration."""
        for i, clip in enumerate(self.clips):
            if not clip.end:
                if i + 1 < len(self.clips):
                    clip.end = self.clips[i + 1].start
                else:
                    clip.end = total_duration_str


def read_tape_spec(spec_text: str) -> TapeSpec:
    """Parses a tape specification text file into a TapeSpec object."""
    tape = TapeSpec()
    current_clip = None

    for line in spec_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("GLOBAL_CROP="):
            tape.global_crop = line.split("=", 1)[1].strip()
            continue

        parts = [p.strip() for p in line.split("|")]
        if len(parts) >= 3:
            if "." in parts[0]:
                if current_clip:
                    sub_title = parts[1]
                    s_time = parts[2]
                    e_time = parts[3] if len(parts) > 3 else ""
                    current_clip.subchapters.append((s_time, e_time, sub_title))
            else:
                idx = parts[0]
                title = parts[1]
                start = parts[2]
                end = parts[3] if len(parts) > 3 else ""
                crop = parts[4] if len(parts) > 4 else ""
                current_clip = ClipSpec(
                    idx=idx, title=title, start=start, end=end, crop=crop
                )
                tape.clips.append(current_clip)

    return tape


def parse_timestamp_to_seconds(ts: str) -> float:
    """Converts HH:MM:SS.mmm or MM:SS.mmm string to total seconds."""
    if not ts:
        return 0.0
    parts = ts.split(":")
    if len(parts) == 3:
        return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    elif len(parts) == 2:
        return float(parts[0]) * 60 + float(parts[1])
    return float(parts[0])


def get_video_duration(mkv_path: str) -> str:
    """Queries ffprobe for the exact duration of the archival source video."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        mkv_path,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    sec = float(res.stdout.strip())
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def resolve_subsegments(
    clip: ClipSpec, total_duration_sec: float
) -> list[tuple[float, float, str]]:
    """Resolves clip timestamps and subchapters into a list of (start_sec, end_sec, title) tuples."""
    segments = []
    if clip.subchapters:
        for idx, (s_str, e_str, sub_title) in enumerate(clip.subchapters):
            s_sec = parse_timestamp_to_seconds(s_str)
            if e_str:
                e_sec = parse_timestamp_to_seconds(e_str)
            elif idx + 1 < len(clip.subchapters):
                e_sec = parse_timestamp_to_seconds(
                    clip.subchapters[idx + 1][0]
                )
            else:
                e_sec = (
                    parse_timestamp_to_seconds(clip.end)
                    if clip.end
                    else total_duration_sec
                )
            segments.append((s_sec, e_sec, sub_title))
    else:
        s_sec = parse_timestamp_to_seconds(clip.start)
        e_sec = (
            parse_timestamp_to_seconds(clip.end)
            if clip.end
            else total_duration_sec
        )
        segments.append((s_sec, e_sec, clip.title))
    return segments


def has_gaps(segments: list[tuple[float, float, str]]) -> bool:
    """Checks if there are time gaps between consecutive subchapter subsegments."""
    for i in range(len(segments) - 1):
        if abs(segments[i][1] - segments[i + 1][0]) > 0.05:
            return True
    return False


def build_crop_filter(crop_str: str) -> str:
    """Converts 'Left Right Top Bottom' pixels string into FFmpeg crop filter string."""
    if not crop_str or crop_str.strip() == "0 0 0 0":
        return ""
    parts = [int(p) for p in crop_str.split()]
    if len(parts) == 4:
        left, right, top, bottom = parts
        return f"crop=iw-{left + right}:ih-{top + bottom}:{left}:{top}"
    return ""


def generate_concat_ffmetadata(
    clip: ClipSpec,
    segments: list[tuple[float, float, str]],
    is_test: bool = False,
) -> str:
    """Generates ;FFMETADATA1 text content for ISO chapters atom."""
    lines = [";FFMETADATA1", f"title={clip.title}", ""]
    current_ms = 0

    for s_sec, e_sec, sub_title in segments:
        dur_ms = int(
            (min(e_sec - s_sec, 10.0) if is_test else e_sec - s_sec) * 1000
        )
        end_ms = current_ms + dur_ms
        lines.append("[CHAPTER]")
        lines.append("TIMEBASE=1/1000")
        lines.append(f"START={current_ms}")
        lines.append(f"END={end_ms}")
        lines.append(f"title={sub_title}")
        lines.append("")
        current_ms = end_ms

    return "\n".join(lines)


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


def clean_directory(
    tape_log_dir: Path,
    do_uncropped: bool,
    do_cropped: bool,
    frames_mode: bool,
    do_test: bool,
) -> None:
    """Cleans up target PNGs or test clips prior to execution."""
    if not tape_log_dir.exists():
        return
    for item in tape_log_dir.iterdir():
        if frames_mode:
            if do_uncropped and item.name.endswith("a.png"):
                item.unlink()
            if do_cropped and item.name.endswith("b.png"):
                item.unlink()
        elif do_test and item.name.endswith("_test.mp4"):
            item.unlink()


def format_elapsed_time(seconds: float) -> str:
    """Formats floating point elapsed seconds into human readable time string."""
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{int(h)}h {int(m)}m {s:.1f}s"
    elif m > 0:
        return f"{int(m)}m {s:.1f}s"
    return f"{s:.2f}s"


def build_clip_pipeline(
    mkv_path: Path, output_mp4: Path, meta_file_path: Path, vtt_file_path: Path,
    segments: list, vf_base: str, is_gapped: bool, do_test: bool, clip_id: str
) -> dict:
    """SINGLE SOURCE OF TRUTH: Builds exact Stage 1 and Stage 2 command lists."""
    tmp_mkv_path = f"/tmp/stage1_{clip_id}.mkv"

    # Stage 1: Decode & Filter -> Lossless MKV
    cmd_stage1 = [
        "ffmpeg", "-nostdin", "-y", "-loglevel", "warning",
        "-fflags", "+genpts+discardcorrupt"
    ]
    for s_sec, e_sec, _ in segments:
        e_target = min(e_sec, s_sec + 10.0) if do_test else e_sec
        cmd_stage1.extend(["-ss", str(s_sec), "-to", str(e_target), "-i", str(mkv_path)])

    if is_gapped or len(segments) > 1:
        filter_lines = []
        for idx in range(len(segments)):
            filter_lines.append(f"[{idx}:v]{vf_base}[v{idx}]")
            filter_lines.append(f"[{idx}:a]asetpts=PTS-STARTPTS,aresample=async=1000:min_hard_comp=0.100000[a{idx}]")
        concat_inputs = "".join(f"[v{idx}][a{idx}]" for idx in range(len(segments)))
        filter_lines.append(f"{concat_inputs}concat=n={len(segments)}:v=1:a=1[outv][outa]")

        cmd_stage1.extend([
            "-filter_complex", ";".join(filter_lines),
            "-map", "[outv]", "-map", "[outa]"
        ])
    else:
        cmd_stage1.extend([
            "-vf", vf_base,
            "-af", "asetpts=PTS-STARTPTS,aresample=async=1000:min_hard_comp=0.100000"
        ])

    cmd_stage1.extend(["-c:v", "utvideo", "-c:a", "pcm_s16le", tmp_mkv_path])

    # Stage 2: Lossless MKV -> Final MP4 + Dual Chapters
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

def format_pipeline_to_bash(
    stage1_cmd: list[str], stage2_cmd: list[str], tmp_mkv_path: str
) -> str:
    """Formats pre-built command lists into a clean multiline bash script using variables."""
    lines = []

    i_idx = stage1_cmd.index("-i")
    input_mkv = stage1_cmd[i_idx + 1]

    i_indices = [idx for idx, arg in enumerate(stage2_cmd) if arg == "-i"]
    meta_txt = stage2_cmd[i_indices[1] + 1]
    chapters_vtt = stage2_cmd[i_indices[2] + 1]
    output_mp4 = stage2_cmd[-1]

    lines.append(f"INPUT_MKV={shlex.quote(str(input_mkv))}")
    lines.append(f"META_TXT={shlex.quote(str(meta_txt))}")
    lines.append(f"CHAPTERS_VTT={shlex.quote(str(chapters_vtt))}")
    lines.append(f"TMP_MKV={shlex.quote(str(tmp_mkv_path))}")
    lines.append(f"OUTPUT_MP4={shlex.quote(str(output_mp4))}")
    lines.append('trap \'rm -f "$TMP_MKV"\' EXIT\n')

    s1_quoted = [shlex.quote(arg) for arg in stage1_cmd]
    lines.append(
        "ffmpeg -nostdin -y -loglevel warning -fflags +genpts+discardcorrupt \\"
    )

    i = 7
    while i < len(s1_quoted):
        if s1_quoted[i] == "-ss":
            s_val, to_val = s1_quoted[i + 1], s1_quoted[i + 3]
            lines.append(f'  -ss {s_val} -to {to_val} -i "$INPUT_MKV" \\')
            i += 6
        elif s1_quoted[i] == "-filter_complex":
            fc_raw = stage1_cmd[i + 1]
            filter_clauses = [
                clause.strip() for clause in fc_raw.split(";") if clause.strip()
            ]

            lines.append('  -filter_complex "\\')
            for idx, clause in enumerate(filter_clauses):
                is_last = idx == len(filter_clauses) - 1
                semi = "" if is_last else ";"
                closing_quote = '" \\' if is_last else " \\"
                lines.append(f"    {clause}{semi}{closing_quote}")

            i += 2
            rest_args = " ".join(s1_quoted[i:-1])
            lines.append(f'  {rest_args} "$TMP_MKV"')
            break
        else:
            rest_args = " ".join(s1_quoted[i:-1])
            lines.append(f'  {rest_args} "$TMP_MKV"')
            break

    lines.append("")

    lines.append(
        "ffmpeg -nostdin -y -loglevel warning -analyzeduration 10M -probesize"
        " 10M \\"
    )
    lines.append('  -channel_layout stereo -i "$TMP_MKV" \\')
    lines.append('  -f ffmetadata -i "$META_TXT" \\')
    lines.append('  -i "$CHAPTERS_VTT" \\')
    lines.append(
        "  -map 0:v:0 -map 0:a:0 -map 2:s:0 -map_metadata 1 -map_chapters 1 \\"
    )
    lines.append("  -movflags +faststart \\")
    lines.append(
        "  -c:v libx264 -crf 22 -preset slow -force_key_frames 'expr:eq(n,0)' -g"
        " 60 \\"
    )
    lines.append(
        "  -pix_fmt yuv420p -tag:v avc1 -color_primaries smpte170m -color_trc"
        " smpte170m -colorspace smpte170m \\"
    )
    lines.append("  -c:a aac -b:a 192k -c:s mov_text -shortest \\")
    lines.append('  "$OUTPUT_MP4"')

    return "\n".join(lines)
