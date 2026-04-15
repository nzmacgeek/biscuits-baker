"""
recipes/blueyos_tzinfo.py - Recipe for blueyos-tzinfo.

blueyos-tzinfo is a pre-packaged timezone database for BlueyOS.  The
repository already contains the dpk ``meta/`` and ``payload/`` layout;
running ``make`` downloads the IANA tzdata archive, compiles it with
``zic``, and calls ``dpkbuild build .`` to produce the final ``.dpk``.
"""

from __future__ import annotations

import glob
import os
import shutil

from recipes.base import BaseRecipe, RecipeError


class BlueyosTzinfoRecipe(BaseRecipe):
    """IANA timezone database package for BlueyOS."""

    name = "blueyos-tzinfo"
    version = "2025.1.0"
    dependencies: list = []

    def __init__(self, config):
        super().__init__(config)
        self._source_dir = os.path.join(config.abs_sources_dir, "blueyos-tzinfo")

    def build(self) -> None:
        src = self._source_dir
        if not os.path.isdir(src):
            raise RecipeError(
                f"blueyos-tzinfo source not found at {src}.  Run 'baker prepare' first."
            )

        if shutil.which("zic") is None:
            self.log.warning(
                "zic not found; timezone data will not be compiled.  "
                "Install 'tzdata' or 'zic' on the host."
            )
            # Continue anyway — dpkbuild may succeed if payload is pre-built
            return

        self.log.info("Building blueyos-tzinfo (downloading IANA tzdata + zic compile)")
        self.run(["make", "build"], cwd=src)

    def install(self) -> None:
        src = self._source_dir
        payload = os.path.join(src, "payload")
        if os.path.isdir(payload):
            # Merge each top-level entry from the payload into the sysroot root
            # rather than targeting '.' directly (which could wipe the sysroot).
            self.sysroot.install_tree(payload, ".")
            self.log.info("Installed blueyos-tzinfo payload to sysroot")
        else:
            self.log.warning("No payload/ directory found; skipping tzinfo install.")

    def package(self) -> str | None:
        src = self._source_dir
        dpkbuild_in_src = os.path.join(
            self.config.abs_sources_dir, "dimsim", "bin", "dpkbuild"
        )
        dpkbuild = (
            shutil.which("dpkbuild")
            or (dpkbuild_in_src if os.path.isfile(dpkbuild_in_src) else None)
        )

        if dpkbuild and os.path.isdir(src):
            env = {
                "PATH": os.path.dirname(dpkbuild) + ":" + os.environ.get("PATH", ""),
            }
            try:
                self.run(["make", "dpk"], cwd=src, env=env)
                dpk_files = glob.glob(os.path.join(src, "*.dpk"))
                if dpk_files:
                    dest = os.path.join(
                        self.config.abs_output_dir, os.path.basename(dpk_files[0])
                    )
                    shutil.copy2(dpk_files[0], dest)
                    self.log.info("Package: %s", dest)
                    return dest
            except RecipeError as exc:
                self.log.warning("make dpk failed: %s; falling back to tar.gz", exc)

        # Fallback: tar.gz of the payload
        from helpers.packaging import PackageBuilder

        builder = PackageBuilder(self.config.abs_output_dir)
        return builder.build_package(
            name=self.name,
            version=self.version,
            sysroot=self.config.abs_sysroot,
            include_paths=["usr/share/zoneinfo"],
            metadata={"arch": "noarch"},
        )
