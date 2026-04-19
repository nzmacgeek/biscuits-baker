"""
recipes/login_tools.py - Recipe for login-tools.

login-tools builds BlueyOS authentication and account-management binaries.
Upstream stages its install image under `pkg/payload/` and packages via the
`build-dpk.sh` helper script.
"""

from __future__ import annotations

import glob
import os
import shutil

from recipes._musl_package import MuslPackageRecipe
from recipes.base import RecipeError


class LoginToolsRecipe(MuslPackageRecipe):
    """login-tools - passwd/login/account management binaries."""

    name = "login-tools"
    version = "1.0.0"
    dependencies = ["musl-blueyos", "blueyos-base"]
    install_paths = [
        "usr/bin/passwd",
        "usr/bin/login",
        "usr/bin/chsh",
        "usr/bin/chmod",
        "usr/bin/chown",
        "usr/bin/chgrp",
        "usr/sbin/setup-root",
        "usr/sbin/useradd",
        "usr/sbin/userdel",
        "usr/sbin/usermod",
        "usr/sbin/groupadd",
        "usr/sbin/groupdel",
        "usr/sbin/groupmod",
        "usr/sbin/userlock",
    ]

    def build(self) -> None:
        src = self._source_dir
        if not os.path.isdir(src):
            raise RecipeError(
                f"{self.name} source not found at {src}.  Run 'baker prepare' first."
            )

        musl_prefix = self._resolve_musl_make_prefix()
        cc = shutil.which("gcc") or shutil.which("cc")
        if not cc:
            raise RecipeError("No host C compiler found for login-tools build.")

        self.log.info("Building %s against musl at %s", self.name, musl_prefix)
        make_flags = self.config.kernel.make_flags.split()
        self.run(
            ["make", f"MUSL_PREFIX={musl_prefix}", f"CC={cc}"] + make_flags,
            cwd=src,
        )

    def install(self) -> None:
        payload_root = os.path.join(self._source_dir, "pkg", "payload")
        if not os.path.isdir(payload_root):
            raise RecipeError(
                "login-tools payload not found.  Expected pkg/payload after build."
            )

        self.sysroot.install_tree(payload_root, ".")
        self.log.info("Installed login-tools payload into %s", self.config.abs_sysroot)

    def package(self) -> str | None:
        src = self._source_dir
        script = os.path.join(src, "build-dpk.sh")
        dpkbuild = self.resolve_dpkbuild()

        if not os.path.isfile(script):
            raise RecipeError(f"build-dpk.sh not found for {self.name} in {src}")

        self.run(
            ["bash", "build-dpk.sh", self.version],
            cwd=src,
            env={
                "PATH": os.path.dirname(dpkbuild) + ":" + os.environ.get("PATH", ""),
                "MUSL_PREFIX": self._resolve_musl_make_prefix(),
                "CC": shutil.which("gcc") or shutil.which("cc") or "",
            },
        )
        dpk_files = glob.glob(os.path.join(src, "*.dpk"))
        if not dpk_files:
            raise RecipeError(
                f"build-dpk.sh completed for {self.name}, but no .dpk was produced in {src}"
            )

        dest = os.path.join(self.config.abs_output_dir, os.path.basename(dpk_files[0]))
        shutil.copy2(dpk_files[0], dest)
        self.log.info("Package: %s", dest)
        return dest
