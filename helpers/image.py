"""
helpers/image.py - Image builder for Baker.

Assembles a bootable filesystem image from the populated sysroot.
Supports ext2/ext4 (via genext2fs or mke2fs) and a raw tarball fallback.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tarfile
from typing import Optional

from config import ImageConfig

logger = logging.getLogger(__name__)


class ImageBuilder:
    """Builds a bootable disk image from the sysroot."""

    def __init__(self, image_cfg: ImageConfig, sysroot: str, output_dir: str) -> None:
        self.cfg = image_cfg
        self.sysroot = os.path.abspath(sysroot)
        self.output_dir = os.path.abspath(output_dir)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self) -> str:
        """Build the image according to configuration.

        Returns:
            Absolute path to the produced image file.

        Raises:
            RuntimeError: if the requested format is unsupported or required
                          tools are unavailable.
        """
        os.makedirs(self.output_dir, exist_ok=True)
        fmt = self.cfg.format.lower()

        if fmt in ("ext2", "ext4"):
            return self._build_ext_image(fmt)
        elif fmt == "iso9660":
            return self._build_iso_image()
        elif fmt == "tar":
            return self._build_tar_image()
        else:
            raise RuntimeError(f"Unsupported image format: {fmt!r}")

    # ------------------------------------------------------------------
    # Format implementations
    # ------------------------------------------------------------------

    def _build_ext_image(self, fmt: str) -> str:
        """Build an ext2/ext4 image using genext2fs or mke2fs."""
        output = os.path.abspath(self.cfg.output)
        os.makedirs(os.path.dirname(output), exist_ok=True)
        size_mb = self.cfg.size_mb

        logger.info("Building %s image (%d MB) → %s", fmt, size_mb, output)

        # Prefer genext2fs (no root needed); fall back to mke2fs (requires loop mount)
        if shutil.which("genext2fs"):
            self._run(
                ["genext2fs", "-b", str(size_mb * 1024), "-d", self.sysroot, output],
                f"genext2fs failed for {output}",
            )
        elif shutil.which("mke2fs"):
            # Create empty image, format, then copy files
            self._run(
                ["dd", "if=/dev/zero", f"of={output}", "bs=1M", f"count={size_mb}"],
                "dd failed",
            )
            self._run(
                ["mke2fs", "-t", fmt, "-F", output],
                "mke2fs failed",
            )
            logger.warning(
                "mke2fs created an empty image.  "
                "Populate it manually with a loop mount or use genext2fs."
            )
        else:
            # Fallback: produce a tar.gz so the build doesn't fail completely
            logger.warning(
                "Neither genext2fs nor mke2fs found.  "
                "Falling back to tar archive: %s.tar.gz",
                output,
            )
            return self._build_tar_image()

        logger.info("Image created: %s", output)
        return output

    def _build_iso_image(self) -> str:
        """Build an ISO 9660 image using genisoimage or mkisofs."""
        output = os.path.abspath(self.cfg.output)
        os.makedirs(os.path.dirname(output), exist_ok=True)

        logger.info("Building ISO image → %s", output)

        tool = shutil.which("genisoimage") or shutil.which("mkisofs")
        if not tool:
            logger.warning("genisoimage/mkisofs not found; falling back to tar.")
            return self._build_tar_image()

        self._run(
            [
                tool,
                "-o", output,
                "-R",   # Rock Ridge
                "-J",   # Joliet
                "-l",   # allow long filenames
                self.sysroot,
            ],
            "ISO creation failed",
        )
        logger.info("ISO image created: %s", output)
        return output

    def _build_tar_image(self) -> str:
        """Fallback: produce a gzip-compressed tar of the sysroot."""
        base = os.path.splitext(self.cfg.output)[0]
        output = os.path.abspath(base + ".tar.gz")
        os.makedirs(os.path.dirname(output), exist_ok=True)

        logger.info("Building tar image → %s", output)
        with tarfile.open(output, "w:gz") as tar:
            tar.add(self.sysroot, arcname=".")
        logger.info("Tar image created: %s (%.1f MB)", output, os.path.getsize(output) / 1024 / 1024)
        return output

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _run(cmd: list, error_msg: str) -> None:
        logger.debug("Running: %s", " ".join(str(c) for c in cmd))
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"{error_msg}\n{result.stderr}")
