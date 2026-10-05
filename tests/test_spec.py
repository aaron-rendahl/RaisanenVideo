"""
tests/test_spec.py

Unit tests verifying spec_reader.py and spec_writer.py against
actual multi-clip and single-clip tape spec conventions.
"""

import textwrap
from models import ArchiveData
from spec_reader import read_tape_spec
from spec_writer import write_tape_spec


def test_spec_reader_multi_clip_with_subchapters_and_single_chapters():
    """Verifies multi-clip mode (no top-level TITLE) with parent headers,

    subchapters, and standalone single-chapter clips.
    """
    spec_text = textwrap.dedent("""
        GLOBAL_CROP = 12 24 0 8

        01 | First Videos
        01.1 | 00:00:02.336 | 00:00:51.184 | Sandy in kitchen
        01.2 | 00:00:51.218 | 00:02:41.728 | Dale in garden
        01.3 | 00:02:41.795 | 00:03:44.191 | kids in kitchen

        07 | 01:01:51.942 | 01:11:14.804 | birthday party
    """)

    data = read_tape_spec(spec_text)

    assert len(data.warnings) == 0
    assert data.global_crop == "12 24 0 8"
    assert len(data.clips) == 2

    # Clip 1: Parent clip with 3 subchapters
    clip1 = data.clips[0]
    assert clip1.idx == "01"
    assert clip1.title == "First Videos"
    assert len(clip1.subchapters) == 3
    assert clip1.subchapters[0].idx == "01.1"
    assert clip1.subchapters[0].title == "Sandy in kitchen"
    assert clip1.subchapters[2].title == "kids in kitchen"

    # Clip 7: Single-chapter clip
    clip7 = data.clips[1]
    assert clip7.idx == "07"
    assert clip7.title == "birthday party"
    assert clip7.start == "01:01:51.942"
    assert clip7.end == "01:11:14.804"
    assert len(clip7.subchapters) == 0


def test_spec_reader_single_clip_master_tape():
    """Verifies single-clip master tape mode (TITLE set, integer indices,

    auto-chained end timestamps).
    """
    spec_text = textwrap.dedent("""
        TITLE = Willy’s 40th Birthday Party
        GLOBAL_DATE = 1987-09-19
        GLOBAL_CROP = 12 24 0 8

        01 | 00:00:01.168 | arrival
        02 | 00:02:12.366 | kids dance
        03 | 00:04:41.548 | social time and presents
    """)

    data = read_tape_spec(spec_text)

    assert len(data.warnings) == 0
    assert data.global_date == "1987-09-19"
    assert data.global_crop == "12 24 0 8"
    assert len(data.clips) == 1

    master_clip = data.clips[0]
    assert master_clip.idx == "MASTER"
    assert master_clip.title == "Willy’s 40th Birthday Party"
    assert len(master_clip.subchapters) == 3

    # Check integer subchapter indexing and auto-chained end times
    sub1 = master_clip.subchapters[0]
    assert sub1.idx == "01"
    assert sub1.start == "00:00:01.168"
    assert sub1.end == "00:02:12.366"  # Auto-chained from 02's start
    assert sub1.title == "arrival"

    sub2 = master_clip.subchapters[1]
    assert sub2.idx == "02"
    assert sub2.start == "00:02:12.366"
    assert sub2.end == "00:04:41.548"  # Auto-chained from 03's start
    assert sub2.title == "kids dance"


def test_spec_reader_orphan_subchapter_warning():
    """Verifies that an orphan subchapter (e.g. 01.1 without a preceding 01 clip header

    or TITLE) logs a warning.
    """
    spec_text = textwrap.dedent("""
        01.1 | 00:00:02.336 | 00:00:51.184 | Sandy in kitchen
    """)

    data = read_tape_spec(spec_text)

    assert len(data.warnings) == 1
    assert "Subchapter 01.1 found before parent clip" in data.warnings[0]


def test_spec_roundtrip_integrity():
    """Verifies that parsing a spec, serializing it via write_tape_spec,

    and re-parsing yields identical data models.
    """
    original_spec = textwrap.dedent("""
        TITLE = Willy’s 40th Birthday Party
        GLOBAL_DATE = 1987-09-19
        GLOBAL_CROP = 12 24 0 8

        01 | 00:00:01.168 | arrival
        02 | 00:02:12.366 | kids dance
    """)

    parsed_1 = read_tape_spec(original_spec)
    written_text = write_tape_spec(parsed_1)
    parsed_2 = read_tape_spec(written_text)

    assert len(parsed_1.clips) == len(parsed_2.clips)
    assert (
        parsed_1.clips[0].subchapters[0].title
        == parsed_2.clips[0].subchapters[0].title
    )
    assert (
        parsed_1.clips[0].subchapters[0].start
        == parsed_2.clips[0].subchapters[0].start
    )


def test_spec_roundtrip_writing():
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
