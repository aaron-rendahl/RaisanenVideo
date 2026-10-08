"""src/ffmpeg_utils.py"""

import os
import shlex
import shutil
from pathlib import Path
from typing import List, Tuple
from models import Clip

from video_utils import has_audio_stream

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
        start_ms = int(round(current_time * 1000))
        end_ms = int(round((current_time + duration) * 1000))

        clean_title = (
            str(title)
            .replace("\\", "\\\\")
            .replace("=", "\\=")
            .replace(";", "\\;")
            .replace("#", "\\#")
            .replace("\n", "\\\n")
        )

        lines.extend(
            [
                "[CHAPTER]",
                "TIMEBASE=1/1000",
                f"START={start_ms}",
                f"END={end_ms}",
                f"title={clean_title}",
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
    """Constructs three-stage FFmpeg pipeline commands with parameter placeholders."""
    tmp_mkv = f"/tmp/stage1_{clip_id}_{mkv_path.stem}.mkv"
    mux_tmp = str(output_mp4.parent / f".tmp_{output_mp4.name}")
    has_audio = has_audio_stream(mkv_path)

    paths = {
        "SRC_MKV": str(mkv_path),
        "TMP_MKV": tmp_mkv,
        "META_TXT": str(meta_file_path),
        "VTT_SUB": str(vtt_file_path),
        "OUT_MP4": str(output_mp4),
        "MUX_MP4": mux_tmp,
    }

    # --- STAGE 1: Unchanged (Deinterlace, Trim, Concat -> UtVideo/PCM) ---
    stage1_cmd = ["ffmpeg", "-y", "-loglevel", "warning", "-i", "${SRC_MKV}"]

    if is_gapped or len(segments) > 1:
        filter_complex_parts = []
        concat_inputs = []

        for idx, (s_sec, e_sec, _) in enumerate(segments):
            dur = 10.0 if do_test else (e_sec - s_sec)

            if has_audio:
                audio_filter = f"[0:a]atrim=start={s_sec:.3f}:duration={dur:.3f},asetpts=PTS-STARTPTS[a{idx}]"
            else:
                audio_filter = f"anullsrc=channel_layout=stereo:sample_rate=48000,atrim=duration={dur:.3f},asetpts=PTS-STARTPTS[a{idx}]"

            filter_complex_parts.append(
                f"[0:v]trim=start={s_sec:.3f}:duration={dur:.3f},{vf_base}[v{idx}];\n"
                f"{audio_filter}"
            )
            concat_inputs.append(f"[v{idx}][a{idx}]")

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

        if has_audio:
            stage1_cmd.extend(
                [
                    "-ss", f"{s_sec:.3f}",
                    "-t", f"{dur:.3f}",
                    "-vf", vf_base,
                ]
            )
        else:
            fc_str = (
                f"[0:v]trim=start={s_sec:.3f}:duration={dur:.3f},{vf_base}[outv];\n"
                f"anullsrc=channel_layout=stereo:sample_rate=48000,atrim=duration={dur:.3f},asetpts=PTS-STARTPTS[outa]"
            )
            stage1_cmd.extend(
                [
                    "-filter_complex", fc_str,
                    "-map", "[outv]",
                    "-map", "[outa]",
                ]
            )

    stage1_cmd.extend(
        [
            "-map_chapters", "-1",
            "-c:v", "utvideo",
            "-c:a", "pcm_s16le",
            "${TMP_MKV}",
        ]
    )

    # --- STAGE 2: Video/Audio Encode Only (Heavy CPU Work -> RAW MP4) ---
    stage2_cmd = [
        "ffmpeg", "-y", "-loglevel", "warning",
        "-channel_layout", "stereo",
        "-i", "${TMP_MKV}",
        "-map", "0:v",
        "-map", "0:a",
        "-c:v", "libx264",
        "-crf", "18",
        "-preset", "slow",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "${OUT_MP4}",
    ]

    # --- STAGE 3: Fast Metadata & Subtitle Multiplexing (-c copy) ---
    stage3_cmd = [
        "ffmpeg", "-y", "-loglevel", "warning",
        "-i", "${OUT_MP4}",
        "-i", "${META_TXT}",
        "-i", "${VTT_SUB}",
        "-map", "0:v",
        "-map", "0:a",
        "-map", "2:s",
        "-map_metadata", "1",
        "-map_chapters", "1",
        "-c:v", "copy",
        "-c:a", "copy",
        "-c:s", "mov_text",
        "-metadata:s:0", "language=eng",
        "-disposition:s:0", "default",
        "-movflags", "+faststart",
        "${MUX_MP4}",
    ]

    return {
        "stage1": stage1_cmd,
        "stage2": stage2_cmd,
        "stage3": stage3_cmd,
        "paths": paths,
    }

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
