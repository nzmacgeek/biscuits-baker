"""
recipes/dropbear.py - Dropbear SSH server/client for BlueyOS (i386, static musl).

Dropbear bundles its own crypto (libtomcrypt/libtommath) so it does NOT
depend on OpenSSL.  zlib compression is disabled to keep the dependency
list minimal.

Produces statically-linked i386 binaries:
  /usr/sbin/dropbear   — SSH server daemon
  /usr/bin/dbclient    — SSH client
  /usr/bin/dropbearkey — key generation tool
  /usr/bin/dropbearconvert — key conversion tool

A claw service unit is installed so dropbear starts automatically.
"""

from __future__ import annotations

import os
import shutil

from recipes._port_recipe import PortRecipe
from recipes.base import RecipeError

_VERSION = "2024.86"


class DropbearRecipe(PortRecipe):
    name = "dropbear"
    version = _VERSION
    description = "Lightweight SSH server and client (static, i386)"
    dependencies = ["musl-blueyos"]
    install_paths = [
        "usr/sbin/dropbear",
        "usr/bin/dbclient",
        "usr/bin/dropbearkey",
        "etc/claw/services.d/dropbear.yml",
    ]
    pkg_depends = []

    tarball_url = (
        f"https://matt.ucc.asn.au/dropbear/releases/dropbear-{_VERSION}.tar.bz2"
    )
    tarball_name = f"dropbear-{_VERSION}.tar.bz2"
    src_subdir = f"dropbear-{_VERSION}"

    def build(self) -> None:
        src = self._source_dir
        if not os.path.isdir(src):
            raise RecipeError(
                f"dropbear source not found at {src}. Run 'baker prepare' first."
            )

        musl_gcc = self._musl_gcc()
        sysroot = self.config.abs_sysroot
        env = {
            "CC": musl_gcc,
            "CFLAGS": f"-O2 -I{sysroot}/usr/include",
            "LDFLAGS": f"-L{sysroot}/usr/lib -static",
        }

        self.log.info("Configuring dropbear %s for i386 static musl", self.version)
        self.run(
            [
                "./configure",
                *self._autoconf_host_flags,
                "--prefix=/usr",
                "--sbindir=/usr/sbin",
                "--sysconfdir=/etc/dropbear",
                "--disable-zlib",
                "--disable-pam",
                "--disable-utmp",
                "--disable-wtmp",
                "--disable-lastlog",
                "--disable-loginfunc",
                "--enable-bundled-libtom",
                "PROGRAMS=dropbear dbclient dropbearkey dropbearconvert",
            ],
            cwd=src,
            env=env,
        )

        self.log.info("Building dropbear %s", self.version)
        make_flags = self.config.kernel.make_flags.split()
        self.run(
            ["make"] + make_flags + ["PROGRAMS=dropbear dbclient dropbearkey dropbearconvert"],
            cwd=src,
            env=env,
        )

    def install(self) -> None:
        src = self._source_dir
        staging = self._staging_dir
        os.makedirs(staging, exist_ok=True)

        self.log.info("Installing dropbear into staging at %s", staging)
        self.run(
            ["make", f"DESTDIR={staging}", "install",
             "PROGRAMS=dropbear dbclient dropbearkey dropbearconvert"],
            cwd=src,
        )

        # Install claw service unit for the SSH daemon.
        self._install_claw_unit(staging)

    def _install_claw_unit(self, staging: str) -> None:
        """Write a claw service unit for dropbear into the staging tree."""
        services_dir = os.path.join(staging, "etc", "claw", "services.d")
        os.makedirs(services_dir, exist_ok=True)

        unit_content = """\
# claw service unit for the Dropbear SSH daemon
name: dropbear
description: Dropbear SSH server
type: oneshot
exec: /usr/sbin/dropbear -R -F -E
after:
  - claw-network.target
wanted_by:
  - claw-multiuser.target
"""
        unit_path = os.path.join(services_dir, "dropbear.yml")
        with open(unit_path, "w") as fh:
            fh.write(unit_content)

        # Ensure host-keys directory exists so dropbear can generate keys
        hostkey_dir = os.path.join(staging, "etc", "dropbear")
        os.makedirs(hostkey_dir, exist_ok=True)

    def _update_claw_manifest(self) -> None:
        """Register the dropbear claw unit in units.manifest."""
        manifest_path = os.path.join(
            self.config.abs_sysroot, "etc", "claw", "units.manifest"
        )
        if not os.path.exists(manifest_path):
            return
        with open(manifest_path) as fh:
            existing = fh.read()
        entry = "services.d/dropbear.yml\n"
        if entry not in existing:
            with open(manifest_path, "a") as fh:
                fh.write(entry)
            self.log.info("Registered dropbear in claw units.manifest")
