"""
recipes/claw.py - Recipe for claw (init system for BlueyOS).

claw's source tree ships a standalone BlueyOS build script that configures an
out-of-tree musl/static build and stages the full payload layout. Baker uses
that supported path so local source-tree configure artefacts do not poison the
image build.
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess

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

        script = os.path.join(src, "scripts", "build-standalone.sh")
        if not os.path.isfile(script):
            raise RecipeError(f"claw standalone build script not found at {script}")

        if os.path.isfile(os.path.join(src, "config.status")) and os.path.isfile(
            os.path.join(src, "Makefile")
        ):
            self.log.info("Cleaning existing in-tree claw configure output from %s", src)
            self.run(["make", "distclean"], cwd=src)

        self.ensure_build_dir()

    def _standalone_build_dir(self) -> str:
        return os.path.join(self._build_dir, "standalone-build")

    def _standalone_sysroot(self) -> str:
        return os.path.join(self._build_dir, "sysroot-staging")

    def _standalone_env(self) -> dict[str, str]:
        musl_prefix = self._resolve_musl_make_prefix()
        env = {"MUSL_PREFIX": musl_prefix}

        # musl-gcc generates target-arch binaries that cannot run on the build host.
        # Detect the triplet so build-standalone.sh passes --host to configure.
        musl_gcc = os.path.join(musl_prefix, "bin", "musl-gcc")
        if os.path.isfile(musl_gcc) and os.access(musl_gcc, os.X_OK):
            try:
                triplet = subprocess.check_output(
                    [musl_gcc, "-dumpmachine"],
                    stderr=subprocess.DEVNULL,
                    text=True,
                    timeout=10,
                ).strip()
                if triplet:
                    env["HOST_TRIPLET"] = triplet
            except Exception:
                pass

        return env

    def build(self) -> None:
        src = self._source_dir
        if not os.path.isdir(src):
            raise RecipeError(
                f"{self.name} source not found at {src}.  Run 'baker prepare' first."
            )

        script = os.path.join(src, "scripts", "build-standalone.sh")
        build_dir = self._standalone_build_dir()
        if os.path.isdir(build_dir):
            shutil.rmtree(build_dir)

        self.log.info("Building %s via standalone musl build in %s", self.name, build_dir)
        self.run(["bash", script, build_dir], cwd=src, env=self._standalone_env())

    def install(self) -> None:
        src = self._source_dir
        script = os.path.join(src, "scripts", "build-standalone.sh")
        build_dir = self._standalone_build_dir()
        staging_dir = self._standalone_sysroot()
        if os.path.isdir(staging_dir):
            shutil.rmtree(staging_dir)

        env = self._standalone_env()
        env["STAGING_DIR"] = staging_dir
        self.run(["bash", script, build_dir], cwd=src, env=env)

        self.sysroot.install_tree(staging_dir, ".")
        self.sysroot.symlink("/sbin/claw", "sbin/init")
        self.sysroot.symlink("/sbin/claw", "bin/init")
        self._merge_units_manifest()
        self.log.info("Installed claw payload into %s", self.config.abs_sysroot)

    def package(self) -> str | None:
        src = self._source_dir
        dist_dir = os.path.join(self._build_dir, "dist")
        os.makedirs(dist_dir, exist_ok=True)
        for existing in glob.glob(os.path.join(dist_dir, "*.dpk")):
            os.remove(existing)

        staging_dir = self._standalone_sysroot()
        if not os.path.isdir(staging_dir):
            raise RecipeError(f"claw staging dir not found at {staging_dir}; run install first")

        self.run(
            ["bash", os.path.join(src, "scripts", "package-dimsim.sh"), staging_dir, dist_dir],
            cwd=src,
        )

        dpk_files = sorted(glob.glob(os.path.join(dist_dir, "*.dpk")))
        if not dpk_files:
            raise RecipeError(
                f"package-dimsim.sh completed for {self.name}, but no .dpk was produced in {dist_dir}"
            )

        dest = os.path.join(self.config.abs_output_dir, os.path.basename(dpk_files[0]))
        shutil.copy2(dpk_files[0], dest)
        self.log.info("Package: %s", dest)
        return dest

    def _merge_units_manifest(self) -> None:
        manifest_path = os.path.join(self.config.abs_sysroot, "etc", "claw", "units.manifest")
        claw_dir = os.path.join(self.config.abs_sysroot, "etc", "claw")
        if not os.path.isfile(manifest_path) or not os.path.isdir(claw_dir):
            return

        with open(manifest_path, "r", encoding="utf-8", errors="replace") as fh:
            lines = [line.rstrip("\n") for line in fh]

        desired_entries = []
        for subdir in ("services.d", "targets.d"):
            full_dir = os.path.join(claw_dir, subdir)
            if not os.path.isdir(full_dir):
                continue
            for entry in sorted(os.listdir(full_dir)):
                if not entry.endswith(".yml"):
                    continue
                manifest_entry = f"/etc/claw/{subdir}/{entry}"
                if manifest_entry not in desired_entries:
                    desired_entries.append(manifest_entry)

        changed = False
        for entry in desired_entries:
            if entry not in lines:
                lines.append(entry)
                changed = True

        if changed:
            with open(manifest_path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines) + "\n")
