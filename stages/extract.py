"""
stages/extract.py - Diagnostic file extraction stage for Baker.

Reads the BlueyOS disk image directly using the BlueyFS reader and extracts
requested paths (default: /var/log and /etc) to a timestamped output directory.

Note: /proc and /sys are virtual filesystems — they are not present in the disk
image and cannot be extracted this way.  They are only available from a live
running system via the QEMU serial console.

Usage:
    baker extract                          # extract /var/log, /etc and /root
    baker extract --paths /var/log        # extract only /var/log
    baker extract --output debug/run-42   # custom output directory
    baker extract --image path/to/img     # use a specific disk image
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

from stage_runner import Stage
from helpers.blueyfs import BlueyFSImage, extract_inode, safe_child_path, IFMT, IFDIR

logger = logging.getLogger(__name__)

DEFAULT_PATHS = ["/var/log", "/etc", "/root"]


def _resolve_image_path(cfg, image_override: str | None) -> str:
    if image_override:
        return image_override if os.path.isabs(image_override) else os.path.join(os.getcwd(), image_override)
    p = cfg.image.output
    return p if os.path.isabs(p) else os.path.join(os.getcwd(), p)


class ExtractStage(Stage):
    """Extract diagnostic files from the BlueyOS disk image."""

    name = "extract"

    # Set by baker.py before run() is called
    paths: list[str] = DEFAULT_PATHS
    output_dir: str | None = None
    image_override: str | None = None

    def run(self) -> None:
        cfg = self.config
        image_path = _resolve_image_path(cfg, self.image_override)

        if not os.path.isfile(image_path):
            raise RuntimeError(
                f"Disk image not found: {image_path}\n"
                "Run 'baker image' to create it first, or pass --image to specify a different path."
            )

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_base = Path(
            self.output_dir if self.output_dir else
            os.path.join(cfg.abs_output_dir, f"extract-{timestamp}")
        )
        out_base.mkdir(parents=True, exist_ok=True)

        self.log.info("Extracting from %s", image_path)
        self.log.info("Output directory: %s", out_base)

        image = BlueyFSImage(Path(image_path))
        try:
            for src_path in self.paths:
                dest = out_base / src_path.lstrip("/")
                self._extract_path(image, src_path, dest)
        finally:
            image.close()

        self.log.info("Extraction complete: %s", out_base)

    def _extract_path(self, image: BlueyFSImage, src_path: str, dest: Path) -> None:
        try:
            inode_no, inode = image.lookup_path(src_path)
        except FileNotFoundError:
            self.log.warning("Path not found in image: %s (skipping)", src_path)
            return
        except (ValueError, NotADirectoryError) as exc:
            self.log.warning("Cannot read %s: %s (skipping)", src_path, exc)
            return

        if (inode.mode & IFMT) == IFDIR:
            # Extract each child rather than the directory node itself so we
            # preserve the expected dest/<name> layout.
            dest.mkdir(parents=True, exist_ok=True)
            for name, child_ino in image.iter_dir(inode):
                extract_inode(image, child_ino, safe_child_path(dest, name))
        else:
            extract_inode(image, inode_no, dest)

        self.log.info("  Extracted %s → %s", src_path, dest)
