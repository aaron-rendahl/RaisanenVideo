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

def parse_crop_string(crop_str: str) -> tuple[int, int, int, int] | None:
    """Parses 'Top Bottom Left Right' spec string into (top, bottom, left, right).
    
    Raises ValueError if input is non-empty, invalid, negative, or produces odd trims.
    """
    if not crop_str or not crop_str.strip():
        return None

    delimiter = "|" if "|" in crop_str else None
    tokens = [p.strip() for p in crop_str.split(delimiter) if p.strip()]

    if len(tokens) != 4:
        raise ValueError(
            f"Invalid crop spec '{crop_str}': expected 4 space/pipe-separated integers "
            f"(Top Bottom Left Right), got {len(tokens)} token(s)."
        )

    try:
        top, bottom, left, right = (int(t) for t in tokens)
    except ValueError as e:
        raise ValueError(
            f"Invalid crop spec '{crop_str}': all values must be integers."
        ) from e

    if any(v < 0 for v in (top, bottom, left, right)):
        raise ValueError(
            f"Invalid crop spec '{crop_str}': crop trim values cannot be negative."
        )

    # Check for YUV420p odd-pixel constraints
    if (top + bottom) % 2 != 0:
        raise ValueError(
            f"Invalid crop spec '{crop_str}': vertical trims (Top + Bottom = {top + bottom}) "
            "must sum to an even number to satisfy YUV420p frame requirements."
        )

    if (left + right) % 2 != 0:
        raise ValueError(
            f"Invalid crop spec '{crop_str}': horizontal trims (Left + Right = {left + right}) "
            "must sum to an even number to satisfy YUV420p frame requirements."
        )

    return top, bottom, left, right

def parse_crop_to_ffmpeg(
    crop_str: str,
    base_width: int,
    base_height: int,
) -> str:
    """Converts LosslessCut 'top bottom left right' trims into FFmpeg 'out_w:out_h:x:y' syntax.
    
    Raises ValueError if trims exceed base frame dimensions.
    """
    parsed = parse_crop_string(crop_str)
    if not parsed:
        return ""

    top, bottom, left, right = parsed

    out_w = base_width - left - right
    out_h = base_height - top - bottom

    if out_w <= 0:
        raise ValueError(
            f"Invalid crop spec '{crop_str}': horizontal trims (left={left}, right={right}) "
            f"equal or exceed base width ({base_width}px), resulting in width {out_w}px."
        )

    if out_h <= 0:
        raise ValueError(
            f"Invalid crop spec '{crop_str}': vertical trims (top={top}, bottom={bottom}) "
            f"equal or exceed base height ({base_height}px), resulting in height {out_h}px."
        )

    x = left
    y = top

    return f"{out_w}:{out_h}:{x}:{y}"

def get_effective_resolution(
    crop_str: str,
    base_width: int,
    base_height: int,
) -> str:
    """Computes target 'WxH' canvas resolution string after applying crop trims.
    
    Returns base resolution if crop_str is empty/None.
    Raises ValueError if crop trims exceed base frame dimensions.
    """
    parsed = parse_crop_string(crop_str)
    if not parsed:
        return f"{base_width}x{base_height}"

    top, bottom, left, right = parsed

    out_w = base_width - left - right
    out_h = base_height - top - bottom

    if out_w <= 0:
        raise ValueError(
            f"Invalid crop spec '{crop_str}': horizontal trims (left={left}, right={right}) "
            f"equal or exceed base width ({base_width}px), resulting in width {out_w}px."
        )

    if out_h <= 0:
        raise ValueError(
            f"Invalid crop spec '{crop_str}': vertical trims (top={top}, bottom={bottom}) "
            f"equal or exceed base height ({base_height}px), resulting in height {out_h}px."
        )

    return f"{out_w}x{out_h}"

def sanitize(title: str) -> str:
    """Converts titles into clean, filesystem-safe string segments."""
    if not title:
        return "untitled"
    cleaned = re.sub(r"['’\"]", "", title)
    cleaned = re.sub(r"[^a-zA-Z0-9\-]", " ", cleaned)
    cleaned = re.sub(r"\s+", "_", cleaned.strip())
    return cleaned.strip("_-") or "untitled"
