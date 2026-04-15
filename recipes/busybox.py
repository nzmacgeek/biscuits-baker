"""
recipes/busybox.py - BusyBox recipe for Baker.

Builds BusyBox as a statically-linked or dynamically-linked multi-call
binary and installs it into the sysroot.
"""

from __future__ import annotations

import os
import shutil

from config import Config
from recipes.base import BaseRecipe, safe_extract


class BusyBoxRecipe(BaseRecipe):
    name = "busybox"
    version = "1.36.1"
    dependencies = ["musl", "linux-headers"]
    install_paths = [
        "usr/bin/busybox",
        "bin",
        "sbin",
        "usr/sbin",
    ]

    _tarball_url = f"https://busybox.net/downloads/busybox-1.36.1.tar.bz2"

    def fetch(self) -> None:
        self.log.info("Fetching BusyBox %s sources", self.version)
        src = self.ensure_source_dir()
        tarball = os.path.join(src, f"busybox-{self.version}.tar.bz2")

        if not os.path.exists(tarball):
            self.log.info("Downloading %s", self._tarball_url)
            import urllib.request
            try:
                urllib.request.urlretrieve(self._tarball_url, tarball)
            except Exception as exc:
                self.log.warning("Download failed (%s); skipping.", exc)
                return

        extracted = os.path.join(src, f"busybox-{self.version}")
        if not os.path.exists(extracted):
            self.log.info("Extracting %s", tarball)
            safe_extract(tarball, src)

    def configure(self) -> None:
        self.log.info("Configuring BusyBox (defconfig)")
        src_inner = os.path.join(self._source_dir, f"busybox-{self.version}")
        if not os.path.exists(src_inner):
            self.log.warning("BusyBox source not found; skipping configure.")
            return
        # Copy source to build dir for an out-of-tree build
        bdir = self.ensure_build_dir()
        if not os.path.exists(os.path.join(bdir, "Makefile")):
            shutil.copytree(src_inner, bdir, dirs_exist_ok=True)
        self.run(["make", "defconfig"], cwd=bdir)

    def build(self) -> None:
        self.log.info("Building BusyBox %s", self.version)
        bdir = self._build_dir
        if not os.path.exists(bdir):
            self.log.warning("BusyBox build dir not found; skipping.")
            return
        make_flags = self.config.kernel.make_flags.split()
        self.run(
            ["make"] + make_flags + [f"ARCH={self.config.arch}"],
            cwd=bdir,
        )

    def install(self) -> None:
        self.log.info("Installing BusyBox into sysroot")
        bdir = self._build_dir
        if not os.path.exists(bdir):
            self.log.warning("BusyBox build dir not found; skipping install.")
            return
        self.run(
            ["make", f"CONFIG_PREFIX={self.config.abs_sysroot}", "install"],
            cwd=bdir,
        )
        self.log.info("BusyBox installed.")
