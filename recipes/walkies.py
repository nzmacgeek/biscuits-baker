"""
recipes/walkies.py - Recipe for walkies.

The upstream walkies repository currently only contains a README, so this
recipe is intentionally tolerant: once upstream grows a Makefile, build script,
or staged payload tree, Baker will consume it. Until then the recipe logs a
warning and skips installation instead of breaking unrelated builds.
"""

from __future__ import annotations

import glob
import os
import shutil

from recipes._musl_package import MuslPackageRecipe
from recipes.base import RecipeError


class WalkiesRecipe(MuslPackageRecipe):
    """walkies - BlueyOS network configuration utility."""

    name = "walkies"
    version = "0.1.0"
    dependencies = ["musl-blueyos", "blueyos-base"]
    install_paths = ["usr/bin/walkies", "etc/interfaces"]

    def build(self) -> None:
        src = self._source_dir
        if not os.path.isdir(src):
            raise RecipeError(
                f"{self.name} source not found at {src}.  Run 'baker prepare' first."
            )

        musl_prefix = self._resolve_musl_make_prefix()
        makefile = os.path.join(src, "Makefile")
        build_script = os.path.join(src, "build.sh")

        if os.path.isfile(makefile):
            self.log.info("Building walkies against musl at %s", musl_prefix)
            self.run(["make"], cwd=src, env={"MUSL_PREFIX": musl_prefix})
            return

        if os.path.isfile(build_script):
            self.log.info("Building walkies via build.sh")
            self.run(["bash", "build.sh"], cwd=src, env={"MUSL_PREFIX": musl_prefix})
            return

        self.log.warning(
            "walkies source at %s does not yet provide build files; skipping build.",
            src,
        )

    def install(self) -> None:
        src = self._source_dir
        installed_payload = False

        # Install config/service files from the payload tree.
        # Note: pkg/payload/sbin/ only contains a .gitkeep placeholder at build time;
        # the walkies binary is not copied there until the dpk/package step.
        for payload_root in [os.path.join(src, "pkg", "payload"), os.path.join(src, "payload")]:
            if os.path.isdir(payload_root):
                self.sysroot.install_tree(payload_root, ".")
                self.log.info("Installed walkies payload into %s", self.config.abs_sysroot)
                installed_payload = True
                break

        # Install the binary separately — it lives in the build output directory.
        binary_candidates = [
            os.path.join(src, "build", "walkies"),
            os.path.join(src, "bin", "walkies"),
            os.path.join(src, "walkies"),
        ]
        for path in binary_candidates:
            if os.path.isfile(path):
                self.sysroot.install_binary(path, "sbin/walkies")
                if not installed_payload:
                    self._install_interfaces_config(src)
                self.log.info("Installed walkies → sysroot/sbin/walkies")
                return

        if not installed_payload:
            self.log.warning("walkies produced no installable payload or binary; skipping install.")

    def package(self) -> str | None:
        src = self._source_dir
        if os.path.isfile(os.path.join(src, "Makefile")):
            dpkbuild = self.resolve_dpkbuild()
            env = {
                "MUSL_PREFIX": self._resolve_musl_make_prefix(),
                "PATH": os.path.dirname(dpkbuild) + ":" + os.environ.get("PATH", ""),
            }
            self.run(["make", "package"], cwd=src, env=env)
            dpk_files = glob.glob(os.path.join(src, "*.dpk"))
            if not dpk_files:
                raise RecipeError(
                    f"make package completed for {self.name}, but no .dpk was produced in {src}"
                )

            dest = os.path.join(
                self.config.abs_output_dir, os.path.basename(dpk_files[0])
            )
            shutil.copy2(dpk_files[0], dest)
            self.log.info("Package: %s", dest)
            return dest

        self.log.warning("walkies does not yet expose a dpk package target; skipping package.")
        return None

    def _install_interfaces_config(self, src: str) -> None:
        config_candidates = [
            os.path.join(src, "etc", "interfaces"),
            os.path.join(src, "config", "interfaces"),
            os.path.join(src, "interfaces"),
        ]
        for path in config_candidates:
            if os.path.isfile(path):
                self.sysroot.install_file(path, "etc/interfaces", mode=0o644)
                return