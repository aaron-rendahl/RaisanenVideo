from typing import Any, Dict

from pipeline.models import ArchiveData
from pipeline.paths import PipelinePaths
from pipeline.utils import parse_crop_to_ffmpeg, timestamp_to_seconds, get_effective_resolution

def to_builder_data(
    archive: ArchiveData,
    paths: PipelinePaths,
    overall_title: str = "",
    fps: str = "30000/1001",
    resolution: str = "720x480",
) -> Dict[str, Any]:
    """Transforms ArchiveData into a hierarchical clip-and-scene structure."""

    clips_data = []
    for clip in archive.clips:
        raw_crop = clip.crop or archive.global_crop
        clip_crop = parse_crop_to_ffmpeg(raw_crop) if raw_crop else ""
        clip_res = get_effective_resolution(raw_crop, default_res=resolution)

        items = clip.subchapters if clip.subchapters else [clip]
        scenes_data = []
        for item in items:
            start_sec = timestamp_to_seconds(item.start)
            end_sec = timestamp_to_seconds(item.end)
            duration_sec = max(0.0, end_sec - start_sec)

            scenes_data.append(
                {
                    "video": paths.vid,
                    "clip_idx": clip.idx,
                    "clip_title": overall_title or paths.vid,
                    "scene_idx": item.idx,
                    "scene_title": item.title,
                    "start_time": item.start,
                    "end_time": item.end,
                    "duration_sec": duration_sec,
                    "crop": clip_crop,
                    "resolution": clip_res,
                    "fps": fps,
                    **paths.scene_paths(item),
                }
            )

        clips_data.append(
            {
                "clip_idx": clip.idx,
                "title": clip.title,
                "crop": clip_crop,
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
