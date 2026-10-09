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
    """Pass 1: Suppresses container crop, conditionally applies spatial crop, and extracts 4:2:2 Ut Video."""
    return (
        f'ffmpeg -y -loglevel warning \\\n'
        f'  -fflags +genpts \\\n'
        f'  -ss "$START_TIME" -to "$END_TIME" \\\n'
        f'  -apply_cropping 0 \\\n'
        f'  -i "$MASTER_MKV" \\\n'
        f'  -map 0:v:0 -map 0:a:0 -map_chapters -1 \\\n'
        f'  ${{CROP_FILTER:+-vf "$CROP_FILTER" }}\\\n'
        f'  -c:v utvideo -pix_fmt yuv422p -c:a pcm_s16le \\\n'
        f'  -avoid_negative_ts make_zero \\\n'
        f'  "$TEMP_MKV"'
    )


def build_h264_cmd(scene: dict) -> str:
    """Pass 2: Encodes pre-cropped 4:2:2 intermediate into standardized 4:2:0 H.264 MP4 with input layout override."""
    return (
        f'FADE="afade=t=in:st=0:d=0.005,afade=t=out:st=$FADE_OUT_START:d=0.005"\n'
        f'ffmpeg -y -loglevel warning \\\n'
        f'  -fflags +genpts \\\n'
        f'  -ch_layout stereo \\\n'
        f'  -i "$TEMP_MKV" \\\n'
        f'  -c:v libx264 -crf 22 -preset slow \\\n'
        f'  -force_key_frames "expr:eq(n,0)" -g 60 \\\n'
        f'  -pix_fmt yuv420p -tag:v avc1 \\\n'
        f'  -color_primaries smpte170m -color_trc smpte170m -colorspace smpte170m \\\n'
        f'  -af "$FADE" -c:a aac -b:a 192k -ar 48000 \\\n'
        f'  -metadata title="$TITLE" \\\n'
        f'  -metadata album="$REEL_TITLE" \\\n'
        f'  -avoid_negative_ts make_zero \\\n'
        f'  -use_editlist 0 \\\n'
        f'  -movflags +faststart \\\n'
        f'  -shortest \\\n'
        f'  "$OUT_MP4"'
    )

def build_black_spacer_cmd(scene: dict, out_spacer_path: Path) -> str:
    """Generates a 1-second black spacer dynamically matched to the scene's exact
    rendered pixel dimensions, sample aspect ratio (SAR), and frame rate.
    """
    out_scene_path = Path(scene["out_mp4_path"])

    # Fallback defaults calculated from spec geometry math
    raw_crop = str(scene.get("crop", "")).strip()
    w, h = 720, 480
    if raw_crop:
        parts = [int(p) for p in raw_crop.split() if p.isdigit()]
        if len(parts) == 4:
            left, right, top, bottom = parts
            w = 720 - (left + right)
            h = 480 - (top + bottom)

    sar = "74/89"  # Default NTSC/ITU SAR
    fps = str(scene.get("fps") or scene.get("r_frame_rate") or "30000/1001")

    # If the scene MP4 has been rendered, probe its exact post-crop metadata
    if out_scene_path.exists():
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,sample_aspect_ratio,r_frame_rate",
            "-of",
            "json",
            str(out_scene_path),
        ]
        try:
            res = subprocess.run(
                cmd, capture_output=True, text=True, check=True
            )
            data = json.loads(res.stdout)
            stream = data.get("streams", [{}])[0]

            w = stream.get("width", w)
            h = stream.get("height", h)
            probed_sar = stream.get("sample_aspect_ratio")
            if probed_sar and probed_sar not in ("0:1", "N/A"):
                # Convert colon notation (74:89) to slash notation (74/89) for setsar
                sar = probed_sar.replace(":", "/")

            probed_fps = stream.get("r_frame_rate")
            if probed_fps and probed_fps != "0/0":
                fps = probed_fps
        except Exception:
            pass

    return (
        f'SPACER_PATH="{out_spacer_path}"\n'
        f"ffmpeg -y -loglevel warning \\\n"
        f'  -f lavfi -i "color=c=black:s={w}x{h}:r={fps}:d=1.0" \\\n'
        f'  -f lavfi -i "anullsrc=channel_layout=stereo:sample_rate=48000" \\\n'
        f'  -vf "setsar={sar}" \\\n'
        f"  -c:v libx264 -crf 22 -preset slow \\\n"
        f'  -force_key_frames "expr:eq(n,0)" -g 60 \\\n'
        f"  -pix_fmt yuv420p -tag:v avc1 \\\n"
        f"  -color_primaries smpte170m -color_trc smpte170m -colorspace smpte170m \\\n"
        f"  -c:a aac -b:a 192k -ar 48000 -ch_layout stereo \\\n"
        f"  -avoid_negative_ts make_zero \\\n"
        f"  -use_editlist 0 \\\n"
        f"  -movflags +faststart \\\n"
        f"  -shortest \\\n"
        f'  "$SPACER_PATH"'
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
    clips: List[Dict[str, Any]],
    script_dir: Path,
    scenes_dir: Path
) -> None:
    """Generates individual scene processing scripts and clip-level black spacer scripts."""
    script_dir.mkdir(parents=True, exist_ok=True)
    scenes_dir.mkdir(parents=True, exist_ok=True)

    for clip in clips:
        clip_idx = clip['clip_idx']
        clip_id = f"{vid}-{clip_idx}"

        # 1. Generate individual scene extraction scripts
        for scene in clip['scenes']:
            scene_sh_path = script_dir / f"{scene['scene_id']}.sh"

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

        # 2. Generate clip-level black spacer script (referencing clip's first scene)
        first_scene = clip['scenes'][0]
        spacer_mp4_path = Path(clip['black_spacer_path'])
        spacer_sh_path = script_dir / f"{clip_id}-black.sh"

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

def write_concat_script(
    vid: str,
    clip: Dict[str, Any],
    concat_txt_path: Path,
    meta_txt_path: Path,
    meta_vtt_path: Path,
    script_dir: Path
) -> Path:
    """Generates a per-clip concat script for stream copy and metadata injection."""
    script_dir.mkdir(parents=True, exist_ok=True)

    clip_idx = clip['clip_idx']
    clip_id = f"{vid}-{clip_idx}"

    out_mp4_path = Path(clip['out_concat_path'])
    tmp_mp4_path = out_mp4_path.parent / f"{clip_id}-TEMP.mp4"
    concat_script_path = script_dir / f"{clip_id}_concat.sh"

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
  -fflags +genpts \\
  -f concat -safe 0 \\
  -i "$CONCAT_TXT" \\
  -c copy \\
  -avoid_negative_ts make_zero \\
  -use_editlist 0 \\
  "$TMP_MP4"

echo "==> [Step 2/2] Injecting metadata & chapters markers..."
ffmpeg -y -loglevel warning \\
  -i "$TMP_MP4" -i "$META_TXT" \\
  -map 0:v:0 -map 0:a:0 \\
  -map_metadata 1 -map_chapters 1 \\
  -dn \\
  -c copy \\
  -avoid_negative_ts make_zero \\
  -movflags +faststart \\
  -use_editlist 0 \\
  "$OUT_MP4"

echo "==> Cleaning up staging file..."
rm -f "$TMP_MP4"

echo "==> Success! Output generated at: $OUT_MP4"
"""

    concat_script_path.write_text(script_content)
    concat_script_path.chmod(0o755)
    return concat_script_path
