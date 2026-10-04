import os
import shutil
from pathlib import Path
from typing import List, Tuple
from models import ArchiveData, Clip, Subchapter


def parse_timestamp_to_seconds(ts: str) -> float:
    """Converts HH:MM:SS.mmm or HH:MM:SS to total float seconds."""
    if not ts:
        return 0.0
    parts = ts.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return float(h) * 3600 + float(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return float(m) * 60 + float(s)
    return float(ts)


def format_elapsed_time(seconds: float) -> str:
    """Formats float seconds into a clean display string."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    if h > 0:
        return f"{h}h {m}m {s:.1f}s"
    elif m > 0:
        return f"{m}m {s:.1f}s"
    return f"{s:.1f}s"


def build_crop_filter(crop_str: str) -> str:
    """Translates 'Top Bottom Left Right' crop boundaries to FFmpeg crop filter strings."""
    if not crop_str:
        return ""
    try:
        delimiter = "|" if "|" in crop_str else " "
        parts = [int(p.strip()) for p in crop_str.split(delimiter) if p.strip()]
        if len(parts) == 4:
            top, bottom, left, right = parts
            return f"crop=iw-{left+right}:ih-{top+bottom}:{left}:{top}"
    except ValueError:
        pass
    return ""


def resolve_subsegments(clip: Clip) -> List[Tuple[float, float, str]]:
    """Converts clip subchapters into (start_sec, end_sec, title) segment tuples."""
    segments = []
    if clip.subchapters:
        for sub in clip.subchapters:
            s_sec = parse_timestamp_to_seconds(sub.start)
            e_sec = parse_timestamp_to_seconds(sub.end)
            segments.append((s_sec, e_sec, sub.title))
    else:
        s_sec = parse_timestamp_to_seconds(clip.start)
        e_sec = parse_timestamp_to_seconds(clip.end)
        segments.append((s_sec, e_sec, clip.title))
    return segments


def has_gaps(segments: List[Tuple[float, float, str]]) -> bool:
    """Checks if there are non-contiguous gaps between segment boundaries."""
    for i in range(len(segments) - 1):
        if abs(segments[i][1] - segments[i + 1][0]) > 0.05:
            return True
    return False


def generate_concat_ffmetadata(
    segments: List[Tuple[float, float, str]], meta_path: str
) -> None:
    """Generates FFmpeg concat metadata format file for chapter marker preservation."""
    lines = [";FFMETADATA1"]
    current_time = 0.0

    for start_sec, end_sec, title in segments:
        duration = end_sec - start_sec
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
    """Converts FFmpeg metadata chapters to WebVTT track format for HTML5 players."""
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


def clean_directory(dir_path: Path) -> None:
    """Removes and recreates target workspace directory."""
    if dir_path.exists():
        shutil.rmtree(dir_path)
    dir_path.mkdir(parents=True, exist_ok=True)
