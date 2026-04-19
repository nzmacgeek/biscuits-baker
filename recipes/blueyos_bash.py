"""recipes/blueyos_bash.py - Shared recipe base for the blueyos-bash repo.

The upstream ``blueyos-bash`` repository builds three independent packages from
one checkout: ``ncurses``, ``readline``, and ``bash``. Each stages its payload
under ``<pkg>/payload`` and can be packaged independently.
"""

from __future__ import annotations

import glob
import os
import shutil

from recipes._musl_package import MuslPackageRecipe
from recipes.base import RecipeError


class BlueyosBashRepoRecipe(MuslPackageRecipe):
    """Shared base for repo-backed package recipes from blueyos-bash."""

    build_target: str = ""
    payload_subdir: str = ""

    def __init__(self, config):
        super().__init__(config)
        self._source_dir = os.path.join(config.abs_sources_dir, "blueyos-bash")
        self._build_dir = os.path.join(config.abs_build_dir, "blueyos-bash")

    def build(self) -> None:
        src = self._source_dir
        if not os.path.isdir(src):
            raise RecipeError(
                f"{self.name} source not found at {src}.  Run 'baker prepare' first."
            )

        musl_prefix = self._resolve_musl_make_prefix()
        self.log.info("Building %s against musl at %s", self.name, musl_prefix)
        self.run(["make", self.build_target], cwd=src, env={"MUSL_PREFIX": musl_prefix})

    def install(self) -> None:
        payload_root = os.path.join(self._source_dir, self.payload_subdir, "payload")
        if not os.path.isdir(payload_root):
            self.log.warning("%s payload not found after build; skipping install.", self.name)
            return

        self.sysroot.install_tree(payload_root, ".")
        self._ensure_root_uses_bash()
        self.log.info("Installed %s payload into %s", self.name, self.config.abs_sysroot)

    def _ensure_root_uses_bash(self) -> None:
        passwd_path = os.path.join(self.config.abs_sysroot, "etc", "passwd")
        if os.path.isfile(passwd_path):
            lines = []
            changed = False
            with open(passwd_path, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if line.startswith("root:"):
                        parts = line.rstrip("\n").split(":")
                        if len(parts) >= 7 and parts[6] != "/bin/bash":
                            parts[6] = "/bin/bash"
                            line = ":".join(parts) + "\n"
                            changed = True
                    lines.append(line)
            if changed:
                with open(passwd_path, "w", encoding="utf-8") as fh:
                    fh.writelines(lines)

        shells_path = os.path.join(self.config.abs_sysroot, "etc", "shells")
        os.makedirs(os.path.dirname(shells_path), exist_ok=True)
        existing = []
        if os.path.isfile(shells_path):
            with open(shells_path, "r", encoding="utf-8", errors="replace") as fh:
                existing = [line.rstrip("\n") for line in fh]
        for shell in ("/bin/sh", "/bin/bash"):
            if shell not in existing:
                existing.append(shell)
        with open(shells_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(existing) + "\n")

    def package(self) -> str | None:
        src = self._source_dir

        dpkbuild = self.resolve_dpkbuild()
        env = {
            "PATH": os.path.dirname(dpkbuild) + ":" + os.environ.get("PATH", ""),
        }
        self.run(
            ["dpkbuild", "build", f"{self.payload_subdir}/"],
            cwd=src,
            env=env,
        )
        dpk_files = glob.glob(
            os.path.join(src, f"{self.name}-*.dpk")
        )
        if not dpk_files:
            raise RecipeError(
                f"dpkbuild completed for {self.name}, but no .dpk was produced in {src}"
            )

        latest = max(dpk_files, key=os.path.getmtime)
        dest = os.path.join(self.config.abs_output_dir, os.path.basename(latest))
        shutil.copy2(latest, dest)
        self.log.info("Package: %s", dest)
        return dest


class BashRecipe(BlueyosBashRepoRecipe):
    """GNU Bash shell built from the blueyos-bash repo."""

    name = "bash"
    version = "5.2.21"
    dependencies = ["musl-blueyos", "ncurses", "readline"]
    build_target = "bash"
    payload_subdir = "bash"
    install_paths = ["bin/bash", "bin/sh"]
