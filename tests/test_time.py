"""
tests/test_time.py

Unit tests for mkv_reader.py using mocked ffprobe JSON payloads.
"""

from time_utils import format_ffprobe_timestamp

def test_format_ffprobe_timestamp():
    """Verifies floating-point seconds conversion to HH:MM:SS.mmm string format."""
    assert format_ffprobe_timestamp("0") == "00:00:00.000"
    assert format_ffprobe_timestamp("123.456") == "00:02:03.456"
    assert format_ffprobe_timestamp("3661.050") == "01:01:01.050"
    assert format_ffprobe_timestamp("invalid") == "00:00:00.000"
