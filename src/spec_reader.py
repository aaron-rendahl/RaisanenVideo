from models import ArchiveData, Clip, Subchapter


def read_tape_spec(text_content: str) -> ArchiveData:
    global_crop = ""
    global_date = ""
    tape_title = ""
    clips = []
    warnings = []

    lines = text_content.splitlines()

    # Pass 1: Extract Key-Value Directives
    body_lines = []
    for line_num, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            if stripped.startswith("## Crop:"):
                global_crop = stripped.replace("## Crop:", "").strip()
            continue

        if "=" in stripped and "|" not in stripped:
            key, val = stripped.split("=", 1)
            key_clean = key.strip().replace(" ", "_").upper()
            if key_clean == "TITLE":
                tape_title = val.strip()
                continue
            elif key_clean in ("GLOBAL_CROP", "CROP"):
                global_crop = val.strip()
                continue
            elif key_clean in ("GLOBAL_DATE", "DATE"):
                global_date = val.strip()
                continue

        body_lines.append((line_num, stripped))

    # Helper to parse timestamp parts
    def parse_timestamp_line(p_list):
        s_time = p_list[1]
        if len(p_list) > 3:
            e_time = p_list[2]
            title = p_list[3]
        elif len(p_list) == 3:
            if ":" in p_list[2]:
                e_time = p_list[2]
                title = ""
            else:
                e_time = ""
                title = p_list[2]
        else:
            e_time = ""
            title = ""
        return s_time, e_time, title

    def parse_kv_extras(p_list, default_date, default_crop):
        d, c = default_date, default_crop
        for extra in p_list:
            if extra.startswith("date="):
                d = extra.split("=", 1)[1].strip()
            elif extra.startswith("crop="):
                c = extra.split("=", 1)[1].strip()
        return d, c

    # Pass 2: Parse Body Lines
    current_clip = None

    # If top-level TITLE is present, create the single Master Clip automatically
    if tape_title:
        current_clip = Clip(
            idx="MASTER",
            start="",
            end="",
            title=tape_title,
            date=global_date,
            crop=global_crop,
        )
        clips.append(current_clip)

    for line_num, stripped in body_lines:
        parts = [p.strip() for p in stripped.split("|")]
        idx = parts[0]
        is_timestamp_line = len(parts) > 1 and ":" in parts[1]

        # Case A: Subchapters under top-level TITLE or parent clip
        if tape_title and is_timestamp_line:
            s_time, e_time, sub_title = parse_timestamp_line(parts)
            sub = Subchapter(idx=idx, start=s_time, end=e_time, title=sub_title)
            current_clip.subchapters.append(sub)

        elif "." in idx:
            s_time, e_time, sub_title = parse_timestamp_line(parts)
            sub = Subchapter(idx=idx, start=s_time, end=e_time, title=sub_title)
            if current_clip:
                current_clip.subchapters.append(sub)
            else:
                warnings.append(
                    f"Line {line_num}: Subchapter {idx} found before parent clip."
                )

        # Case B: Multi-clip mode parent headers or standalone clips
        elif is_timestamp_line:
            idx_num = idx if idx.isdigit() else f"{len(clips)+1:02d}"
            s_time, e_time, title = parse_timestamp_line(parts)
            clip_date, clip_crop = parse_kv_extras(
                parts[3:], global_date, global_crop
            )

            current_clip = Clip(
                idx=idx_num,
                start=s_time,
                end=e_time,
                title=title or f"Clip {idx_num}",
                date=clip_date,
                crop=clip_crop,
            )
            clips.append(current_clip)
        else:
            idx_num = idx if idx.isdigit() else f"{len(clips)+1:02d}"
            title = parts[1] if len(parts) > 1 else parts[0]
            clip_date, clip_crop = parse_kv_extras(
                parts[2:], global_date, global_crop
            )

            current_clip = Clip(
                idx=idx_num,
                start="",
                end="",
                title=title,
                date=clip_date,
                crop=clip_crop,
            )
            clips.append(current_clip)

    # Post-Processing: Auto-chaining end timestamps
    chronological_sequence = []
    for clip in clips:
        if clip.subchapters:
            chronological_sequence.extend(clip.subchapters)
        elif clip.start:
            chronological_sequence.append(clip)

    for i in range(len(chronological_sequence) - 1):
        if not chronological_sequence[i].end:
            chronological_sequence[i].end = chronological_sequence[i + 1].start

    for clip in clips:
        clip.crop = clip.crop if clip.crop else global_crop
        clip.date = clip.date if clip.date else global_date

        if clip.subchapters:
            clip.start = clip.subchapters[0].start
            clip.end = clip.subchapters[-1].end

    return ArchiveData(
        global_crop=global_crop,
        global_date=global_date,
        raw_spec=text_content.strip(),
        clips=clips,
        warnings=warnings,
    )
