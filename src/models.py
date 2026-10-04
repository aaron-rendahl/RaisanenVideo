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
