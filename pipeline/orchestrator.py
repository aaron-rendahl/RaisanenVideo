# pipeline/orchestrator.py
from pathlib import Path

from pipeline.adapters import to_builder_data
from pipeline.layout import PipelineDirs
from pipeline.mkv import read_mkv_metadata
from pipeline.models import ArchiveData
from pipeline.script_builders import (
    build_concat_manifest,
    build_ffmetadata_file,
    write_concat_script,
    write_extract_scripts,
    write_black_spacer_script,
    write_main_script
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

    for clip in clips:
        clip_idx = clip["clip_idx"]
        clip_id = f"{vid}-{clip_idx}"
        clip_scenes = clip["scenes"]

        manifest_path = dirs.scripts / f"{clip_id}.txt"
        meta_txt_path = dirs.metadata / f"{clip_id}.txt"
        black_spacer_path = Path(clip["black_spacer_path"])
        clean_clip_title = clip.get("title") or f"Clip_{clip_idx}"

        build_concat_manifest(clip_scenes, black_spacer_path, manifest_path)
        build_ffmetadata_file(
            clip_scenes, meta_txt_path, title=clean_clip_title
        )

        write_extract_scripts(
            vid=vid, 
            scenes=clip_scenes, 
            script_dir=dirs.scripts, 
            scenes_dir=dirs.scenes
        )

        write_black_spacer_script(
            vid=vid,
            clip=clip,
            script_dir=dirs.scripts,
            fps=fps,
            resolution=resolution,
        )

        write_concat_script(
            vid=vid,
            clip=clip,
            concat_txt_path=manifest_path,
            meta_txt_path=meta_txt_path,
            script_dir=dirs.scripts,
        )

    # 3. Render master execution script via Jinja2
    main_script_path = write_main_script(
        vid=vid,
        clips=clips,
        script_dir=dirs.scripts,
    )
    
    print(f"--> Main pipeline script generated at: {dirs.rel_path(main_script_path)}")

    return main_script_path
