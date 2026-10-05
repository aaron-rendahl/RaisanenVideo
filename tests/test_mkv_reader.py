"""
tests/test_mkv_reader.py

Unit tests for mkv_reader.py using mocked ffprobe JSON payloads.
"""

import json
from unittest.mock import MagicMock, patch
from mkv_reader import read_mkv_metadata


@patch("subprocess.run")
def test_read_mkv_metadata_parses_ffprobe_json(mock_run):
    """Verifies stream crop detection, chapter tag parsing, and clip generation."""
    mock_payload = {
        "streams": [
            {
                "codec_type": "video",
                "crop_top": 8,
                "crop_bottom": 8,
                "crop_left": 12,
                "crop_right": 12,
            }
        ],
        "chapters": [
            {
                "start_time": "1.168",
                "end_time": "132.366",
                "tags": {
                    "title": "Arrival",
                    "DATE_RECORDED": "1987-09-19",
                },
            },
            {
                "start_time": "132.366",
                "end_time": "281.548",
                "tags": {
                    "title": "Kids Dance",
                    "CROPPING": "0|0|0|0",
                },
            },
        ],
    }

    mock_run.return_value = MagicMock(
        stdout=json.dumps(mock_payload),
        returncode=0,
    )

    data = read_mkv_metadata("dummy_archive.mkv")

    # Verify video stream crop detection
    assert data.global_crop == "8|8|12|12"
    assert len(data.clips) == 2

    # Clip 1: Inherits global stream crop and reads DATE_RECORDED
    clip1 = data.clips[0]
    assert clip1.idx == "01"
    assert clip1.title == "Arrival"
    assert clip1.start == "00:00:01.168"
    assert clip1.end == "00:02:12.366"
    assert clip1.date == "1987-09-19"
    assert clip1.crop == "8|8|12|12"

    # Clip 2: Overrides global crop with chapter-level CROPPING tag
    clip2 = data.clips[1]
    assert clip2.idx == "02"
    assert clip2.title == "Kids Dance"
    assert clip2.crop == "0|0|0|0"
