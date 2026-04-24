"""
recipes/walkies.py - Recipe for walkies.

Builds the walkies network configuration daemon from the nzmacgeek/walkies
repository. Walkies reads /etc/interfaces and configures the BlueyOS TCP/IP
stack via the AF_BLUEY_NETCTL kernel control plane socket. It runs as a claw
oneshot service in the claw-network.target boot stage.
"""

from __future__ import annotations

import glob
import os
import shutil

from recipes._musl_package import MuslPackageRecipe
from recipes.base import RecipeError


class WalkiesRecipe(MuslPackageRecipe):
    """walkies - BlueyOS network configuration daemon."""

    name = "walkies"
    version = "0.1.0"
    dependencies = ["musl-blueyos", "blueyos-base"]
    install_paths = ["sbin/walkies", "etc/interfaces"]

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

        raise RecipeError(
            f"walkies source at {src} has no Makefile or build.sh. "
            "Run 'baker prepare' to fetch the latest source."
        )

    def install(self) -> None:
        src = self._source_dir
        installed_payload = False

        # Install claw service units, /etc/interfaces, and other payload files.
        # pkg/payload/sbin/ contains only a .gitkeep; the binary is installed below.
        for payload_root in [os.path.join(src, "pkg", "payload"), os.path.join(src, "payload")]:
            if os.path.isdir(payload_root):
                self.sysroot.install_tree(payload_root, ".")
                self.log.info("Installed walkies payload into %s", self.config.abs_sysroot)
                installed_payload = True
                break

        # Install the compiled binary from the build output directory.
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
                break
        else:
            if not installed_payload:
                self.log.warning(
                    "walkies produced no installable payload or binary; skipping install."
                )
            return

        self._update_claw_manifest()

    def package(self) -> str | None:
        src = self._source_dir
        if not os.path.isfile(os.path.join(src, "Makefile")):
            self.log.warning("walkies has no Makefile; skipping package.")
            return None

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

        dest = os.path.join(self.config.abs_output_dir, os.path.basename(dpk_files[0]))
        shutil.copy2(dpk_files[0], dest)
        self.log.info("Package: %s", dest)
        return dest

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

    def _update_claw_manifest(self) -> None:
        manifest_path = os.path.join(
            self.config.abs_sysroot, "etc", "claw", "units.manifest"
        )
        if not os.path.isfile(manifest_path):
            return

        desired_entries = [
            "/etc/claw/services.d/walkies.yml",
            "/etc/claw/services.d/walkies-monitor.yml",
            "/etc/claw/targets.d/claw-network.target.yml",
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
            self.log.info("Updated units.manifest with walkies claw service entries")