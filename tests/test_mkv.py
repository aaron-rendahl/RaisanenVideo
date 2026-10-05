"""tests/test_mkv.py

Integration round-trip tests for Matroska container metadata (Writer <-> Reader).
"""

import textwrap
from unittest.mock import MagicMock, patch
import pytest

from mkv_reader import read_mkv_metadata
from mkv_writer import generate_mkv_chapters_and_tags
from spec_reader import read_tape_spec


@patch("subprocess.run")
def test_mkv_xml_writer_reader_roundtrip(mock_run):
    """Verifies complete round-trip fidelity:
    Spec -> ArchiveData -> mkv_writer XML -> (mkvextract mock) -> mkv_reader -> ArchiveData
    Ensures nested subchapters, custom crops, and dates are preserved across writer/reader.
    """
    spec_text = textwrap.dedent("""
        TITLE = Raisanen 1987 Tape A
        GLOBAL_DATE = 1987-05-10
        GLOBAL_CROP = 30 6 18 8

        01 | 00:00:02.336 | 00:06:02.696 | First Videos | crop= 26 10 8 8
            .01 | 00:00:02.336 | 00:00:51.184 | Sandy in kitchen
            .02 | 00:00:51.218 | 00:02:41.728 | Dale in garden
        02 | 00:06:05.000 | 00:12:00.000 | Summer Vacation
    """)

    # 1. Spec -> ArchiveData
    original_data = read_tape_spec(spec_text)

    # 2. ArchiveData -> Matroska XML strings
    chapters_xml, tags_xml = generate_mkv_chapters_and_tags(original_data)

    # 3. Mock mkvextract calls for chapters and tags
    def subprocess_side_effect(cmd, **kwargs):
        cmd_str = " ".join(cmd)
        if "mkvextract" in cmd_str and "chapters" in cmd_str:
            return MagicMock(stdout=chapters_xml, returncode=0)
        elif "mkvextract" in cmd_str and "tags" in cmd_str:
            return MagicMock(stdout=tags_xml, returncode=0)
        return MagicMock(stdout="", returncode=0)

    mock_run.side_effect = subprocess_side_effect

    # 4. Extract XML via reader -> Reconstructed ArchiveData
    reconstructed_data = read_mkv_metadata("dummy_archive.mkv")

    # 5. Assert global attributes
    assert reconstructed_data.global_crop == "30 6 18 8"
    assert len(reconstructed_data.clips) == 2

    # 6. Assert parent Clip 01 & subchapter hierarchy
    clip1 = reconstructed_data.clips[0]
    assert clip1.title == "First Videos"
    assert clip1.crop == "26 10 8 8"
    assert len(clip1.subchapters) == 2

    sub1 = clip1.subchapters[0]
    assert sub1.title == "Sandy in kitchen"
    assert sub1.start == "00:00:02.336"
    assert sub1.end == "00:00:51.184"

    sub2 = clip1.subchapters[1]
    assert sub2.title == "Dale in garden"
    assert sub2.start == "00:00:51.218"
    assert sub2.end == "00:02:41.728"

    # 7. Assert parent Clip 02 inherits global crop
    clip2 = reconstructed_data.clips[1]
    assert clip2.title == "Summer Vacation"
    assert clip2.crop == "30 6 18 8"
    assert len(clip2.subchapters) == 0
