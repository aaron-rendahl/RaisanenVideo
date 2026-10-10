from typing import Any, Dict

from pipeline.models import ArchiveData
from pipeline.paths import PipelinePaths
from pipeline.utils import parse_crop_to_ffmpeg, timestamp_to_seconds, get_effective_resolution

def to_builder_data(
    archive: ArchiveData,
    paths: PipelinePaths,
    archive_resolution: str,
    archive_fps: str,
) -> Dict[str, Any]:
    """Transforms ArchiveData into a hierarchical clip-and-scene template payload.

    `archive_resolution` (e.g., "720x480") and `fps` (e.g., "30000/1001") are
    required positional arguments probed from the source MKV container.
    """
    try:
        base_w, base_h = map(int, archive_resolution.lower().split("x"))
    except (ValueError, AttributeError):
        raise ValueError(
            f"Invalid source resolution: '{archive_resolution}'. "
            "Expected 'WxH' string probed from MKV (e.g., '720x480')."
        )

    clips_data = []
    for clip in archive.clips:
        raw_crop = clip.crop or archive.global_crop
        clip_crop = parse_crop_to_ffmpeg(raw_crop, base_w, base_h) if raw_crop else ""
        clip_res = get_effective_resolution(raw_crop, base_w, base_h) if raw_crop else archive_resolution

        items = clip.subchapters if clip.subchapters else [clip]
        scenes_data = []
        for item in items:
            scenes_data.append(
                {
                    "scene_idx": item.idx,
                    "scene_title": item.title,
                    "start_time": item.start,
                    "end_time": item.end,
                    "crop": clip_crop,
                    **paths.scene_paths(item),
                }
            )

        clips_data.append(
            {
                "clip_idx": clip.idx,
                "title": clip.title,
                "resolution": clip_res,
                "fps": fps,
                "scenes": scenes_data,
                **paths.clip_paths(clip),
            }
        )

    return {
        "path_main_sh": str(paths.path_main_sh.resolve()),
        "clips": clips_data,
    }
