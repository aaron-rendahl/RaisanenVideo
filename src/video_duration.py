import json
import subprocess

def has_audio_stream(mkv_path: Path) -> bool:
    """Returns True if the MKV container has at least one audio stream."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=index",
        "-of", "csv=p=0",
        str(mkv_path)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    return bool(res.stdout.strip())


def get_video_duration(video_path: str) -> str:
    """Returns total duration of a video file formatted as HH:MM:SS.mmm using ffprobe."""
    cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_entries",
        "format=duration",
        video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    seconds = float(json.loads(result.stdout)["format"]["duration"])

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60

    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"
