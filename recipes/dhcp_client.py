"""
recipes/dhcp_client.py — bluey-dhcp DHCP client for BlueyOS

Builds the bluey-dhcp daemon from src/bluey-dhcp/user/.  The daemon performs
a standard DHCP DISCOVER→OFFER→REQUEST→ACK exchange via UDP on the named
interface, then configures the resulting IP address, subnet mask, and default
gateway through the AF_BLUEY_NETCTL kernel control plane (same API as walkies).

Claw integration:
  - bluey-dhcp@eth0.service starts after walkies.service
  - walkies parses 'iface eth0 inet dhcp' and brings the interface UP
  - bluey-dhcp@eth0 then handles the actual DHCP negotiation
"""

from __future__ import annotations

import glob as _glob
import os
import shutil
import subprocess

from recipes.base import BaseRecipe, RecipeError


class DhcpClientRecipe(BaseRecipe):
    """bluey-dhcp — DHCP client daemon for BlueyOS."""

    name = "bluey-dhcp"
    version = "0.1.0"
    dependencies = ["musl-blueyos", "walkies"]

    def _user_src(self) -> str:
        return os.path.join(
            os.path.dirname(__file__), "..", "src", "bluey-dhcp", "user"
        )

    def _pkg_root(self) -> str:
        return os.path.join(
            os.path.dirname(__file__), "..", "src", "bluey-dhcp", "pkg"
        )

    def _musl_gcc(self) -> str:
        candidate = os.path.join(
            self.config.abs_build_dir, "musl", "bin", "musl-gcc"
        )
        if os.path.isfile(candidate):
            return candidate
        raise RecipeError(
            "musl-gcc not found.  Ensure the musl-blueyos recipe has been built."
        )

    def build(self) -> None:
        src = self._user_src()
        if not os.path.isfile(os.path.join(src, "main.c")):
            raise RecipeError(f"bluey-dhcp source not found at {src}")

        musl_gcc = self._musl_gcc()
        sysroot = self.config.abs_sysroot
        env = {
            "CC":      musl_gcc,
            "CFLAGS":  f"-O2 -Wall -I{sysroot}/usr/include",
            "LDFLAGS": "-static",
            "PATH":    os.environ.get("PATH", ""),
        }

        self.log.info("Building bluey-dhcp %s", self.version)
        self.run(["make", "clean"], cwd=src, env=env)
        self.run(["make"], cwd=src, env=env)

        binary = os.path.join(src, "bluey-dhcp")
        if not os.path.isfile(binary):
            raise RecipeError("bluey-dhcp build completed but binary not found")

        out = subprocess.check_output(["file", binary], text=True)
        if "ELF 32-bit" not in out:
            raise RecipeError(
                f"bluey-dhcp binary is not ELF 32-bit: {out.strip()}"
            )
        self.log.info("bluey-dhcp: %s", out.strip())

    def install(self) -> None:
        binary = os.path.join(self._user_src(), "bluey-dhcp")
        if not os.path.isfile(binary):
            self.log.warning("bluey-dhcp binary missing; skipping install")
            return

        self.sysroot.install_binary(binary, "sbin/bluey-dhcp")

        payload = os.path.join(self._pkg_root(), "payload")
        if os.path.isdir(payload):
            self.sysroot.install_tree(payload, ".")

        self._update_claw_manifest()
        self.log.info("Installed bluey-dhcp")

    def package(self) -> str | None:
        binary = os.path.join(self._user_src(), "bluey-dhcp")
        if not os.path.isfile(binary):
            self.log.warning("bluey-dhcp binary missing; skipping package")
            return None

        dpkbuild = self.resolve_dpkbuild()
        pkg_root = self._pkg_root()

        # Ensure the compiled binary is in the package payload
        sbin_payload = os.path.join(pkg_root, "payload", "sbin")
        os.makedirs(sbin_payload, exist_ok=True)
        shutil.copy2(binary, os.path.join(sbin_payload, "bluey-dhcp"))

        repo_root = os.path.dirname(pkg_root)
        env = {
            "PATH": os.path.dirname(dpkbuild) + ":" + os.environ.get("PATH", ""),
        }
        build_sh = os.path.join(repo_root, "build-dpk.sh")
        if os.path.isfile(build_sh):
            self.run(["bash", build_sh], cwd=repo_root, env=env)
        else:
            self.run(
                [dpkbuild, "pkg/meta/manifest.json", "pkg/payload"],
                cwd=repo_root,
                env=env,
            )

        dpk_files = _glob.glob(os.path.join(repo_root, "*.dpk"))
        if not dpk_files:
            raise RecipeError(
                "dpkbuild completed for bluey-dhcp but no .dpk was produced"
            )

        dest = os.path.join(
            self.config.abs_output_dir, os.path.basename(dpk_files[0])
        )
        shutil.copy2(dpk_files[0], dest)
        self.log.info("Package: %s", dest)
        return dest

    def _update_claw_manifest(self) -> None:
        manifest_path = os.path.join(
            self.config.abs_sysroot, "etc", "claw", "units.manifest"
        )
        if not os.path.isfile(manifest_path):
            return

        desired = ["/etc/claw/services.d/bluey-dhcp@.yml"]
        with open(manifest_path, "r", encoding="utf-8", errors="replace") as fh:
            lines = [line.rstrip("\n") for line in fh]

        changed = False
        for entry in desired:
            if entry not in lines:
                lines.append(entry)
                changed = True

        if changed:
            with open(manifest_path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines) + "\n")
            self.log.info("Updated units.manifest with bluey-dhcp claw service")
