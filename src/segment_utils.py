"""src/segment_utils.py"""

from typing import List, Tuple
from models import Clip
from time_utils import parse_timestamp_to_seconds

def has_gaps(segments: List[Tuple[float, float, str]]) -> bool:
    """Checks if there are non-contiguous gaps between segment boundaries."""
    for i in range(len(segments) - 1):
        if abs(segments[i][1] - segments[i + 1][0]) > 0.05:
            return True
    return False

def resolve_clip_subchapters(
    clip: Clip, total_duration_sec: float = 0.0
) -> List[Tuple[str, str, str, float, float]]:
    """
    Single source of truth for resolving subchapter bounds.
    Returns a list of 5-tuples: (sub_tag, sub_title_display, sub_title_safe, start_sec, end_sec).
    """
    results = []
    subchapters = getattr(clip, "subchapters", [])

    if subchapters:
        for idx, sub in enumerate(subchapters, start=1):
            s_sec = parse_timestamp_to_seconds(sub.start) if isinstance(sub.start, str) else float(sub.start)

            if getattr(sub, "end", None):
                e_sec = parse_timestamp_to_seconds(sub.end) if isinstance(sub.end, str) else float(sub.end)
            elif idx < len(subchapters):
                next_start = subchapters[idx].start
                e_sec = parse_timestamp_to_seconds(next_start) if isinstance(next_start, str) else float(next_start)
            else:
                e_sec = total_duration_sec

            sub_title_raw = getattr(sub, "title", f"Chapter {idx}")

            # Display title: preserve spaces & punctuation for FFMETADATA / WebVTT
            sub_title_display = "".join(
                c if c.isalnum() or c in (" ", "-", "_", "'", ",", ".") else "" for c in sub_title_raw
            ).strip()

            # Safe title: convert spaces to underscores for filenames / debug logs
            sub_title_safe = sub_title_display.replace(" ", "_")

            sub_tag = getattr(sub, "idx", None) or f"{idx:02d}"
            results.append((sub_tag, sub_title_display, sub_title_safe, s_sec, e_sec))
    else:
        # Fallback for standalone clips without subchapters
        s_sec = parse_timestamp_to_seconds(clip.start) if isinstance(clip.start, str) else float(clip.start)
        e_sec = parse_timestamp_to_seconds(clip.end) if clip.end else total_duration_sec

        clip_title_raw = getattr(clip, "title", "Clip")
        clip_title_display = "".join(
            c if c.isalnum() or c in (" ", "-", "_", "'", ",", ".") else "" for c in clip_title_raw
        ).strip()
        clip_title_safe = clip_title_display.replace(" ", "_")

        sub_tag = getattr(clip, "idx", "01")
        results.append((sub_tag, clip_title_display, clip_title_safe, s_sec, e_sec))

    return results


def resolve_subsegments(
    clip: Clip, total_duration_sec: float = 0.0
) -> List[Tuple[float, float, str]]:
    """
    Backwards-compatible bridge for FFmpeg pipeline builders.
    Returns list of 3-tuples: (start_sec, end_sec, title_display).
    """
    resolved = resolve_clip_subchapters(clip, total_duration_sec)
    # Use title_display (index 1) so metadata retains natural spaces
    return [(s_sec, e_sec, title_display) for _, title_display, _, s_sec, e_sec in resolved]
