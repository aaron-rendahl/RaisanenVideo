import re

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

def parse_crop_string(crop_str: str):
    """Parses 'Top Bottom Left Right' or 'Top|Bottom|Left|Right' spec string into (top, bottom, left, right)."""
    if not crop_str:
        return None
    try:
        delimiter = "|" if "|" in crop_str else " "
        parts = [int(p.strip()) for p in crop_str.split(delimiter) if p.strip()]
        if len(parts) == 4:
            return parts[0], parts[1], parts[2], parts[3]
    except ValueError:
        pass
    return None

def parse_crop_to_ffmpeg(
    crop_str: str,
    base_width: int = 720,
    base_height: int = 480,
) -> str:
    """Converts LosslessCut 'top bottom left right' trims into FFmpeg 'out_w:out_h:x:y' syntax."""
    parsed = parse_crop_string(crop_str)
    if not parsed:
        return ""

    top, bottom, left, right = parsed
    out_w = base_width - left - right
    out_h = base_height - top - bottom
    x = left
    y = top

    return f"{out_w}:{out_h}:{x}:{y}"

def get_effective_resolution(raw_crop: str, default_res: str = "720x480") -> str:
    """Derives post-crop 'WxH' resolution if a crop string exists, otherwise returns default."""
    if not raw_crop:
        return default_res

    # Expects crop format like "crop=w:h:x:y" or "w:h:x:y" or "w:h"
    match = re.search(r"(?:crop=)?(\d+):(\d+)", raw_crop)
    if match:
        w, h = match.groups()
        return f"{w}x{h}"
    
    return default_res

def sanitize(title: str) -> str:
    """Converts titles into clean, filesystem-safe string segments."""
    if not title:
        return "untitled"
    cleaned = re.sub(r"['’\"]", "", title)
    cleaned = re.sub(r"[^a-zA-Z0-9\-]", " ", cleaned)
    cleaned = re.sub(r"\s+", "_", cleaned.strip())
    return cleaned.strip("_-") or "untitled"
