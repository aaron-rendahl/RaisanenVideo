from pathlib import Path

from pipeline.adapters import to_builder_data
from pipeline.mkv import probe_mkv, read_mkv_metadata
from pipeline.paths import PipelinePaths
from pipeline.script_builders import render_all_scripts
from pipeline.spec import read_tape_spec


def generate_pipeline(
    vid: str,
    base_dir: Path,
) -> Path:
    """Orchestrates metadata parsing and generates all sub-scripts and master pipeline runner."""

    # 1. Initialize workspace paths & ensure directories exist
    paths = PipelinePaths.from_vid(base_dir, vid)
    paths.ensure_exists()

    if not paths.path_archive_mkv.exists():
        raise FileNotFoundError(
            f"Archival master not found at {paths.path_archive_mkv}"
        )

    # 2. Ingest Metadata (Spec file or embedded MKV)
    if paths.path_specs.exists():
        print(f"--> Reading LosslessCut spec file: {paths.rel_path(paths.path_specs)}")
        archive_data = read_tape_spec(paths.path_specs.read_text(encoding="utf-8"))
        archive_data.print_warnings()
    else:
        print(f"--> Spec file not found at {paths.path_specs}. Attempting MKV embedded import...")
        archive_data = read_mkv_metadata(paths.path_archive_mkv)

    if not archive_data or not archive_data.clips:
        raise ValueError(f"Failed to load valid clip metadata for {vid}")

    # 3. Probe container media specs from source MKV
    media_info = probe_mkv(paths.path_archive_mkv)

    # 4. Fill missing trailing end timestamps using container duration
    archive_data.resolve_missing_end_times(media_info["duration"])

    # 5. Transform domain models into Jinja render payload
    builder_data = to_builder_data(
        archive=archive_data,
        paths=paths,
        archive_resolution=media_info["resolution"],
        archive_fps=media_info["fps"],
    )

    total_scenes = sum(len(c["scenes"]) for c in builder_data["clips"])
    print(f"--> Parsed {total_scenes} total scene(s) across {len(builder_data['clips'])} clip(s).")

    # 6. Render all scripts, manifests, and metadata text files
    render_all_scripts(builder_data, paths)

    print(f"--> Main pipeline script generated at: {paths.rel_path(paths.path_main_sh)}")

    return paths.path_main_sh
