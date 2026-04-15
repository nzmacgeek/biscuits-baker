"""
stages/image.py - Image build stage for Baker.

Assembles a bootable filesystem image from the populated sysroot.
"""

from __future__ import annotations

from stage_runner import Stage
from helpers.image import ImageBuilder


class ImageStage(Stage):
    """Assemble a bootable image from the sysroot."""

    name = "image"

    def run(self) -> None:
        cfg = self.config

        if not cfg.image.enabled:
            self.log.info("Image generation is disabled in configuration.")
            return

        self.log.info(
            "Building %s image (%d MB) → %s",
            cfg.image.format,
            cfg.image.size_mb,
            cfg.image.output,
        )

        builder = ImageBuilder(
            image_cfg=cfg.image,
            sysroot=cfg.abs_sysroot,
            output_dir=cfg.abs_output_dir,
        )

        image_path = builder.build()
        self.log.info("Image stage complete: %s", image_path)
