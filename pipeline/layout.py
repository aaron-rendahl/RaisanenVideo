# pipeline/layout.py
from pathlib import Path


class PipelineDirs:

    def __init__(self, base_dir: Path, vid: str):
        self.base_dir = base_dir.resolve()
        self.vid = vid
        self.prep = self.base_dir / "04_prep" / vid

        self.originals = self.base_dir / "00_originals"
        self.archive = self.base_dir / "01_archive"
        self.clips = self.base_dir / "02_clips" / vid
        self.specs = self.base_dir / "03_specs"

        self.scenes = self.prep / "scenes"
        self.scripts = self.prep / "scripts"
        self.metadata = self.prep / "metadata"
        self.log = self.prep / "log"
        self.frames = self.prep / "frames"

    def ensure_exists(self) -> None:
        for d in [
            self.clips,
            self.scenes,
            self.scripts,
            self.metadata,
            self.log,
            self.frames,
        ]:
            d.mkdir(parents=True, exist_ok=True)

    def rel_path(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.base_dir))
        except ValueError:
            return str(path)
