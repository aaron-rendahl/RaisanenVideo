import re
from dataclasses import dataclass
from pathlib import Path

from pipeline.models import Clip, Subchapter

def sanitize(title: str) -> str:
    """Converts titles into clean, filesystem-safe string segments."""
    if not title:
        return "untitled"
    cleaned = re.sub(r"['’\"]", "", title)
    cleaned = re.sub(r"[^a-zA-Z0-9\-]", " ", cleaned)
    cleaned = re.sub(r"\s+", "_", cleaned.strip())
    return cleaned.strip("_-") or "untitled"

@dataclass
class PipelinePaths:
    base: Path
    vid: str
    path_archive_mkv: Path
    path_specs: Path
    path_main_sh: Path
    clips: Path
    frames: Path   
    log: Path
    metadata: Path
    scenes: Path
    scripts: Path

    @classmethod
    def from_vid(cls, base_dir: Path, vid: str) -> "PipelinePaths":
        """Factory to create all workspace paths given a video ID and base directory."""
        base = base_dir.resolve()
        prep = base / "04_prep" / vid
        return cls(
            base = base,
            vid = vid,
            path_archive_mkv = base / "01_archive" / f"{vid}.mkv",
            path_specs       = base / "03_specs" / f"{vid}.txt",
            clips    = base / "02_clips" / vid,
            frames   = prep / "frames",
            log      = prep / "log",
            metadata = prep / "metadata",
            scenes   = prep / "scenes",
            scripts  = prep / "scripts",
            path_main_sh = prep / "scripts" / "00-run_pipeline.sh"
        )

    def ensure_exists(self) -> None:
        """Creates all workspace directories if they do not exist."""
        directories = [
            self.clips,
            self.frames,
            self.log,
            self.metadata,
            self.scenes,
            self.scripts,
        ]
        for d in directories:
            if d is not None:
                d.mkdir(parents=True, exist_ok=True)

    def rel_path(self, path: Path) -> str:
        """Returns path string relative to project base directory if possible."""
        try:
            return str(path.resolve().relative_to(self.base))
        except ValueError:
            return str(path)

    def scene_paths(
        self, 
        scene: Subchapter | Clip, 
    ) -> dict[str, str]:
        """Returns all resolved path strings required for a scene."""
        title = sanitize(scene.title)
        short_id = f"{scene.idx}-{title}"
        long_id  = f"{self.vid}-{short_id}"
        return {
            "path_archive_mkv": str(self.path_archive_mkv.resolve()),
            "path_temp_mkv":    str((self.scenes  / f"{long_id}_TEMP.mkv").resolve()),
            "path_scene_mp4":   str((self.scenes  / f"{long_id}.mp4").resolve()),
            "path_scene_sh":    str((self.scripts / f"{short_id}.sh").resolve()),
        }

    def clip_paths(
      self, 
      clip: Clip
    ) -> dict[str, str]:
        """Returns all resolved path strings required for a clip."""
        title = sanitize(clip.title)
        short_id = f"{clip.idx}-{title}"
        long_id  = f"{self.vid}-{short_id}"

        return {
            "path_clip_mp4":   str((self.clips    / f"{long_id}.mp4").resolve()),
            "path_spacer_mp4": str((self.scenes   / f"{long_id}-black.mp4").resolve()),
            "path_clip_sh":    str((self.scripts  / f"{short_id}-concat.sh").resolve()),
            "path_spacer_sh":  str((self.scripts  / f"{short_id}-black.sh").resolve()),
            "path_manifest":   str((self.metadata / f"{short_id}-manifest.txt").resolve()),
            "path_metadata":   str((self.metadata / f"{short_id}-metadata.txt").resolve()),
        }
