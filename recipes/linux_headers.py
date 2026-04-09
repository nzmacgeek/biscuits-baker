"""
recipes/linux_headers.py - Linux kernel headers recipe for Baker.

Installs the Linux UAPI headers into the sysroot so that userspace
programs can include <linux/…> headers during compilation.
"""

from __future__ import annotations

import os

from config import Config
from recipes.base import BaseRecipe


class LinuxHeadersRecipe(BaseRecipe):
    name = "linux-headers"
    version = "6.6"
    dependencies: list = []
    install_paths = ["usr/include/linux", "usr/include/asm", "usr/include/asm-generic"]

    def fetch(self) -> None:
        self.log.info("Fetching Linux %s headers", self.version)
        src = self.ensure_source_dir()
        tarball = os.path.join(src, f"linux-{self.version}.tar.xz")
        url = f"https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-{self.version}.tar.xz"

        if not os.path.exists(tarball):
            self.log.info("Downloading %s", url)
            import urllib.request
            try:
                urllib.request.urlretrieve(url, tarball)
            except Exception as exc:
                self.log.warning("Download failed (%s); skipping.", exc)
                return

        extracted = os.path.join(src, f"linux-{self.version}")
        if not os.path.exists(extracted):
            import tarfile
            self.log.info("Extracting %s", tarball)
            with tarfile.open(tarball) as tf:
                tf.extractall(src)

    def build(self) -> None:
        """Headers don't require a compilation step."""
        self.log.info("linux-headers: nothing to build")

    def install(self) -> None:
        self.log.info("Installing Linux headers into sysroot")
        src_inner = os.path.join(self._source_dir, f"linux-{self.version}")
        if not os.path.exists(src_inner):
            self.log.warning("Linux source not found at %s; skipping.", src_inner)
            return

        self.run(
            [
                "make",
                "headers_install",
                f"ARCH={self.config.arch}",
                f"INSTALL_HDR_PATH={self.config.abs_sysroot}/usr",
            ],
            cwd=src_inner,
        )
        self.log.info("Linux headers installed.")
