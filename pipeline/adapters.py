import dataclasses
import re
from pathlib import Path
from typing import Any, Dict, List

from pipeline.models import ArchiveData

def timestamp_to_seconds(ts: str) -> float:
    """Converts 'HH:MM:SS.mmm' or 'MM:SS.mmm' string to float seconds."""
    if not ts:
        return 0.0
    parts = ts.strip().split(':')
    if len(parts) == 3:
        h, m, s = parts
        return float(h) * 3600 + float(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return float(m) * 60 + float(s)
    return float(parts[0])


def sanitize_filename(title: str) -> str:
    """Converts titles into clean, filesystem-safe string segments."""
    if not title:
        return "untitled"
    # Replace spaces with underscores and remove non-alphanumeric/hyphen/underscore chars
    cleaned = re.sub(r'\s+', '_', title.strip())
    cleaned = re.sub(r'[^a-zA-Z0-9_\-]', '', cleaned)
    return cleaned.strip('_') or "untitled"

def to_builder_data(
    archive: ArchiveData,
    vid: str,
    prep_dir: Path,
    master_mkv_path: Path,
    overall_title: str = "",
    fps: str = "30000/1001",
    resolution: str = "720x480"
) -> Dict[str, Any]:
    """Transforms ArchiveData model into scene extraction tasks and clip-level specs."""
    scenes = []
    clips = []
    scene_dir = prep_dir / vid / "scenes"
    abs_master_mkv = str(master_mkv_path.resolve())

    for clip in archive.clips:
        clip_crop = clip.crop or archive.global_crop
        safe_clip_title = sanitize_filename(clip.title)

        clip_spacer_path = str((scene_dir / f'{vid}-{clip.idx}_black.mp4').resolve())
        out_concat_path = str((prep_dir / vid / f'{vid}-{clip.idx}_{safe_clip_title}.mp4').resolve())

        items_to_process = clip.subchapters if clip.subchapters else [clip]
        group_scene_paths = []

        for item in items_to_process:
            clean_title = sanitize_filename(item.title)
            scene_id = f"{vid}-{item.idx}-{clean_title}"

            start_sec = timestamp_to_seconds(item.start)
            end_sec = timestamp_to_seconds(item.end)
            duration_sec = max(0.0, end_sec - start_sec)

            temp_mkv_path = str((scene_dir / f'{scene_id}_temp.mkv').resolve())
            out_mp4_path = str((scene_dir / f'{scene_id}.mp4').resolve())

            scenes.append({
                'scene_id': scene_id,
                'master_mkv_path': abs_master_mkv,
                'start_time': item.start,
                'end_time': item.end,
                'duration_sec': duration_sec,
                'temp_mkv_path': temp_mkv_path,
                'out_mp4_path': out_mp4_path,
                'crop': clip_crop,
                'title': item.title,
                'reel_title': overall_title or vid,
                'resolution': resolution,
                'fps': fps
            })

            group_scene_paths.append(out_mp4_path)

        clips.append({
            'clip_idx': clip.idx,
            'title': clip.title,
            'crop': clip_crop,
            'black_spacer_path': clip_spacer_path,
            'out_concat_path': out_concat_path,
            'scene_paths': group_scene_paths
        })

    return {
        'vid': vid,
        'scenes': scenes,
        'clips': clips
    }
