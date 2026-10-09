# pipeline/orchestrator.py
from pathlib import Path

from pipeline.adapters import to_builder_data
from pipeline.layout import PipelineDirs
from pipeline.mkv import read_mkv_metadata
from pipeline.models import ArchiveData
from pipeline.script_builders import (
    build_concat_manifest,
    build_ffmetadata_file,
    build_webvtt_file,
    write_concat_script,
    write_extract_script,
)
from pipeline.spec import read_tape_spec


def generate_pipeline(
    vid: str, base_dir: Path, fps: str, resolution: str
) -> Path:
    """Orchestrates metadata parsing and generates all sub-scripts and master pipeline runner."""
    dirs = PipelineDirs(base_dir, vid)
    dirs.ensure_exists()

    master_mkv_path = dirs.archive / f"{vid}.mkv"
    spec_path = dirs.specs / f"{vid}.txt"

    if not master_mkv_path.exists():
        raise FileNotFoundError(
            f"Archival master not found at {master_mkv_path}"
        )

    # Ingest Metadata
    if spec_path.exists():
        print(
            f"--> Reading LosslessCut spec file: {dirs.rel_path(spec_path)}"
        )
        archive_data = read_tape_spec(spec_path.read_text(encoding="utf-8"))
        archive_data.print_warnings()
    else:
        print(
            f"--> Spec file not found at {spec_path}. Attempting MKV embedded import..."
        )
        archive_data = read_mkv_metadata(master_mkv_path)

    if not archive_data or not archive_data.clips:
        raise ValueError(f"Failed to load valid clip metadata for {vid}")

    builder_data = to_builder_data(
        archive=archive_data,
        vid=vid,
        scenes_dir=dirs.scenes,
        clips_dir=dirs.clips,
        master_mkv_path=master_mkv_path,
        overall_title=archive_data.global_date or vid,
        fps=fps,
        resolution=resolution,
    )

    clips = builder_data["clips"]
    total_scenes = sum(len(c["scenes"]) for c in clips)
    print(
        f"--> Parsed {total_scenes} total scene(s) across {len(clips)} clip(s)."
    )

    write_extract_script(
        vid=vid, clips=clips, script_dir=dirs.scripts, scenes_dir=dirs.scenes
    )

    master_body_lines = []
    for clip in clips:
        clip_idx = clip["clip_idx"]
        clip_id = f"{vid}-{clip_idx}"
        clip_scenes = clip["scenes"]

        manifest_path = dirs.scripts / f"{clip_id}.txt"
        meta_txt_path = dirs.metadata / f"{clip_id}.txt"
        meta_vtt_path = dirs.metadata / f"{clip_id}.vtt"
        black_spacer_path = Path(clip["black_spacer_path"])
        clean_clip_title = clip.get("title") or f"Clip_{clip_idx}"

        build_concat_manifest(clip_scenes, black_spacer_path, manifest_path)
        build_ffmetadata_file(
            clip_scenes, meta_txt_path, title=clean_clip_title
        )
        build_webvtt_file(clip_scenes, meta_vtt_path)

        clip_concat_sh = write_concat_script(
            vid=vid,
            clip=clip,
            concat_txt_path=manifest_path,
            meta_txt_path=meta_txt_path,
            meta_vtt_path=meta_vtt_path,
            script_dir=dirs.scripts,
        )

        master_body_lines.append("# " + "-" * 78)
        master_body_lines.append(f"# CLIP {clip_idx}: {clean_clip_title}")
        master_body_lines.append("# " + "-" * 78)
        master_body_lines.append("(")
        master_body_lines.append(f'  SCRIPT_DIR="{dirs.scripts.resolve()}"')
        master_body_lines.append(
            f'  echo "==> [START] Processing Clip {clip_idx}/{len(clips)}: {clean_clip_title}"'
        )

        for scene in clip_scenes:
            master_body_lines.append(
                f'  bash "$SCRIPT_DIR/{scene["scene_id"]}.sh"'
            )

        master_body_lines.append(f'  bash "$SCRIPT_DIR/{clip_id}-black.sh"')
        master_body_lines.append(
            f'  bash "$SCRIPT_DIR/{clip_concat_sh.name}"'
        )
        master_body_lines.append(
            f'  echo "==> [COMPLETE] Clip {clip_idx} finished successfully!"'
        )
        master_body_lines.append(")")
        master_body_lines.append("")

    master_script_path = dirs.scripts / "01_run_pipeline.sh"
    content = (
        f"#!/usr/bin/env bash\nset -euo pipefail\n\n"
        f'echo "==> Launching clip-by-clip pipeline for {vid}..."\n\n'
        + "\n".join(master_body_lines)
        + '\necho "=================================================================="\n'
        + 'echo "  [SUCCESS] All clips built, concatenated, and tagged!"\n'
        + 'echo "=================================================================="\n'
    )

    master_script_path.write_text(content)
    master_script_path.chmod(0o755)
    return master_script_path
