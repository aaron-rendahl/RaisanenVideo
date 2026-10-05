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


def test_mkv_xml_chapter_cropping_tag_targeting():
    """Verifies that chapter-specific crop overrides generate a <Tag> entry

    explicitly bound to the corresponding <ChapterUID>.
    """
    spec_text = textwrap.dedent("""
        GLOBAL_CROP = 30 6 18 8

        01 | 00:00:08.108 | 00:12:33.319 | BWCA | crop= 26 10 8 8
        02 | 00:12:55.241 | 00:13:32.278 | kids playing
    """)

    parsed_data = read_tape_spec(spec_text)
    chapters_xml, tags_xml = generate_mkv_chapters_and_tags(parsed_data)

    # 1. Global crop tag assertion (TargetTypeValue 50 / file-level)
    assert "<Name>CROPPING</Name>" in tags_xml
    assert "<String>30 6 18 8</String>" in tags_xml

    # 2. Chapter-specific crop tag assertion
    assert "<String>26 10 8 8</String>" in tags_xml
    assert "<ChapterUID>" in tags_xml

def test_mkv_xml_no_empty_tags_when_inheriting_global_crop():
    """Verifies that chapters inheriting global crop settings do not generate empty <Tag> blocks."""
    spec_text = textwrap.dedent("""
        GLOBAL_CROP = 30 6 18 8

        01 | 00:00:08.108 | 00:12:33.319 | BWCA
    """)

    parsed_data = read_tape_spec(spec_text)
    chapters_xml, tags_xml = generate_mkv_chapters_and_tags(parsed_data)

    # Global crop tag should exist
    assert "<String>30 6 18 8</String>" in tags_xml

    # No ChapterUID-targeted tags should exist because Chapter 01 has no overrides
    assert "<ChapterUID>" not in tags_xml
