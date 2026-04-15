"""
recipes/claw.py - Recipe for claw (init system for BlueyOS).

claw uses autotools (./autogen.sh + ./configure + make).  It links
statically against musl-blueyos and produces a single ``claw`` binary
installed to ``/sbin/init`` (with a symlink from ``/bin/init``).
"""

from __future__ import annotations

import os
import shutil

from recipes.base import RecipeError
from recipes._musl_package import MuslPackageRecipe


class ClawRecipe(MuslPackageRecipe):
    """claw — init / service manager for BlueyOS."""

    name = "claw"
    version = "1.0.0"
    dependencies = ["musl-blueyos"]
    binary_name = "claw"
    binary_dest = "sbin/init"
    install_paths = ["sbin/init", "bin/init"]

    def configure(self) -> None:
        src = self._source_dir
        if not os.path.isdir(src):
            raise RecipeError(f"claw source not found at {src}")

        musl_prefix = self.config.abs_musl_prefix

        # Run autogen.sh if configure script doesn't exist yet
        configure_script = os.path.join(src, "configure")
        if not os.path.isfile(configure_script):
            autogen = os.path.join(src, "autogen.sh")
            if os.path.isfile(autogen):
                self.log.info("Running autogen.sh for claw")
                self.run(["bash", "autogen.sh"], cwd=src)
            else:
                self.log.warning("No autogen.sh found; assuming configure is present")

        if not os.path.isfile(configure_script):
            raise RecipeError(f"configure script not found in {src}")

        self.log.info("Configuring claw with musl prefix %s", musl_prefix)
        self.run(
            [
                "./configure",
                f"--prefix=/usr",
                f"CC=gcc -m32 -isystem {musl_prefix}/include",
                f"LDFLAGS=-L{musl_prefix}/lib -static",
                "--host=i686-linux-gnu",
            ],
            cwd=src,
        )

    def install(self) -> None:
        src = self._source_dir
        # Look for claw binary in common locations
        for candidate in ("build/claw", "claw", "src/claw"):
            path = os.path.join(src, candidate)
            if os.path.isfile(path):
                self.sysroot.ensure_dir("sbin")
                self.sysroot.install_binary(path, "sbin/init")
                # Also create /bin/init symlink pointing to /sbin/init
                self.sysroot.ensure_dir("bin")
                self.sysroot.symlink("/sbin/init", "bin/init")
                self.log.info("Installed claw → sysroot/sbin/init")
                return
        self.log.warning("claw binary not found after build; skipping install.")
