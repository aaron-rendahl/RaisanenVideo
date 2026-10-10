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
