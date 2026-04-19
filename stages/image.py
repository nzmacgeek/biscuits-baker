"""
stages/image.py - Image build stage for Baker.

Assembles a bootable filesystem image from the populated sysroot.
"""

from __future__ import annotations

import os
import shutil
import subprocess

from helpers.host_tools import build_host_env
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

        native_fmt = cfg.image.format.lower()
        if native_fmt in {"disk", "iso", "iso9660"}:
            image_path = self._build_native_image(native_fmt)
            self.log.info("Image stage complete: %s", image_path)
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

    def _build_native_image(self, fmt: str) -> str:
        cfg = self.config
        src = cfg.abs_kernel_source
        if not os.path.isdir(src):
            raise RuntimeError(f"Kernel source not found at {src}. Run 'baker prepare' first.")

        os.makedirs(cfg.abs_output_dir, exist_ok=True)
        build_dir = os.path.join(src, "build")
        image_target = "disk" if fmt == "disk" else "iso"
        self.log.info("Delegating %s image build to biscuits", image_target)
        self._run(
            [
                "make",
                f"BUILD_DIR={build_dir}",
                f"BLUEYOS_SYSROOT={cfg.abs_sysroot}",
                image_target,
            ],
            cwd=src,
        )

        if image_target == "disk":
            if shutil.which("mkfs.fat"):
                self._run(
                    ["bash", "tools/mkfat_logs_disk.sh", os.path.join(build_dir, "blueyos-log-fat.img")],
                    cwd=src,
                )
            else:
                self.log.info("mkfs.fat not found; skipping optional FAT log disk image.")
            produced = os.path.join(build_dir, "blueyos-disk.img")
        else:
            produced = os.path.join(build_dir, "blueyos.iso")

        requested = cfg.image.output
        output = requested if os.path.isabs(requested) else os.path.join(os.getcwd(), requested)
        os.makedirs(os.path.dirname(output), exist_ok=True)
        if os.path.abspath(produced) != os.path.abspath(output):
            shutil.copy2(produced, output)
            return output
        return produced

    def _run(self, cmd: list[str], cwd: str) -> None:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            env=build_host_env(),
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr or result.stdout or f"Command failed: {' '.join(cmd)}")
