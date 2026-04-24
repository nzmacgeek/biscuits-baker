"""
recipes/w3m.py - w3m text-mode web browser for BlueyOS (i386, static musl).

w3m requires:
  - OpenSSL (for HTTPS) — must be built and merged into the sysroot first
  - Boehm-Demers-Weiser GC (libgc) — bundled build or sysroot-installed
  - ncurses — already in the sysroot

Image display (--disable-image) and mouse support (--disable-mouse) are
disabled; only text-mode browsing is built.

NOTE: w3m depends on the openssl recipe having run install() first so that
libssl.a/libcrypto.a and the OpenSSL headers are present in the sysroot.
"""

from __future__ import annotations

import os

from recipes._port_recipe import PortRecipe
from recipes.base import RecipeError

_VERSION = "0.5.3+git20230121"
_TARBALL_VERSION = "0.5.3+git20230121"


class W3mRecipe(PortRecipe):
    name = "w3m"
    version = "0.5.3"
    description = "w3m text-mode web browser with SSL support (static, i386)"
    dependencies = ["musl-blueyos", "ncurses", "openssl"]
    install_paths = ["usr/bin/w3m", "usr/share/w3m", "usr/lib/w3m"]
    pkg_depends = []

    tarball_url = (
        "https://github.com/tats/w3m/archive/refs/tags/v0.5.3+git20230121.tar.gz"
    )
    tarball_name = "w3m-0.5.3+git20230121.tar.gz"
    # GitHub replaces '+' with '-' in the extracted directory name
    src_subdir = "w3m-0.5.3-git20230121"

    def build(self) -> None:
        src = self._source_dir
        if not os.path.isdir(src):
            raise RecipeError(
                f"w3m source not found at {src}. Run 'baker prepare' first."
            )

        sysroot = self.config.abs_sysroot
        ssl_lib = os.path.join(sysroot, "usr", "lib", "libssl.a")
        if not os.path.isfile(ssl_lib):
            raise RecipeError(
                "OpenSSL static library not found in sysroot. "
                "Build the 'openssl' recipe first."
            )

        musl_gcc = self._musl_gcc()
        env = {
            "CC": musl_gcc,
            "CFLAGS": f"-O2 -I{sysroot}/usr/include",
            "LDFLAGS": f"-L{sysroot}/usr/lib -static",
            "LIBS": "-lssl -lcrypto -lncurses",
        }

        self.log.info("Configuring w3m %s for i386 static musl", self.version)
        # Run autoreconf if configure doesn't exist
        if not os.path.isfile(os.path.join(src, "configure")):
            self.run(["autoreconf", "-fiv"], cwd=src)

        self.run(
            [
                "./configure",
                *self._autoconf_host_flags,
                "--prefix=/usr",
                "--sysconfdir=/etc",
                "--disable-image",
                "--disable-mouse",
                "--disable-nls",
                "--with-ssl",
                f"--with-ssl-prefix={sysroot}/usr",
                "--with-ncurses",
                "--without-gc",   # skip Boehm GC; w3m has a fallback allocator
                "--without-migemo",
            ],
            cwd=src,
            env=env,
        )

        self.log.info("Building w3m %s", self.version)
        make_flags = self.config.kernel.make_flags.split()
        self.run(["make"] + make_flags, cwd=src, env=env)

    def install(self) -> None:
        src = self._source_dir
        staging = self._staging_dir
        os.makedirs(staging, exist_ok=True)

        self.log.info("Installing w3m into staging at %s", staging)
        self.run(
            ["make", f"DESTDIR={staging}", "install"],
            cwd=src,
        )
