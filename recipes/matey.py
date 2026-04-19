"""
recipes/matey.py - Recipe for matey (getty for BlueyOS).

matey is a single-file C program linked statically against musl-blueyos.
Its Makefile accepts ``MUSL_PREFIX`` and produces ``build/matey``.
``make package`` uses dpkbuild to create a ``.dpk``.
"""

from __future__ import annotations

import os

from recipes._musl_package import MuslPackageRecipe


class MateyRecipe(MuslPackageRecipe):
    """matey — getty / login prompt for BlueyOS."""

    name = "matey"
    version = "1.0.0"
    dependencies = ["musl-blueyos", "claw"]
    binary_name = "matey"
    binary_dest = "sbin/matey"
    install_paths = [
        "sbin/matey",
        "etc/claw/services.d/matey@tty1.yml",
        "etc/claw/services.d/matey@tty2.yml",
        "etc/claw/services.d/matey@tty3.yml",
        "etc/claw/targets.d/claw-multiuser.target.yml",
    ]

    def install(self) -> None:
        payload_root = os.path.join(self._source_dir, "pkg", "payload")
        built_binary = os.path.join(self._source_dir, "build", "matey")
        if os.path.isdir(payload_root):
            self.sysroot.install_tree(payload_root, ".")
            if os.path.isfile(built_binary):
                self.sysroot.install_binary(built_binary, "sbin/matey")
            self._update_claw_manifest()
            self.log.info("Installed matey payload into %s", self.config.abs_sysroot)
            return

        super().install()

    def _update_claw_manifest(self) -> None:
        manifest_path = os.path.join(self.config.abs_sysroot, "etc", "claw", "units.manifest")
        if not os.path.isfile(manifest_path):
            return

        desired_entries = [
            "/etc/claw/services.d/matey@tty1.yml",
            "/etc/claw/services.d/matey@tty2.yml",
            "/etc/claw/services.d/matey@tty3.yml",
            "/etc/claw/targets.d/claw-multiuser.target.yml",
        ]

        with open(manifest_path, "r", encoding="utf-8", errors="replace") as fh:
            lines = [line.rstrip("\n") for line in fh]

        changed = False
        for entry in desired_entries:
            if entry not in lines:
                lines.append(entry)
                changed = True

        if changed:
            with open(manifest_path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines) + "\n")
