"""
recipes/claw.py - Recipe for claw (init system for BlueyOS).

claw uses autotools (./autogen.sh + ./configure + make).  It links
statically against musl-blueyos and produces a single ``claw`` binary
    installed to ``/sbin/claw`` (with compatibility symlinks for init paths).
"""

from __future__ import annotations

import glob
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
    binary_dest = "sbin/claw"
    install_paths = ["sbin/claw", "sbin/init", "bin/init"]

    def configure(self) -> None:
        src = self._source_dir
        if not os.path.isdir(src):
            raise RecipeError(f"claw source not found at {src}")

        musl_prefix = self.config.abs_musl_prefix
        toolchain_prefix = self.config.abs_toolchain_prefix

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
        env = {
            "BLUEYOS_CROSS": toolchain_prefix,
            "BLUEYOS_SYSROOT": musl_prefix,
        }

        configure_wrapper = os.path.join(src, "configure-blueyos")
        if os.path.isfile(configure_wrapper):
            self.run(
                [
                    "./configure-blueyos",
                    "--prefix=/",
                    "--sbindir=/sbin",
                    "--bindir=/bin",
                    "--sysconfdir=/etc",
                    "--localstatedir=/var",
                ],
                cwd=src,
                env=env,
            )
            return

        self.run(
            [
                "./configure",
                "--enable-static-binary",
                "--prefix=/",
                "--sbindir=/sbin",
                "--bindir=/bin",
                "--sysconfdir=/etc",
                "--localstatedir=/var",
            ],
            cwd=src,
            env=env,
        )

    def build(self) -> None:
        src = self._source_dir
        if not os.path.isdir(src):
            raise RecipeError(
                f"{self.name} source not found at {src}.  Run 'baker prepare' first."
            )

        make_flags = self.config.kernel.make_flags.split()
        musl_prefix = self.config.abs_musl_prefix
        toolchain_prefix = self.config.abs_toolchain_prefix

        env = {
            "MUSL_PREFIX": musl_prefix,
            "BLUEYOS_CROSS": toolchain_prefix,
            "BLUEYOS_SYSROOT": musl_prefix,
        }

        self.log.info("Building %s against musl sysroot at %s", self.name, musl_prefix)
        self.run(["make"] + make_flags, cwd=src, env=env)

    def install(self) -> None:
        src = self._source_dir
        staging_dir = os.path.join(self._build_dir, "sysroot-staging")
        if os.path.isdir(staging_dir):
            shutil.rmtree(staging_dir)
        os.makedirs(staging_dir, exist_ok=True)

        self.run(["make", "install", f"DESTDIR={staging_dir}"], cwd=src)
        self.sysroot.install_tree(staging_dir, ".")
        self.sysroot.symlink("/sbin/claw", "sbin/init")
        self.sysroot.symlink("/sbin/claw", "bin/init")
        self.log.info("Installed claw payload into %s", self.config.abs_sysroot)

    def package(self) -> str | None:
        src = self._source_dir
        dist_dir = os.path.join(src, "dist")
        os.makedirs(dist_dir, exist_ok=True)
        for existing in glob.glob(os.path.join(dist_dir, "*.dpk")):
            os.remove(existing)

        self.run(["make", "package"], cwd=src)

        dpk_files = sorted(glob.glob(os.path.join(dist_dir, "*.dpk")))
        if not dpk_files:
            raise RecipeError(f"make package completed for {self.name}, but no .dpk was produced in {dist_dir}")

        dest = os.path.join(self.config.abs_output_dir, os.path.basename(dpk_files[0]))
        shutil.copy2(dpk_files[0], dest)
        self.log.info("Package: %s", dest)
        return dest
