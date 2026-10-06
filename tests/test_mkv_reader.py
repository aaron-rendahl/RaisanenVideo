"""tests/test_mkv_reader.py

Unit tests for mkv_reader.py XML parsing.
"""

import textwrap
from mkv_reader import parse_mkv_xml_strings


def test_read_mkv_metadata_parses_mkvextract_xml():
    """Verifies that parse_mkv_xml_strings extracts chapters and tags from raw XML strings."""
    chapters_xml = textwrap.dedent("""
        <Chapters>
          <EditionEntry>
            <ChapterAtom>
              <ChapterUID>1000</ChapterUID>
              <ChapterTimeStart>00:00:01.168000000</ChapterTimeStart>
              <ChapterTimeEnd>00:02:12.366000000</ChapterTimeEnd>
              <ChapterDisplay>
                <ChapterString>Arrival</ChapterString>
              </ChapterDisplay>
            </ChapterAtom>
            <ChapterAtom>
              <ChapterUID>1001</ChapterUID>
              <ChapterTimeStart>00:02:12.366000000</ChapterTimeStart>
              <ChapterTimeEnd>00:04:41.548000000</ChapterTimeEnd>
              <ChapterDisplay>
                <ChapterString>Kids Dance</ChapterString>
              </ChapterDisplay>
            </ChapterAtom>
          </EditionEntry>
        </Chapters>
    """)

    tags_xml = textwrap.dedent("""
        <Tags>
          <Tag>
            <Targets>
              <TargetTypeValue>50</TargetTypeValue>
            </Targets>
            <Simple>
              <Name>CROPPING</Name>
              <String>12 24 0 8</String>
            </Simple>
          </Tag>
          <Tag>
            <Targets>
              <ChapterUID>1000</ChapterUID>
              <TargetTypeValue>50</TargetTypeValue>
            </Targets>
            <Simple>
              <Name>DATE_RECORDED</Name>
              <String>1987-09-19</String>
            </Simple>
          </Tag>
        </Tags>
    """)

    data = parse_mkv_xml_strings(chapters_xml, tags_xml)

    assert data.global_crop == "12 24 0 8"
    assert len(data.clips) == 2
    assert data.clips[0].title == "Arrival"
    assert data.clips[0].date == "1987-09-19"
    assert data.clips[1].title == "Kids Dance"
