# src/mkv_reader.py

import subprocess
import xml.etree.ElementTree as ET
from models import ArchiveData, Clip, Subchapter


def read_mkv_metadata(mkv_path: str) -> ArchiveData:
    """Extracts native Matroska Chapters and Tags XML directly via mkvextract.

    Supports both multi-clip nested parent/child hierarchies and single-clip top-level subchapters.
    """
    chap_cmd = ["mkvextract", "chapters", mkv_path]
    chap_res = subprocess.run(chap_cmd, capture_output=True, text=True, check=True)

    tags_cmd = ["mkvextract", "tags", mkv_path]
    tags_res = subprocess.run(tags_cmd, capture_output=True, text=True, check=True)

    global_crop = ""
    chapter_tags = {}  # chap_uid -> {"crop": ..., "date": ...}

    if tags_res.stdout.strip():
        tags_root = ET.fromstring(tags_res.stdout)
        for tag in tags_root.findall("Tag"):
            chap_uid = tag.findtext("Targets/ChapterUID")
            crop_val = ""
            date_val = ""

            for simple in tag.findall("Simple"):
                name = simple.findtext("Name")
                string_val = simple.findtext("String")
                if name == "CROPPING":
                    crop_val = string_val
                elif name == "DATE_RECORDED":
                    date_val = string_val

            if chap_uid:
                chapter_tags[chap_uid] = {"crop": crop_val, "date": date_val}
            else:
                if crop_val:
                    global_crop = crop_val

    clips = []
    if chap_res.stdout.strip():
        chap_root = ET.fromstring(chap_res.stdout)
        edition = chap_root.find("EditionEntry")

        if edition is not None:
            top_level_atoms = [elem for elem in list(edition) if elem.tag == "ChapterAtom"]

            for c_idx, parent_atom in enumerate(top_level_atoms, start=1):
                p_uid = parent_atom.findtext("ChapterUID")
                p_title = parent_atom.findtext("ChapterDisplay/ChapterString", f"Clip {c_idx}")
                p_start = parent_atom.findtext("ChapterTimeStart", "00:00:00.000000000")
                p_end = parent_atom.findtext("ChapterTimeEnd", "")

                child_atoms = [elem for elem in list(parent_atom) if elem.tag == "ChapterAtom"]

                subchapters = []
                for s_idx, child_atom in enumerate(child_atoms, start=1):
                    s_uid = child_atom.findtext("ChapterUID")
                    s_title = child_atom.findtext("ChapterDisplay/ChapterString", f"Subchapter {s_idx}")
                    s_start = child_atom.findtext("ChapterTimeStart", "00:00:00.000000000")
                    s_end = child_atom.findtext("ChapterTimeEnd", "")
                    s_tag_data = chapter_tags.get(s_uid, {})

                    subchapters.append(
                        Subchapter(
                            idx=f"{s_idx:02d}",
                            start=s_start[:12],
                            end=s_end[:12] if s_end else "",
                            title=s_title,
                            crop=s_tag_data.get("crop", ""),
                            date=s_tag_data.get("date", ""),
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
    )
