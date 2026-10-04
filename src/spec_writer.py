from models import ArchiveData


def write_tape_spec(data: ArchiveData) -> str:
    lines = []

    # 1. Mode Check: Single-Tape Uncut Mode
    is_uncut_mode = (
        len(data.clips) == 1
        and data.clips[0].idx in ("", "MASTER")
    )

    # 2. Header Directives Block
    if is_uncut_mode:
        master = data.clips[0]
        lines.append(f"TITLE = {master.title}")

    if data.global_date:
        lines.append(f"GLOBAL_DATE = {data.global_date}")
    if data.global_crop:
        lines.append(f"GLOBAL_CROP = {data.global_crop}")

    lines.append("")

    # 3. Body Serialization
    if is_uncut_mode:
        master = data.clips[0]
        for sub in master.subchapters:
            if sub.end:
                lines.append(f"{sub.idx} | {sub.start} | {sub.end} | {sub.title}")
            else:
                lines.append(f"{sub.idx} | {sub.start} | {sub.title}")
    else:
        for clip in data.clips:
            extras = []
            if clip.date and clip.date != data.global_date:
                extras.append(f"date={clip.date}")
            if clip.crop and clip.crop != data.global_crop:
                extras.append(f"crop={clip.crop}")

            extra_str = (" | " + " | ".join(extras)) if extras else ""

            if clip.subchapters:
                lines.append(f"{clip.idx} | {clip.title}{extra_str}")
                for sub in clip.subchapters:
                    if sub.end:
                        lines.append(
                            f"{sub.idx} | {sub.start} | {sub.end} | {sub.title}"
                        )
                    else:
                        lines.append(f"{sub.idx} | {sub.start} | {sub.title}")
            else:
                if clip.end:
                    lines.append(
                        f"{clip.idx} | {clip.start} | {clip.end} | {clip.title}{extra_str}"
                    )
                else:
                    lines.append(
                        f"{clip.idx} | {clip.start} | {clip.title}{extra_str}"
                    )

            lines.append("")

    return "\n".join(lines).rstrip() + "\n"
