#!/usr/bin/env python3
"""
script_builders.py - FFmpeg Command & Shell Script Generators for Modular Video Pipeline
"""

from pathlib import Path
from typing import List, Dict, Any

# ==============================================================================
# SECTION 1: Low-Level FFmpeg Command Builders
# ==============================================================================

def build_utvideo_cmd(scene: dict) -> str:
    """Builds Pass 1: Lossless Ut Video extraction command using bash variables."""
    return (
        f'ffmpeg -y -loglevel warning \\\n'
        f'  -ss "$START_TIME" -to "$END_TIME" \\\n'
        f'  -i "$MASTER_MKV" \\\n'
        f'  -map 0:v:0 -map 0:a:0 -map_chapters -1 \\\n'
        f'  -c:v utvideo -c:a pcm_s16le \\\n'
        f'  "$TEMP_MKV"'
    )

def build_h264_cmd(scene: dict) -> str:
    """Builds Pass 2: Standardized H.264 MP4 render command using bash variables."""
    return (
        f'FADE="afade=t=in:st=0:d=0.005,afade=t=out:st=$FADE_OUT_START:d=0.005"\n'
        f'ffmpeg -y -loglevel warning \\\n'
        f'  -ch_layout stereo \\\n'
        f'  -i "$TEMP_MKV" \\\n'
        f'  ${{CROP_FILTER:+-vf "$CROP_FILTER" }}\\\n'
        f'  -c:v libx264 -crf 22 -preset slow \\\n'
        f'  -force_key_frames "expr:eq(n,0)" -g 60 \\\n'
        f'  -pix_fmt yuv420p -tag:v avc1 \\\n'
        f'  -color_primaries smpte170m -color_trc smpte170m -colorspace smpte170m \\\n'
        f'  -af "$FADE" -c:a aac -b:a 192k -ar 48000 \\\n'
        f'  -metadata title="$TITLE" \\\n'
        f'  -metadata album="$REEL_TITLE" \\\n'
        f'  -shortest \\\n'
        f'  "$OUT_MP4"'
    )

def build_black_spacer_cmd(scene: dict, out_spacer_path: Path) -> str:
    """Generates a 1-second black spacer matched to the post-crop resolution of a clip."""
    raw_crop = scene.get('crop', '')
    # Base NTSC dimensions
    w, h = 720, 480
    
    if raw_crop:
        try:
            delimiter = "|" if "|" in str(raw_crop) else " "
            parts = [int(p.strip()) for p in str(raw_crop).split(delimiter) if p.strip()]
            if len(parts) == 4:
                left, right, top, bottom = parts
                w = 720 - (left + right)
                h = 480 - (top + bottom)
        except (ValueError, TypeError):
            pass

    return (
        f'ffmpeg -y -loglevel warning \\\n'
        f'  -f lavfi -i "color=c=black:s={w}x{h}:r=29.97:d=1.0" \\\n'
        f'  -f lavfi -i "anullsrc=channel_layout=stereo:sample_rate=48000" \\\n'
        f'  -c:v libx264 -crf 22 -preset slow \\\n'
        f'  -pix_fmt yuv420p -tag:v avc1 \\\n'
        f'  -color_primaries smpte170m -color_trc smpte170m -colorspace smpte170m \\\n'
        f'  -c:a aac -b:a 192k -ar 48000 -ch_layout stereo \\\n'
        f'  -shortest \\\n'
        f'  "{out_spacer_path}"'
    )


# ==============================================================================
# SECTION 2: Concat Manifest & Metadata File Builders
# ==============================================================================

def build_concat_manifest(
    scenes: List[Dict[str, Any]], 
    black_spacer_path: Path, 
    out_manifest_path: Path
) -> Path:
    """Writes manifest text file alternating scenes and black spacers."""
    lines = []
    black_str = str(black_spacer_path.resolve())

    for idx, scene in enumerate(scenes):
        scene_str = str(Path(scene['out_mp4_path']).resolve())
        lines.append(f"file '{scene_str}'")
        if idx < len(scenes) - 1:
            lines.append(f"file '{black_str}'")

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
        chapter_title = scene.get('title', f"Scene {scene.get('scene_num', '')}")
        
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


