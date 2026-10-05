"""src/time_utils.py"""

def format_ffprobe_timestamp(seconds_str: str) -> str:
    """Converts ffprobe time in seconds to HH:MM:SS.mmm format."""
    try:
        total_seconds = float(seconds_str)
    except (ValueError, TypeError):
        return "00:00:00.000"

    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = total_seconds % 60

    return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}"

def parse_timestamp_to_seconds(ts: str) -> float:
    """Converts HH:MM:SS.mmm or HH:MM:SS to total float seconds."""
    if not ts:
        return 0.0
    parts = ts.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return float(h) * 3600 + float(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return float(m) * 60 + float(s)
    return float(ts)


def format_elapsed_time(seconds: float) -> str:
    """Formats float seconds into a clean display string."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    if h > 0:
        return f"{h}h {m}m {s:.1f}s"
    elif m > 0:
        return f"{m}m {s:.1f}s"
    return f"{s:.1f}s"
