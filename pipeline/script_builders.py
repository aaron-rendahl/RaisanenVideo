#!/usr/bin/env python3
"""
script_builders.py - Manifest & Shell Script Writers for Video Pipeline
"""

from pathlib import Path
from typing import Any, Dict, List
from jinja2 import Environment, FileSystemLoader

# Set up Jinja2 environment pointing to pipeline/templates
TEMPLATES_DIR = Path(__file__).parent / "templates"
jinja_env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    trim_blocks=True,
    lstrip_blocks=True,
)


# ==============================================================================
# SECTION 1: Concat Manifest & Metadata File Builders
# ==============================================================================

def build_concat_manifest(
    scenes: List[Dict[str, Any]], 
    black_spacer_path: str, 
    out_manifest_path: Path
) -> Path:
    """Writes manifest text file alternating scenes and black spacers."""
    lines = []
    for idx, scene in enumerate(scenes):
        lines.append(f"file '{scene['path_scene_mp4']}'")
        if idx < len(scenes) - 1:
            lines.append(f"file '{black_spacer_path}'")

    out_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    out_manifest_path.write_text("\n".join(lines) + "\n")
    return out_manifest_path


def build_ffmetadata_file(
    scenes: List[Dict[str, Any]], 
    out_meta_txt_path: Path,
    title: str = ""
) -> Path:
    """Generates ffmetadata file with TIMEBASE=1/1000 millisecond offsets."""
    lines = [
        ";FFMETADATA1",
        "TIMEBASE=1/1000",
        f"title={title}" if title else ""
    ]
    current_time_ms = 0

    for scene in scenes:
        duration_ms = int(round(scene['duration_sec'] * 1000))
        start_ms = current_time_ms
        end_ms = start_ms + duration_ms
        chapter_title = scene.get('scene_title', f"Scene {scene.get('scene_idx', '')}")
        
        lines.append("")
        lines.append("[CHAPTER]")
        lines.append("TIMEBASE=1/1000")
        lines.append(f"START={start_ms}")
        lines.append(f"END={end_ms}")
        lines.append(f"title={chapter_title}")
        
        current_time_ms = end_ms + 1000  # Account for 1s black spacer

    out_meta_txt_path.parent.mkdir(parents=True, exist_ok=True)
    out_meta_txt_path.write_text("\n".join(lines) + "\n")
    return out_meta_txt_path


# ==============================================================================
# SECTION 2: Template Script Writers & Rendering Orchestrator
# ==============================================================================

def _write_script(target_path: Path, content: str) -> None:
    """Helper to write template content to disk and set executable permissions."""
    target_path.write_text(content)
    target_path.chmod(0o755)


def render_all_scripts(data: Dict[str, Any], paths: PipelinePaths) -> None:
    """Generates all shell scripts, concat manifests, and metadata files for a video pipeline."""
    
    # Filter resolving paths relative to the scripts directory
    def script_rel_filter(path_val: str | Path) -> str:
        p = Path(path_val) if isinstance(path_val, str) else path_val
        try:
            return str(p.resolve().relative_to(paths.scripts.resolve()))
        except ValueError:
            return str(p)

    # Register both the script dir and the relative filter on the environment
    jinja_env.globals["script_dir"] = paths.scripts
    jinja_env.filters["rel_script"] = script_rel_filter
    
    # 1. Render Scene Extraction Scripts
    extract_tmpl = jinja_env.get_template("extract_scene.sh.j2")
    for clip in data["clips"]:
        for scene in clip["scenes"]:
            script_path = Path(scene["path_scene_sh"])
            content = extract_tmpl.render(**scene)
            _write_script(script_path, content)

    # 2. Render Spacer, Concat Scripts, and Text Manifests
    spacer_tmpl = jinja_env.get_template("black_spacer.sh.j2")
    concat_tmpl = jinja_env.get_template("concat.sh.j2")

    for clip in data["clips"]:
        # Write text metadata & manifests needed for concatenation
        build_concat_manifest(
            scenes=clip["scenes"],
            black_spacer_path=clip["path_spacer_mp4"],
            out_manifest_path=Path(clip["path_manifest"])
        )
        build_ffmetadata_file(
            scenes=clip["scenes"],
            out_meta_txt_path=Path(clip["path_metadata"]),
            title=clip.get("title", "")
        )

        spacer_sh_path = Path(clip["path_spacer_sh"])
        _write_script(spacer_sh_path, spacer_tmpl.render(**clip))

        concat_sh_path = Path(clip["path_clip_sh"])
        _write_script(concat_sh_path, concat_tmpl.render(**clip))

    # 3. Render Master Orchestrator Script
    master_tmpl = jinja_env.get_template("main_pipeline.sh.j2")
    master_sh_path = Path(data["path_main_sh"])
    _write_script(master_sh_path, master_tmpl.render(**data))
