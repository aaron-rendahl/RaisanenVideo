"""tests/test_mkv.py

Integration round-trip tests for Matroska container metadata (Writer <-> Reader).
"""

import textwrap
from mkv_reader import parse_mkv_xml_strings
from mkv_writer import generate_mkv_chapters_and_tags
from spec_reader import read_tape_spec


def test_mkv_xml_writer_reader_roundtrip():
    """Verifies complete round-trip fidelity directly in Python (zero mocks/subprocesses):
    
    Spec -> ArchiveData -> mkv_writer XML -> parse_mkv_xml_strings -> ArchiveData
    """
    spec_text = textwrap.dedent("""
        GLOBAL_DATE = 1987-05-10
        GLOBAL_CROP = 30 6 18 8
    
        01 | First Videos | crop= 26 10 8 8
        01.01 | 00:00:02.336 | 00:00:51.184 | Sandy in kitchen
        01.02 | 00:00:51.218 | 00:02:41.728 | Dale in garden
        02 | 00:06:05.000 | 00:12:00.000 | Summer Vacation
    """)
    
    # 1. Spec -> ArchiveData
    original_data = read_tape_spec(spec_text)
    
    # 2. ArchiveData -> Matroska XML strings
    chapters_xml, tags_xml = generate_mkv_chapters_and_tags(original_data)
    
    # 3. Parse XML strings directly without subprocess calls
    reconstructed_data = parse_mkv_xml_strings(chapters_xml, tags_xml)
    
    # 4. Assert global attributes
    assert reconstructed_data.global_crop == "30 6 18 8"
    assert len(reconstructed_data.clips) == 2
    
    # 5. Assert Clip 01 & subchapters
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
    
    # 6. Assert Clip 02
    clip2 = reconstructed_data.clips[1]
    assert clip2.title == "Summer Vacation"
    assert clip2.crop == "30 6 18 8"
    assert len(clip2.subchapters) == 0
