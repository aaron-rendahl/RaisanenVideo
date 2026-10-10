import os
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.dom import minidom
from pipeline.models import ArchiveData, Clip, Subchapter
from pipeline.utils import parse_crop_string
s
def read_mkv_metadata(mkv_path: str | Path) -> ArchiveData:
    """Subprocess I/O wrapper: extracts raw XML chapter/tag strings from an MKV file
    and delegates parsing to parse_mkv_xml_strings.
    """
    mkv_path = Path(mkv_path)
    if not mkv_path.exists():
        raise FileNotFoundError(f"MKV file not found: {mkv_path}")

    # Call mkvextract to extract chapters XML
    chapters_cmd = ["mkvextract", "chapters", str(mkv_path)]
    chapters_xml = subprocess.check_output(chapters_cmd, text=True)

    # Call mkvextract to extract tags XML
    tags_cmd = ["mkvextract", "tags", str(mkv_path)]
    tags_xml = subprocess.check_output(tags_cmd, text=True)

    # Delegate data reconstruction to the pure parser
    return parse_mkv_xml_strings(chapters_xml, tags_xml)


def parse_mkv_xml_strings(chapters_xml: str, tags_xml: str) -> ArchiveData:
    """Pure data processing: parses raw Matroska XML strings for chapters and tags
    and reconstructs the domain ArchiveData model matching the result from the
    'generate mkv chapters and tags' function.
    """
    chapter_tags = {}
    global_crop = ""
    has_global_title = False
    global_title_str = ""

    # 1. Parse Tags XML
    if tags_xml and tags_xml.strip():
        tags_root = ET.fromstring(tags_xml)
        for tag in tags_root.findall("Tag"):
            targets = tag.find("Targets")
            chap_uid = targets.findtext("ChapterUID") if targets is not None else None
            target_type = targets.findtext("TargetTypeValue") if targets is not None else ""

            tag_dict = {}
            for simple in tag.findall("Simple"):
                name = simple.findtext("Name", "").upper()
                val = simple.findtext("String", "")
                if name in ("CROP", "CROPPING", "GLOBAL_CROP"):
                    tag_dict["crop"] = val
                elif name in ("DATE", "DATE_RECORDED", "DATE_RELEASED", "GLOBAL_DATE"):
                    tag_dict["date"] = val
                elif name == "TITLE":
                    tag_dict["title"] = val

            if chap_uid:
                chapter_tags[chap_uid] = tag_dict
            else:
                # Global segment tags (TargetTypeValue == 50 or no ChapterUID)
                if "crop" in tag_dict:
                    global_crop = tag_dict["crop"]
                if "title" in tag_dict:
                    has_global_title = True
                    global_title_str = tag_dict["title"]
                if "date" in tag_dict:
                    global_date_str = tag_dict["date"]

    # 2. Parse Chapters XML
    clips = []
    has_nested_children = False
    top_level_atoms = []

    if chapters_xml and chapters_xml.strip():
        chap_root = ET.fromstring(chapters_xml)
        edition = chap_root.find("EditionEntry")

        if edition is not None:
            top_level_atoms = [elem for elem in list(edition) if elem.tag == "ChapterAtom"]

            # Check if any top-level atom has child ChapterAtoms (Multi-clip indicator)
            for parent_atom in top_level_atoms:
                child_atoms = [elem for elem in list(parent_atom) if elem.tag == "ChapterAtom"]
                if child_atoms:
                    has_nested_children = True
                    break

    # 3. Determine Mode
    # Multi-clip IF there are nested child atoms OR (multiple top-level atoms AND no global TITLE tag)
    is_multi_clip = has_nested_children or (len(top_level_atoms) > 1 and not has_global_title)

    if not is_multi_clip and chapters_xml and chapters_xml.strip():
        # Uncut Single-Clip Mode: top-level atoms ARE the subchapters
        subchapters = []
        for s_idx, atom in enumerate(top_level_atoms, start=1):
            s_uid = atom.findtext("ChapterUID")
            s_title = atom.findtext("ChapterDisplay/ChapterString", f"Subchapter {s_idx}")
            s_start = atom.findtext("ChapterTimeStart", "00:00:00.000000000")
            s_end = atom.findtext("ChapterTimeEnd", "")

            subchapters.append(
                Subchapter(
                    idx=f"01.{s_idx:02d}",
                    start=s_start[:12],
                    end=s_end[:12] if s_end else "",
                    title=s_title,
                )
            )

        # Reconstruct single MASTER clip containing all subchapters
        single_clip = Clip(
            idx="01",
            start="00:00:00.000",
            end="",
            title=global_title_str or "Master Tape",
            date=global_date_str or "",
            crop=global_crop,
            subchapters=subchapters,
        )
        clips = [single_clip]

    elif is_multi_clip:
        # Multi-Clip Mode: top-level atoms are parent clips with nested subchapters
        for c_idx, parent_atom in enumerate(top_level_atoms, start=1):
            p_uid = parent_atom.findtext("ChapterUID")
            p_title = parent_atom.findtext("ChapterDisplay/ChapterString", f"Clip {c_idx}")
            p_start = parent_atom.findtext("ChapterTimeStart", "00:00:00.000000000")
            p_end = parent_atom.findtext("ChapterTimeEnd", "")

            child_atoms = [elem for elem in list(parent_atom) if elem.tag == "ChapterAtom"]

            subchapters = []
            for s_idx, child_atom in enumerate(child_atoms, start=1):
                s_title = child_atom.findtext("ChapterDisplay/ChapterString", f"Subchapter {s_idx}")
                s_start = child_atom.findtext("ChapterTimeStart", "00:00:00.000000000")
                s_end = child_atom.findtext("ChapterTimeEnd", "")

                subchapters.append(
                    Subchapter(
                        idx=f"{c_idx:02d}.{s_idx:02d}",
                        start=s_start[:12],
                        end=s_end[:12] if s_end else "",
                        title=s_title,
                    )
                )

            p_tag_data = chapter_tags.get(p_uid, {})
            clips.append(
                Clip(
                    idx=f"{c_idx:02d}",
                    start=p_start[:12],
                    end=p_end[:12] if p_end else "",
                    title=p_title,
                    date=p_tag_data.get("date", ""),
                    crop=p_tag_data.get("crop", global_crop),
                    subchapters=subchapters,
                )
            )

    return ArchiveData(
        global_crop=global_crop,
        raw_spec="",
        clips=clips,
        is_multi_clip=is_multi_clip,
    )

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

    # Helper to generate chapter-level tag entries bound via ChapterUID
    def add_chapter_tags(chap_uid: str, crop_val: str = "", date_val: str = ""):
        # Determine if there is any chapter-specific metadata to write
        has_custom_crop = bool(crop_val and crop_val != data.global_crop)
        has_custom_date = bool(date_val)

        # Do not create an empty <Tag> element if there are no <Simple> children
        if not (has_custom_crop or has_custom_date):
            return

        c_tag = ET.SubElement(tags_root, "Tag")
        c_targets = ET.SubElement(c_tag, "Targets")
        ET.SubElement(c_targets, "ChapterUID").text = chap_uid
        ET.SubElement(c_targets, "TargetTypeValue").text = "50"

        if has_custom_date:
            s_date = ET.SubElement(c_tag, "Simple")
            ET.SubElement(s_date, "Name").text = "DATE_RECORDED"
            ET.SubElement(s_date, "String").text = date_val

        if has_custom_crop:
            s_crop = ET.SubElement(c_tag, "Simple")
            ET.SubElement(s_crop, "Name").text = "CROPPING"
            ET.SubElement(s_crop, "String").text = crop_val

    # 3. Write Chapter Atoms and Chapter-Level Tags
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

                add_chapter_tags(
                    sub_uid,
                    crop_val=getattr(sub, "crop", ""),
                    date_val=getattr(sub, "date", "")
                )
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

            add_chapter_tags(
                clip_uid,
                crop_val=getattr(clip, "crop", ""),
                date_val=getattr(clip, "date", "")
            )

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

                add_chapter_tags(
                    sub_uid,
                    crop_val=getattr(sub, "crop", ""),
                    date_val=getattr(sub, "date", "")
                )

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

