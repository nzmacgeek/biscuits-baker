"""
recipes/nano.py - GNU nano text editor for BlueyOS (i386, static musl).

Builds nano against the ncurses library already in the sysroot.
Produces a single statically-linked i386 binary.
"""

from __future__ import annotations

import os
import shutil

from recipes._port_recipe import PortRecipe
from recipes.base import RecipeError

_VERSION = "8.3"


class NanoRecipe(PortRecipe):
    name = "nano"
    version = _VERSION
    description = "GNU nano text editor (static, i386)"
    dependencies = ["musl-blueyos", "ncurses"]
    install_paths = ["usr/bin/nano", "usr/share/nano"]
    pkg_depends = []

    tarball_url = f"https://www.nano-editor.org/dist/v8/nano-{_VERSION}.tar.xz"
    tarball_name = f"nano-{_VERSION}.tar.xz"
    src_subdir = f"nano-{_VERSION}"

    def build(self) -> None:
        src = self._source_dir
        if not os.path.isdir(src):
            raise RecipeError(
                f"nano source not found at {src}. Run 'baker prepare' first."
            )

        musl_gcc = self._musl_gcc()
        sysroot = self.config.abs_sysroot
        env = {
            "CC": musl_gcc,
            # term.h and other curses headers land in ncursesw/ when built with
            # wide-character support (the blueyos-bash ncurses build uses --enable-widec)
            "CFLAGS": (
                f"-O2 -I{sysroot}/usr/include -I{sysroot}/usr/include/ncursesw"
            ),
            "LDFLAGS": f"-L{sysroot}/usr/lib -static",
        }

        self.log.info("Configuring nano %s for i386 static musl", self.version)
        self.run(
            [
                "./configure",
                *self._autoconf_host_flags,
                "--prefix=/usr",
                "--sysconfdir=/etc",
                "--disable-nls",
                "--disable-mouse",
                "--without-libmagic",
                "--enable-utf8",
                "--with-wordbounds",
            ],
            cwd=src,
            env=env,
        )

        self.log.info("Building nano %s", self.version)
        make_flags = self.config.kernel.make_flags.split()
        self.run(["make"] + make_flags, cwd=src, env=env)

    def install(self) -> None:
        src = self._source_dir
        staging = self._staging_dir
        os.makedirs(staging, exist_ok=True)

        self.log.info("Installing nano into staging at %s", staging)
        self.run(
            ["make", f"DESTDIR={staging}", "install"],
            cwd=src,
        )
