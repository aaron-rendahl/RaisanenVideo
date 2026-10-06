"""src/ffmpeg_utils.py"""

import os
import shlex
import shutil
from pathlib import Path
from typing import List, Tuple
from models import Clip

def build_crop_filter(crop_str: str) -> str:
    """Translates 'Left Right Top Bottom' crop boundaries to FFmpeg crop filter strings."""
    if not crop_str:
        return ""
    try:
        delimiter = "|" if "|" in crop_str else " "
        parts = [int(p.strip()) for p in crop_str.split(delimiter) if p.strip()]
        if len(parts) == 4:
            left, right, top, bottom = parts
            return f"crop=iw-{left+right}:ih-{top+bottom}:{left}:{top}"
    except ValueError:
        pass
    return ""



def generate_concat_ffmetadata(
    clip: Clip, segments: List[Tuple[float, float, str]], meta_path: str, is_test: bool = False
) -> None:
    """Generates FFmpeg concat metadata format file for chapter marker preservation."""
    lines = [";FFMETADATA1"]
    current_time = 0.0

    for start_sec, end_sec, title in segments:
        duration = 10.0 if is_test else max(0.1, end_sec - start_sec)
        start_ms = int(current_time * 1000)
        end_ms = int((current_time + duration) * 1000)

        lines.extend(
            [
                "[CHAPTER]",
                "TIMEBASE=1/1000",
                f"START={start_ms}",
                f"END={end_ms}",
                f"title={title}",
            ]
        )
        current_time += duration

    Path(meta_path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def convert_ffmetadata_to_vtt(meta_path: str, vtt_path: str) -> None:
    """Converts FFmpeg metadata chapters to WebVTT track format for HTML5/macOS players."""
    meta_text = Path(meta_path).read_text(encoding="utf-8")
    vtt_lines = ["WEBVTT", ""]

    chapter_title = ""
    start_ms = 0
    end_ms = 0

    def format_vtt_timestamp(ms: int) -> str:
        s, ms_rem = divmod(ms, 1000)
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}.{ms_rem:03d}"

    for line in meta_text.splitlines():
        line = line.strip()
        if line == "[CHAPTER]":
            if chapter_title:
                vtt_lines.append(
                    f"{format_vtt_timestamp(start_ms)} --> {format_vtt_timestamp(end_ms)}"
                )
                vtt_lines.append(chapter_title)
                vtt_lines.append("")
            chapter_title = ""
        elif line.startswith("START="):
            start_ms = int(line.split("=")[1])
        elif line.startswith("END="):
            end_ms = int(line.split("=")[1])
        elif line.startswith("title="):
            chapter_title = line.split("=", 1)[1]

    if chapter_title:
        vtt_lines.append(
            f"{format_vtt_timestamp(start_ms)} --> {format_vtt_timestamp(end_ms)}"
        )
        vtt_lines.append(chapter_title)
        vtt_lines.append("")

    Path(vtt_path).write_text("\n".join(vtt_lines) + "\n", encoding="utf-8")




