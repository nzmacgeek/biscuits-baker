"""
recipes/scout.py - Recipe for scout (DHCP/DNS daemon for BlueyOS).

scout uses autotools (autogen.sh → configure → make) and links against
musl-blueyos.  Baker runs configure out-of-tree inside the component
build directory, mirroring what tools/configure-blueyos.sh does.

Installed paths:
    /sbin/scoutd
    /usr/bin/nslookup
    /usr/bin/ping
    /usr/bin/tracert
    /etc/scout/scout.conf
    /etc/claw/services.d/scout.service.yml
"""

from __future__ import annotations

import glob
import os
import shutil

from recipes._musl_package import MuslPackageRecipe
from recipes.base import RecipeError


class ScoutRecipe(MuslPackageRecipe):
    """scout — DHCP client and DNS resolver daemon for BlueyOS."""

    name = "scout"
    version = "0.1.0"
    dependencies = ["musl-blueyos", "claw"]
    install_paths = [
        "sbin/scoutd",
        "usr/bin/nslookup",
        "usr/bin/ping",
        "usr/bin/tracert",
        "etc/scout/scout.conf",
        "etc/claw/services.d/scout.service.yml",
    ]

    def configure(self) -> None:
        src = self._source_dir
        if not os.path.isdir(src):
            raise RecipeError(f"scout source not found at {src}")

        configure_script = os.path.join(src, "configure")
        if not os.path.isfile(configure_script):
            autogen = os.path.join(src, "autogen.sh")
            if os.path.isfile(autogen):
                self.log.info("Running autogen.sh for scout")
                self.run(["bash", "autogen.sh"], cwd=src)
            else:
                self.log.warning("No autogen.sh found; assuming configure is present")

        if not os.path.isfile(configure_script):
            raise RecipeError(f"configure script not found in {src}")

        build_dir = self.ensure_build_dir()
        musl_sysroot = self._resolve_musl_sysroot()

        self._ensure_musl_specs()
        self.log.info("Configuring scout with musl prefix %s", musl_sysroot)

        configure_blueyos = os.path.join(src, "tools", "configure-blueyos.sh")
        if os.path.isfile(configure_blueyos):
            self.run(
                [
                    "bash",
                    configure_blueyos,
                    "--libc=musl",
                    f"--sysroot={musl_sysroot}",
                    f"--build-dir={build_dir}",
                ],
                cwd=src,
            )
        else:
            self.run(
                [
                    configure_script,
                    "--prefix=/usr",
                    "--sysconfdir=/etc",
                    "--localstatedir=/var",
                    "--with-libc=musl",
                    f"--with-blueyos-sysroot={musl_sysroot}",
                    "--enable-blueyos-netctl",
                ],
                cwd=build_dir,
            )

    def build(self) -> None:
        src = self._source_dir
        if not os.path.isdir(src):
            raise RecipeError(
                f"{self.name} source not found at {src}.  Run 'baker prepare' first."
            )

        build_dir = self._build_dir
        if not os.path.isdir(build_dir):
            raise RecipeError(
                f"scout build directory not found at {build_dir}.  Run 'baker configure' first."
            )

        musl_prefix = self._resolve_musl_make_prefix()
        make_flags = self.config.kernel.make_flags.split()
        env = {"MUSL_PREFIX": musl_prefix}

        self.log.info("Building scout in %s with musl prefix %s", build_dir, musl_prefix)
        self.run(["make"] + make_flags, cwd=build_dir, env=env)
    def install(self) -> None:
        build_dir = self._build_dir
        if not os.path.isdir(build_dir):
            self.log.warning("scout build directory not found; skipping install.")
            return

        staging_dir = os.path.join(build_dir, "sysroot-staging")
        if os.path.isdir(staging_dir):
            shutil.rmtree(staging_dir)
        os.makedirs(staging_dir, exist_ok=True)

        self.run(["make", "install", f"DESTDIR={staging_dir}"], cwd=build_dir)
        self.sysroot.install_tree(staging_dir, ".")
        self.log.info("Installed scout payload into %s", self.config.abs_sysroot)

    def package(self) -> str | None:
        build_dir = self._build_dir
        if not os.path.isdir(build_dir):
            raise RecipeError(
                f"scout build directory not found at {build_dir}.  Build first."
            )

        dist_dir = os.path.join(build_dir, "dist")
        os.makedirs(dist_dir, exist_ok=True)
        for existing in glob.glob(os.path.join(dist_dir, "*.dpk")):
            os.remove(existing)

        dpkbuild = self.resolve_dpkbuild()
        musl_prefix = self._resolve_musl_make_prefix()
        env = {
            "PATH": os.path.dirname(dpkbuild) + ":" + os.environ.get("PATH", ""),
            "MUSL_PREFIX": musl_prefix,
        }

        self.run(["make", "package"], cwd=build_dir, env=env)

        dpk_files = sorted(glob.glob(os.path.join(dist_dir, "*.dpk")))
        if not dpk_files:
            raise RecipeError(
                f"make package completed for {self.name}, but no .dpk was produced in {dist_dir}"
            )

        dest = os.path.join(self.config.abs_output_dir, os.path.basename(dpk_files[0]))
        shutil.copy2(dpk_files[0], dest)
        self.log.info("Package: %s", dest)
        return dest
