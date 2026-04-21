"""
recipes/musl.py - musl libc recipe for Baker.

Builds and installs the musl C library (https://musl.libc.org/) into the
sysroot.  musl is used as the system C library for ClawOS.
"""

from __future__ import annotations

import os
import shutil

from config import Config
from recipes.base import BaseRecipe, safe_extract


class MuslRecipe(BaseRecipe):
    name = "musl"
    version = "1.2.5"
    dependencies: list = []
    install_paths = [
        "usr/lib/libc.so",
        "usr/lib/libc.a",
        "usr/include",
        "lib/ld-musl-i386.so.1",
    ]

    # Source URL (tarball fetched during prepare)
    _tarball_url = f"https://musl.libc.org/releases/musl-1.2.5.tar.gz"

    def fetch(self) -> None:
        self.log.info("Fetching musl %s sources", self.version)
        src = self.ensure_source_dir()
        tarball = os.path.join(src, f"musl-{self.version}.tar.gz")

        if not os.path.exists(tarball):
            self.log.info("Downloading %s", self._tarball_url)
            import urllib.request
            try:
                urllib.request.urlretrieve(self._tarball_url, tarball)
            except Exception as exc:
                self.log.warning("Download failed (%s); skipping.", exc)
                return

        # Extract if not already done
        extracted = os.path.join(src, f"musl-{self.version}")
        if not os.path.exists(extracted):
            self.log.info("Extracting %s", tarball)
            safe_extract(tarball, src)

    def configure(self) -> None:
        self.log.info("Configuring musl")
        bdir = self.ensure_build_dir()
        src_inner = os.path.join(self._source_dir, f"musl-{self.version}")
        if not os.path.exists(src_inner):
            self.log.warning("musl source not found at %s; skipping configure.", src_inner)
            return

        self.run(
            [
                os.path.join(src_inner, "configure"),
                "--prefix=/usr",
                "--syslibdir=/lib",
                "--disable-static",
            ],
            cwd=bdir,
            env={"ARCH": self.config.arch},
        )

    def build(self) -> None:
        self.log.info("Building musl %s", self.version)
        bdir = self._build_dir
        if not os.path.exists(bdir):
            self.log.warning("musl build dir not found; skipping build.")
            return
        make_flags = self.config.kernel.make_flags.split()
        self.run(["make"] + make_flags, cwd=bdir)

    def install(self) -> None:
        self.log.info("Installing musl into sysroot")
        bdir = self._build_dir
        if not os.path.exists(bdir):
            self.log.warning("musl build dir not found; skipping install.")
            return
        self.run(
            ["make", f"DESTDIR={self.config.abs_sysroot}", "install"],
            cwd=bdir,
        )
        self.log.info("musl installed.")