def format_vtt_timestamp(ms: int) -> str:
    """Converts milliseconds to WebVTT timestamp string (HH:MM:SS.mmm)."""
    hrs = ms // 3600000
    ms %= 3600000
    mins = ms // 60000
    ms %= 60000
    secs = ms // 1000
    millis = ms % 1000
    return f"{hrs:02d}:{mins:02d}:{secs:02d}.{millis:03d}"


def build_webvtt_file(
    scenes: List[Dict[str, Any]], 
    out_vtt_path: Path
) -> Path:
    """Generates WebVTT subtitle file for Apple/QuickTime chapters."""
    lines = ["WEBVTT", ""]
    current_time_ms = 0

    for idx, scene in enumerate(scenes, start=1):
        duration_ms = int(round(scene['duration_sec'] * 1000))
        start_ms = current_time_ms
        end_ms = start_ms + duration_ms
        
        start_vtt = format_vtt_timestamp(start_ms)
        end_vtt = format_vtt_timestamp(end_ms)
        chapter_title = scene.get('title', f"Scene {idx}")
        
        lines.append(f"{idx}")
        lines.append(f"{start_vtt} --> {end_vtt}")
        lines.append(chapter_title)
        lines.append("")
        
        current_time_ms = end_ms + 1000  # Account for 1s black spacer

    out_vtt_path.parent.mkdir(parents=True, exist_ok=True)
    out_vtt_path.write_text("\n".join(lines) + "\n")
    return out_vtt_path


# ==============================================================================
# SECTION 3: Shell Script File Writers
# ==============================================================================

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

def write_extract_script(
    vid: str,
    scenes: List[Dict[str, Any]],
    script_dir: Path,
    scenes_dir: Path
) -> Path:
    """Generates 01_extract_scenes.sh, per-clip black spacer scripts, and individual scene scripts."""
    script_dir.mkdir(parents=True, exist_ok=True)
    scenes_dir.mkdir(parents=True, exist_ok=True)
    master_script_path = script_dir / "01_extract_scenes.sh"
    
    spacer_script_calls = []
    individual_script_calls = []

    # 1. Group scenes strictly by primary clip index ('01', '02', ..., '13')
    clip_groups: Dict[str, List[Dict[str, Any]]] = {}
    for scene in scenes:
        if "clip_idx" in scene and scene["clip_idx"]:
            raw_idx = str(scene["clip_idx"])
        else:
            # Parse from scene_id: strip vid prefix -> take first token -> take portion before dot
            id_suffix = scene["scene_id"].replace(f"{vid}-", "")
            raw_token = id_suffix.split("-")[0] if "-" in id_suffix else "01"
            raw_idx = raw_token.split(".")[0]  # <--- Strips subchapters like .1, .01

        clip_idx = raw_idx.zfill(2) if raw_idx.isdigit() else raw_idx
        clip_groups.setdefault(clip_idx, []).append(scene)

    # 2. Generate dedicated scripts for each clip's black spacer
    for clip_idx in sorted(clip_groups.keys()):
        clip_scenes = clip_groups[clip_idx]
        clip_id = f"{vid}-{clip_idx}"

        spacer_mp4_path = scenes_dir / f"{clip_id}-black.mp4"
        spacer_sh_path = script_dir / f"{clip_id}-black.sh"
        
        first_scene = clip_scenes[0]
        spacer_cmd = build_black_spacer_cmd(first_scene, spacer_mp4_path)

        spacer_sh_content = f"""#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Black Spacer Generation: {clip_id}-black
# ==============================================================================

echo "==> Generating Black Spacer: {clip_id}-black.mp4"
{spacer_cmd}
"""
        spacer_sh_path.write_text(spacer_sh_content)
        spacer_sh_path.chmod(0o755)
        spacer_script_calls.append(f'bash "{spacer_sh_path.resolve()}"')

    # 3. Generate individual scene extraction scripts
    for scene in scenes:
        scene_sh_name = f"{scene['scene_id']}.sh"
        scene_sh_path = script_dir / scene_sh_name

        duration = scene['duration_sec']
        fade_out_start = max(0.0, round(duration - 0.005, 3))
        raw_crop = scene.get('crop', '')
        crop_val = build_crop_filter(str(raw_crop) if raw_crop else "")
        title_val = scene.get('title', '')
        reel_title_val = scene.get('reel_title', '')

        utvideo_cmd = build_utvideo_cmd(scene)
        h264_cmd = build_h264_cmd(scene)

        scene_sh_content = f"""#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Scene Processing: {scene['scene_id']}
# ==============================================================================

# Input & Staging Paths
MASTER_MKV="{scene['master_mkv_path']}"
TEMP_MKV="{scene['temp_mkv_path']}"
OUT_MP4="{scene['out_mp4_path']}"

# Timecodes & Durations
START_TIME="{scene['start_time']}"
END_TIME="{scene['end_time']}"
DURATION="{duration}"
FADE_OUT_START="{fade_out_start:.3f}"

# Video & Metadata Parameters
CROP_FILTER="{crop_val}"
TITLE="{title_val}"
REEL_TITLE="{reel_title_val}"

echo "==> Processing Scene: {scene['scene_id']}"
echo "  -> [1/2] Lossless extraction (Ut Video)..."
{utvideo_cmd}

echo "  -> [2/2] Standardized H.264 render..."
{h264_cmd}

echo "  -> Cleaning up temporary intermediate..."
rm -f "$TEMP_MKV"
"""
        scene_sh_path.write_text(scene_sh_content)
        scene_sh_path.chmod(0o755)
        individual_script_calls.append(f'bash "{scene_sh_path.resolve()}"')

    # 4. Construct master orchestrator (01_extract_scenes.sh)
    master_content = f"""#!/usr/bin/env bash
set -euo pipefail

# Phase 3: Scene Extraction Pipeline for {vid}
echo "==> [Phase 3.1] Generating {len(spacer_script_calls)} dimension-matched black spacer(s)..."
""" + "\n".join(spacer_script_calls) + f"""

echo "==> [Phase 3.2] Extracting and encoding {len(scenes)} scene(s)..."
""" + "\n".join(individual_script_calls) + """

echo "==> [Phase 3] Scene extraction completed successfully!"
"""

    master_script_path.write_text(master_content)
    master_script_path.chmod(0o755)
    return master_script_path
  
