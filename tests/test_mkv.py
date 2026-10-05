"""
tests/test_spec.py / tests/test_mkv.py

Unit tests for mkv_writer.py (Matroska Chapter & Tag XML Generation).
"""

import textwrap
from pathlib import Path
import pytest

from mkv_writer import generate_mkv_chapters_and_tags
from spec_reader import read_tape_spec
from spec_writer import write_tape_spec


def test_mkv_xml_generation_single_clip_master():
    """Verifies that a Single-Clip Master ArchiveData generates valid Matroska XML structure."""
    spec_text = textwrap.dedent("""
        TITLE = Willy’s 40th Birthday Party
        GLOBAL_DATE = 1987-09-19
        GLOBAL_CROP = 12 24 0 8

        01 | 00:00:01.168 | arrival
        02 | 00:02:12.366 | kids dance
    """)

    parsed_data = read_tape_spec(spec_text)
    chapters_xml, tags_xml = generate_mkv_chapters_and_tags(parsed_data)

    # Verify Chapter XML elements
    assert "<Chapters>" in chapters_xml
    assert "<EditionEntry>" in chapters_xml
    assert "<ChapterAtom>" in chapters_xml
    assert "</Chapters>" in chapters_xml

    # Verify Tag XML elements
    assert "<Tags>" in tags_xml
    assert "<Tag>" in tags_xml
    assert "</Tags>" in tags_xml


def test_mkv_xml_generation_multi_clip_mode():
    """Verifies that Multi-Clip mode generates distinct chapter entries."""
    spec_text = textwrap.dedent("""
        GLOBAL_CROP = 12 24 0 8

        01 | First Videos
        01.1 | 00:00:02.336 | 00:00:51.184 | Sandy in kitchen
        01.2 | 00:00:51.218 | 00:02:41.728 | Dale in garden

        07 | 01:01:51.942 | 01:11:14.804 | birthday party
    """)

    parsed_data = read_tape_spec(spec_text)
    chapters_xml, tags_xml = generate_mkv_chapters_and_tags(parsed_data)

    assert "<Chapters>" in chapters_xml
    assert "<ChapterString>Sandy in kitchen</ChapterString>" in chapters_xml
    assert "<ChapterString>birthday party</ChapterString>" in chapters_xml


def test_mkv_roundtrip_spec_writing():
    """Verifies that write_tape_spec outputs non-empty spec strings for reconstructed models."""
    spec_text = textwrap.dedent("""
        TITLE = Willy’s 40th Birthday Party
        GLOBAL_DATE = 1987-09-19

        01 | 00:00:01.168 | arrival
    """)

    parsed_data = read_tape_spec(spec_text)
    recreated_spec_text = write_tape_spec(parsed_data)

    assert len(recreated_spec_text.strip()) > 0
    reparsed_data = read_tape_spec(recreated_spec_text)
    assert len(reparsed_data.clips) == len(parsed_data.clips)