def build_clip_pipeline(
    mkv_path: Path,
    output_mp4: Path,
    meta_file_path: Path,
    vtt_file_path: Path,
    segments: List[Tuple[float, float, str]],
    vf_base: str,
    is_gapped: bool,
    do_test: bool,
    clip_id: str,
) -> dict:
    """Constructs the two-stage FFmpeg pipeline arguments and temporary MKV path."""
    tmp_mkv = f"/tmp/stage1_{clip_id}_{mkv_path.stem}.mkv"

    # Stage 1: Fast intermediate extraction to UtVideo/PCM
    stage1_cmd = ["ffmpeg", "-y", "-loglevel", "warning", "-i", str(mkv_path)]

    if is_gapped or len(segments) > 1:
        filter_complex_parts = []
        concat_inputs = []

        for idx, (s_sec, e_sec, _) in enumerate(segments):
            dur = 10.0 if do_test else (e_sec - s_sec)

            filter_complex_parts.append(
                f"[0:v]trim=start={s_sec}:duration={dur},{vf_base}[v{idx}];\n"
                f"[0:a]atrim=start={s_sec}:duration={dur},asetpts=PTS-STARTPTS[a{idx}]"
            )
            concat_inputs.append(f"[v{idx}][a{idx}]")

        # Multi-line filter complex: join segments with ';\n', add ';', then pads + concat filter
        fc_str = (
            ";\n".join(filter_complex_parts)
            + ";\n"
            + "".join(concat_inputs)
            + f"concat=n={len(segments)}:v=1:a=1[outv][outa]"
        )

        stage1_cmd.extend(
            [
                "-filter_complex", fc_str,
                "-map", "[outv]",
                "-map", "[outa]",
            ]
        )
    else:
        s_sec, e_sec, _ = segments[0]
        dur = 10.0 if do_test else (e_sec - s_sec)
        stage1_cmd.extend(
            [
                "-ss", str(s_sec),
                "-t", str(dur),
                "-vf", vf_base,  # Fixed typo: f_base -> vf_base
            ]
        )

    stage1_cmd.extend(
        [
            "-c:v", "utvideo",
            "-c:a", "pcm_s16le",
            "-ch_layout", "stereo",
            tmp_mkv,
        ]
    )

    # Stage 2: Encode web-ready H.264/AAC MP4 with dual chapter sidecars
    stage2_cmd = [
        "ffmpeg", "-y", "-loglevel", "warning",
        "-i", tmp_mkv,
        "-i", str(meta_file_path),
        "-i", str(vtt_file_path),
        "-map_metadata", "1",
        "-map", "0:v",
        "-map", "0:a",
        "-map", "2:s",
        "-c:v", "libx264",
        "-crf", "18",
        "-preset", "slow",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-c:s", "mov_text",
        "-metadata:s:0", "language=eng",
        "-disposition:s:0", "default",
        "-movflags", "+faststart",
        str(output_mp4),
    ]

    return {
        "stage1": stage1_cmd,
        "stage2": stage2_cmd,
        "tmp_mkv": tmp_mkv,
    }

def format_cmd_tokens(cmd: list) -> str:
    """Groups FFmpeg flags with their arguments into readable multi-line shell commands."""
    lines = []
    i = 0
    current_line = []

    while i < len(cmd):
        token = cmd[i]
        quoted = shlex.quote(token)

        # Start a new line on major options or trailing positional output file
        if token.startswith("-") or i == len(cmd) - 1:
            if current_line:
                lines.append("  " + " ".join(current_line))
                current_line = []
            current_line.append(quoted)

            # Keep short flag-value pairs together (e.g. -c:v libx264, -i file.mkv)
            if i + 1 < len(cmd) and not cmd[i + 1].startswith("-"):
                current_line.append(shlex.quote(cmd[i + 1]))
                i += 1
        else:
            current_line.append(quoted)
        i += 1

    if current_line:
        lines.append("  " + " ".join(current_line))

    # First token is executable name
    if lines:
        lines[0] = lines[0].strip()

    return " \\\n".join(lines)


def format_pipeline_to_bash(
    stage1: list, stage2: list, tmp_mkv: str
) -> str:
    """Formats two-stage FFmpeg pipeline into clean multiline bash script syntax."""
    s1_str = format_cmd_tokens(stage1)
    s2_str = format_cmd_tokens(stage2)
    clean_tmp = shlex.quote(tmp_mkv)

    return f"{s1_str}\n\n{s2_str}\n\nrm -f {clean_tmp}"

def clean_directory(
    target_dir: Path,
    do_uncropped: bool = False,
    do_cropped: bool = False,
    frames_mode: bool = False,
    do_test: bool = False,
) -> None:
    """Selectively cleans or resets output log directories depending on execution mode."""
    if frames_mode:
        if do_uncropped:
            for p in target_dir.glob("*a.png"):
                p.unlink()
        if do_cropped:
            for p in target_dir.glob("*b.png"):
                p.unlink()
    elif do_test:
        for p in target_dir.glob("*_test.mp4"):
            p.unlink()
