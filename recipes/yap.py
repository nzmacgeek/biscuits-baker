"""
recipes/yap.py - Recipe for yap (BlueyOS syslog daemon).

yap is built against musl-blueyos and installs its daemon binaries plus claw
service units and configuration into the target sysroot.
"""

from __future__ import annotations

import glob
import os
import shutil

from recipes._musl_package import MuslPackageRecipe
from recipes.base import RecipeError


class YapRecipe(MuslPackageRecipe):
    """yap - BlueyOS syslog daemon and log rotation helper."""

    name = "yap"
    version = "0.2.0"
    dependencies = ["musl-blueyos", "claw"]
    install_paths = [
        "sbin/yap",
        "sbin/yap-rotate",
        "etc/yap.yml",
        "etc/claw/services.d/yap.service.yml",
        "etc/claw/services.d/yap-rotate.service.yml",
    ]

    def install(self) -> None:
        src = self._source_dir
        if not os.path.isdir(src):
            raise RecipeError(
                f"{self.name} source not found at {src}.  Run 'baker prepare' first."
            )
        staging_dir = os.path.join(self._build_dir, "sysroot-staging")
        if os.path.isdir(staging_dir):
            shutil.rmtree(staging_dir)
        os.makedirs(staging_dir, exist_ok=True)

        env = {"MUSL_PREFIX": self._resolve_musl_make_prefix()}
        self.run(["make", "install", f"SYSROOT={staging_dir}"], cwd=src, env=env)
        self.sysroot.install_tree(staging_dir, ".")
        self._update_claw_manifest()
        self.log.info("Installed yap payload into %s", self.config.abs_sysroot)

    def package(self) -> str | None:
        src = self._source_dir
        for existing in glob.glob(os.path.join(src, "yap-*.dpk")):
            os.remove(existing)

        dpkbuild = self.resolve_dpkbuild()
        env = {
            "MUSL_PREFIX": self._resolve_musl_make_prefix(),
            "PATH": os.path.dirname(dpkbuild) + ":" + os.environ.get("PATH", ""),
        }

        self.run(["make", "package"], cwd=src, env=env)

        dpk_files = glob.glob(os.path.join(src, f"yap-{self.version}*.dpk"))
        if not dpk_files:
            dpk_files = glob.glob(os.path.join(src, "yap-*.dpk"))
        if not dpk_files:
            raise RecipeError(
                f"make package completed for {self.name}, but no .dpk was produced in {src}"
            )

        dpk_file = max(dpk_files, key=os.path.getmtime)
        dest = os.path.join(self.config.abs_output_dir, os.path.basename(dpk_file))
        shutil.copy2(dpk_file, dest)
        self.log.info("Package: %s", dest)
        return dest

    def _update_claw_manifest(self) -> None:
        manifest_path = os.path.join(self.config.abs_sysroot, "etc", "claw", "units.manifest")
        if not os.path.isfile(manifest_path):
            return

        desired_entries = [
            "/etc/claw/services.d/yap.service.yml",
            "/etc/claw/services.d/yap-rotate.service.yml",
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
