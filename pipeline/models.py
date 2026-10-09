import dataclasses
from typing import List


@dataclasses.dataclass
class Subchapter:
    idx: str
    start: str
    end: str
    title: str


@dataclasses.dataclass
class Clip:
    idx: str
    start: str
    end: str
    title: str
    date: str
    crop: str
    subchapters: List[Subchapter] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class ArchiveData:
    global_crop: str = ""
    global_date: str = ""
    raw_spec: str = ""
    clips: List[Clip] = dataclasses.field(default_factory=list)
    warnings: List[str] = dataclasses.field(default_factory=list)

    @property
    def is_multi_clip(self) -> bool:
        """Returns True if there are 2 or more clips in the archive data."""
        return len(self.clips) > 1

    def print_warnings(self):
        """Prints all collected spec warnings in a prominent banner."""
        if self.warnings:
            print("\n" + "⚠️  " * 3 + " SPEC WARNINGS " + "⚠️  " * 3)
            for w in self.warnings:
                print(f"  - {w}")

    def resolve_missing_end_times(self, total_duration: str):
        """Fills any remaining empty end timestamps with total_duration."""
        if not self.clips:
            return

        last_clip = self.clips[-1]

        if last_clip.subchapters and not last_clip.subchapters[-1].end:
            last_clip.subchapters[-1].end = total_duration
            last_clip.end = total_duration
        elif not last_clip.end:
            last_clip.end = total_duration


import re
from pathlib import Path
from typing import List, Dict, Any

def timestamp_to_seconds(ts: str) -> float:
    """Converts 'HH:MM:SS.mmm' or 'MM:SS.mmm' string to float seconds."""
    if not ts:
        return 0.0
    parts = ts.strip().split(':')
    if len(parts) == 3:
        h, m, s = parts
        return float(h) * 3600 + float(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return float(m) * 60 + float(s)
    return float(parts[0])


def sanitize_filename(title: str) -> str:
    """Converts titles into clean, filesystem-safe string segments."""
    if not title:
        return "untitled"
    # Replace spaces with underscores and remove non-alphanumeric/hyphen/underscore chars
    cleaned = re.sub(r'\s+', '_', title.strip())
    cleaned = re.sub(r'[^a-zA-Z0-9_\-]', '', cleaned)
    return cleaned.strip('_') or "untitled"
