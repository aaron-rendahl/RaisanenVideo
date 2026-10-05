import os
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from xml.dom import minidom
from models import ArchiveData, Clip, Subchapter


def format_mkv_timestamp(ts: str) -> str:
    """Converts HH:MM:SS.mmm or HH:MM:SS to Matroska HH:MM:SS.nanoseconds format."""
    if not ts:
        return "00:00:00.000000000"

    parts = ts.split(".")
    time_part = parts[0]

    t_parts = time_part.split(":")
    if len(t_parts) == 2:
        time_part = f"00:{t_parts[0]}:{t_parts[1]}"

    ms_part = parts[1] if len(parts) > 1 else "0"
    ms_padded = ms_part.ljust(9, "0")[:9]

    return f"{time_part}.{ms_padded}"


def parse_crop_string(crop_str: str):
    """Parses 'Top Bottom Left Right' or 'Top|Bottom|Left|Right' spec string into (top, bottom, left, right)."""
    if not crop_str:
        return None
    try:
        delimiter = "|" if "|" in crop_str else " "
        parts = [int(p.strip()) for p in crop_str.split(delimiter) if p.strip()]
        if len(parts) == 4:
            return parts[0], parts[1], parts[2], parts[3]
    except ValueError:
        pass
    return None

def generate_mkv_chapters_and_tags(data: ArchiveData):
    """Generates Matroska XML chapters and tags from ArchiveData."""
    chapters_root = ET.Element("Chapters")
    edition = ET.SubElement(chapters_root, "EditionEntry")
    ET.SubElement(edition, "EditionFlagDefault").text = "1"

    tags_root = ET.Element("Tags")
    uid_counter = 1000

    # 1. Check Mode: Single-clip uncut master tape vs Multi-clip tape
    is_uncut_mode = (
        len(data.clips) == 1
        and data.clips[0].idx in ("", "MASTER", "01")
    )

    # 2. Global Segment Tags (TargetTypeValue = 50)
    if data.global_date or data.global_crop or (is_uncut_mode and data.clips[0].title):
        g_tag = ET.SubElement(tags_root, "Tag")
        g_targets = ET.SubElement(g_tag, "Targets")
        ET.SubElement(g_targets, "TargetTypeValue").text = "50"

        if is_uncut_mode and data.clips[0].title:
            simple_title = ET.SubElement(g_tag, "Simple")
            ET.SubElement(simple_title, "Name").text = "TITLE"
            ET.SubElement(simple_title, "String").text = data.clips[0].title

        if data.global_date:
            simple_date = ET.SubElement(g_tag, "Simple")
            ET.SubElement(simple_date, "Name").text = "DATE_RECORDED"
            ET.SubElement(simple_date, "String").text = data.global_date

        if data.global_crop:
            simple_crop = ET.SubElement(g_tag, "Simple")
            ET.SubElement(simple_crop, "Name").text = "CROPPING"
            ET.SubElement(simple_crop, "String").text = data.global_crop

    # 3. Write Chapter Atoms
    for clip in data.clips:
        if is_uncut_mode and clip.subchapters:
            # Uncut single-tape mode: Emit subchapters directly at top level
            for sub in clip.subchapters:
                sub_uid = str(uid_counter)
                uid_counter += 1

                sub_atom = ET.SubElement(edition, "ChapterAtom")
                ET.SubElement(sub_atom, "ChapterUID").text = sub_uid
                ET.SubElement(
                    sub_atom, "ChapterTimeStart"
                ).text = format_mkv_timestamp(sub.start)
                if sub.end:
                    ET.SubElement(
                        sub_atom, "ChapterTimeEnd"
                    ).text = format_mkv_timestamp(sub.end)

                sub_display = ET.SubElement(sub_atom, "ChapterDisplay")
                ET.SubElement(sub_display, "ChapterString").text = sub.title
                ET.SubElement(sub_display, "ChapterLanguage").text = "eng"
        else:
            # Multi-clip mode: Parent clip Atom with nested child subchapters
            clip_uid = str(uid_counter)
            uid_counter += 1

            clip_atom = ET.SubElement(edition, "ChapterAtom")
            ET.SubElement(clip_atom, "ChapterUID").text = clip_uid
            ET.SubElement(
                clip_atom, "ChapterTimeStart"
            ).text = format_mkv_timestamp(clip.start)
            if clip.end:
                ET.SubElement(
                    clip_atom, "ChapterTimeEnd"
                ).text = format_mkv_timestamp(clip.end)

            display = ET.SubElement(clip_atom, "ChapterDisplay")
            ET.SubElement(display, "ChapterString").text = clip.title
            ET.SubElement(display, "ChapterLanguage").text = "eng"

            for sub in clip.subchapters:
                sub_uid = str(uid_counter)
                uid_counter += 1

                sub_atom = ET.SubElement(clip_atom, "ChapterAtom")
                ET.SubElement(sub_atom, "ChapterUID").text = sub_uid
                ET.SubElement(
                    sub_atom, "ChapterTimeStart"
                ).text = format_mkv_timestamp(sub.start)
                if sub.end:
                    ET.SubElement(
                        sub_atom, "ChapterTimeEnd"
                    ).text = format_mkv_timestamp(sub.end)

                sub_display = ET.SubElement(sub_atom, "ChapterDisplay")
                ET.SubElement(sub_display, "ChapterString").text = sub.title
                ET.SubElement(sub_display, "ChapterLanguage").text = "eng"

    chapters_xml = minidom.parseString(
        ET.tostring(chapters_root, encoding="utf-8")
    ).toprettyxml(indent="  ")
    tags_xml = minidom.parseString(
        ET.tostring(tags_root, encoding="utf-8")
    ).toprettyxml(indent="  ")

    return chapters_xml, tags_xml


def write_mkv_metadata(mkv_path: str, data: ArchiveData) -> None:
    """In-place updates an MKV file's title, chapters, tags, and native video track crop fields using mkvpropedit."""
    chapters_xml, tags_xml = generate_mkv_chapters_and_tags(data)

    with tempfile.TemporaryDirectory() as tmpdir:
        chap_file = os.path.join(tmpdir, "chapters.xml")
        tags_file = os.path.join(tmpdir, "tags.xml")

        with open(chap_file, "w", encoding="utf-8") as f:
            f.write(chapters_xml)

        with open(tags_file, "w", encoding="utf-8") as f:
            f.write(tags_xml)

        cmd = [
            "mkvpropedit",
            mkv_path,
            "--chapters",
            chap_file,
            "--tags",
            f"all:{tags_file}",
        ]

        # Explicitly set segment title header in mkvpropedit
        is_uncut_mode = (
            len(data.clips) == 1
            and data.clips[0].idx in ("", "MASTER", "01")
        )
        if is_uncut_mode and data.clips[0].title:
            cmd.extend(["--edit", "info", "--set", f"title={data.clips[0].title}"])

        # Track cropping execution...
        crop_vals = parse_crop_string(data.global_crop)
        if crop_vals:
            top, bottom, left, right = crop_vals
            cmd.extend(
                [
                    "--edit",
                    "track:v1",
                    "--set",
                    f"pixel-crop-top={top}",
                    "--set",
                    f"pixel-crop-bottom={bottom}",
                    "--set",
                    f"pixel-crop-left={left}",
                    "--set",
                    f"pixel-crop-right={right}",
                ]
            )

        subprocess.run(cmd, check=True)