def write_concat_script(
    vid: str,
    clip_id: str,
    concat_txt_path: Path,
    meta_txt_path: Path,
    meta_vtt_path: Path,
    out_mp4_path: Path,
    script_dir: Path
) -> Path:
    """Generates a per-clip concat script for stream copy and metadata injection."""
    script_dir.mkdir(parents=True, exist_ok=True)
    concat_script_path = script_dir / f"{clip_id}_concat.sh"  # <--- Per-clip script name!
    tmp_mp4_path = out_mp4_path.parent / f"{clip_id}-TEMP.mp4"

    script_content = f"""#!/usr/bin/env bash
set -euo pipefail

# Phase 4: Concat, Metadata Tagging & Apple Faststart for {clip_id}
CONCAT_TXT="{concat_txt_path.resolve()}"
META_TXT="{meta_txt_path.resolve()}"
META_VTT="{meta_vtt_path.resolve()}"
TMP_MP4="{tmp_mp4_path.resolve()}"
OUT_MP4="{out_mp4_path.resolve()}"

echo "==> [Step 1/2] Zero-loss stream copy concatenation for {clip_id}..."
ffmpeg -y -loglevel warning \\
  -f concat -safe 0 -i "$CONCAT_TXT" \\
  -c copy "$TMP_MP4"

echo "==> [Step 2/2] Injecting Apple metadata, chapters, and soft WebVTT subtitles..."
ffmpeg -y -loglevel warning \\
  -i "$TMP_MP4" -i "$META_TXT" -i "$META_VTT" \\
  -map 0:v -map 0:a -map 2:s \\
  -map_metadata 1 -map_chapters 1 \\
  -c:v copy -c:a copy -c:s mov_text \\
  -metadata:s:0 language=eng \\
  -disposition:s:0 default \\
  -movflags +faststart \\
  "$OUT_MP4"

echo "==> Cleaning up staging file..."
rm -f "$TMP_MP4"

echo "==> Success! Output generated at: $OUT_MP4"
"""

    concat_script_path.write_text(script_content)
    concat_script_path.chmod(0o755)
    return concat_script_path
