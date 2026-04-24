"""
recipes/openssl.py - OpenSSL 3.x port for BlueyOS (i386, static musl).

Builds the static libraries (libssl.a, libcrypto.a) and installs headers
into the sysroot so other ports (dropbear, w3m) can link against them.
The openssl CLI tool is also included.
"""

from __future__ import annotations

import os
import shutil

from recipes._port_recipe import PortRecipe
from recipes.base import RecipeError

_VERSION = "3.4.1"


class OpenSSLRecipe(PortRecipe):
    name = "openssl"
    version = _VERSION
    description = "OpenSSL cryptography library and TLS toolkit (static, i386)"
    dependencies = ["musl-blueyos"]
    install_paths = [
        "usr/lib/libssl.a",
        "usr/lib/libcrypto.a",
        "usr/include/openssl",
        "usr/bin/openssl",
    ]
    pkg_depends = []

    tarball_url = (
        f"https://github.com/openssl/openssl/releases/download/"
        f"openssl-{_VERSION}/openssl-{_VERSION}.tar.gz"
    )
    tarball_name = f"openssl-{_VERSION}.tar.gz"
    src_subdir = f"openssl-{_VERSION}"

    def build(self) -> None:
        src = self._source_dir
        if not os.path.isdir(src):
            raise RecipeError(
                f"openssl source not found at {src}. Run 'baker prepare' first."
            )

        musl_gcc = self._musl_gcc()
        sysroot = self.config.abs_sysroot

        self.log.info("Configuring OpenSSL %s for i386 static musl", self.version)
        self.run(
            [
                "./Configure",
                "linux-x86",
                "no-shared",
                "no-dso",
                "no-tests",
                "no-asm",       # avoid NASM dependency; pure-C fallback
                "no-engine",
                "no-threads",   # musl-gcc uses -nostdinc which hides stdatomic.h;
                                # no-threads avoids the C11 atomic header requirement
                "--prefix=/usr",
                "--openssldir=/etc/ssl",
                f"CC={musl_gcc}",
                "AR=ar",
                "RANLIB=ranlib",
                f"CFLAGS=-O2 -I{sysroot}/usr/include",
            ],
            cwd=src,
        )

        self.log.info("Building OpenSSL %s", self.version)
        make_flags = self.config.kernel.make_flags.split()
        self.run(["make"] + make_flags + ["build_libs"], cwd=src)
        # Also build the openssl CLI
        self.run(["make"] + make_flags + ["openssl"], cwd=src)

    def install(self) -> None:
        src = self._source_dir
        staging = self._staging_dir
        os.makedirs(staging, exist_ok=True)

        self.log.info("Installing OpenSSL into staging at %s", staging)
        self.run(
            ["make", f"DESTDIR={staging}", "install_dev", "install_sw"],
            cwd=src,
        )

        # Also copy into the sysroot so other ports can find headers/libs.
        self.log.info("Merging OpenSSL into sysroot %s", self.config.abs_sysroot)
        for subdir in ("usr/include/openssl", "usr/lib"):
            src_dir = os.path.join(staging, subdir)
            dst_dir = os.path.join(self.config.abs_sysroot, subdir)
            if os.path.isdir(src_dir):
                shutil.copytree(src_dir, dst_dir, dirs_exist_ok=True)

        # Copy openssl binary into sysroot
        openssl_bin = os.path.join(staging, "usr", "bin", "openssl")
        if os.path.isfile(openssl_bin):
            dst = os.path.join(self.config.abs_sysroot, "usr", "bin", "openssl")
            shutil.copy2(openssl_bin, dst)
            os.chmod(dst, 0o755)
