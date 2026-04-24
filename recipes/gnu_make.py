"""
recipes/gnu_make.py - GNU make for BlueyOS (i386, static musl).

Produces a statically-linked i386 /usr/bin/make that can run build systems
inside BlueyOS.  Required for any autoconf/automake-based self-hosted build.
"""

from __future__ import annotations

import os

from recipes._port_recipe import PortRecipe
from recipes.base import RecipeError

_VERSION = "4.4.1"


class GnuMakeRecipe(PortRecipe):
    name = "gnu-make"
    version = _VERSION
    description = "GNU make build tool (static, i386)"
    dependencies = ["musl-blueyos"]
    install_paths = ["usr/bin/make"]
    pkg_depends = []

    tarball_url = f"https://ftp.gnu.org/gnu/make/make-{_VERSION}.tar.gz"
    tarball_name = f"make-{_VERSION}.tar.gz"
    src_subdir = f"make-{_VERSION}"

    def build(self) -> None:
        src = self._source_dir
        if not os.path.isdir(src):
            raise RecipeError(
                f"make source not found at {src}. Run 'baker prepare' first."
            )

        env = self._cross_env(static=True)
        # Disable features that complicate static linking.
        env["LDFLAGS"] += " -Wl,--as-needed"

        self.log.info("Configuring GNU make %s for i386 static musl", self.version)
        self.run(
            [
                "./configure",
                *self._autoconf_host_flags,
                "--prefix=/usr",
                "--without-guile",
                "--disable-nls",
                "--disable-rpath",
            ],
            cwd=src,
            env=env,
        )

        self.log.info("Building GNU make %s", self.version)
        make_flags = self.config.kernel.make_flags.split()
        self.run(["make"] + make_flags, cwd=src, env=env)

    def install(self) -> None:
        src = self._source_dir
        staging = self._staging_dir
        os.makedirs(staging, exist_ok=True)

        self.log.info("Installing GNU make into staging at %s", staging)
        self.run(["make", f"DESTDIR={staging}", "install"], cwd=src)
