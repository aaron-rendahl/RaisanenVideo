import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from models import ArchiveData, Clip, Subchapter


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
    and reconstructs the domain ArchiveData model matching generate_mkv_chapters_and_tags.
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
