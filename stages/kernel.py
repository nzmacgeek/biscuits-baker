"""
stages/kernel.py - Kernel build stage for Baker.

Builds the Biscuits kernel using its native Makefile, then installs the
kernel image into the sysroot.  The biscuits kernel output is always at
``build/kernel/bkernel`` relative to the kernel source tree.
"""

from __future__ import annotations

import os
import shutil
import subprocess

from helpers.host_tools import build_host_env
from stage_runner import Stage


class KernelStage(Stage):
    """Build the Biscuits kernel."""

    name = "kernel"

    def run(self) -> None:
        cfg = self.config
        src = cfg.abs_kernel_source

        if not os.path.isdir(src):
            self.log.warning(
                "Kernel source directory not found at %s.  Run 'baker prepare' first.",
                src,
            )
            return

        self.log.info("Building biscuits kernel in %s", src)

        make_flags = cfg.kernel.make_flags.split()

        # Step 1: build host-side helper tools (mkfs, list, fsck for BlueyFS)
        self.log.info("Building host tools (make tools-host)")
        self._make(["make", "tools-host"] + make_flags, src)

        # Step 2: build the kernel itself
        self.log.info("Building kernel (make %s)", " ".join(make_flags))
        self._make(["make"] + make_flags, src)

        # Step 3: install the kernel image into sysroot/boot/
        boot_dir = os.path.join(cfg.abs_sysroot, "boot")
        os.makedirs(boot_dir, exist_ok=True)

        # biscuits always outputs to build/kernel/bkernel
        bkernel_path = os.path.join(src, "build", "kernel", "bkernel")
        if os.path.exists(bkernel_path):
            dest = os.path.join(boot_dir, "bkernel")
            shutil.copy2(bkernel_path, dest)
            self.log.info("Kernel image installed: %s → %s", bkernel_path, dest)
        else:
            # Fallback scan for other common output locations
            fallbacks = [
                "vmlinux",
                "vmlinuz",
                os.path.join("build", "bkernel"),
            ]
            found = False
            for candidate in fallbacks:
                candidate_path = os.path.join(src, candidate)
                if os.path.exists(candidate_path):
                    dest = os.path.join(boot_dir, os.path.basename(candidate_path))
                    shutil.copy2(candidate_path, dest)
                    self.log.info("Kernel image installed: %s → %s", candidate_path, dest)
                    found = True
                    break
            if not found:
                self.log.warning(
                    "No kernel image found after build.  "
                    "Expected: %s", bkernel_path
                )

        # Step 4: copy grub.cfg from biscuits source into sysroot/boot/ if present
        grub_cfg_src = os.path.join(src, "grub.cfg")
        if os.path.exists(grub_cfg_src):
            shutil.copy2(grub_cfg_src, os.path.join(boot_dir, "grub.cfg"))
            self.log.info("Copied grub.cfg to sysroot/boot/")

        self.log.info("Kernel stage complete.")

    # ------------------------------------------------------------------

    def _make(self, cmd: list, cwd: str) -> None:
        if shutil.which("make") is None:
            self.log.warning("make not found; skipping: %s", " ".join(cmd))
            return
        self.log.debug("Running: %s (cwd=%s)", " ".join(cmd), cwd)
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            env=build_host_env(),
        )
        if result.stdout:
            self.log.debug(result.stdout.rstrip())
        if result.stderr:
            self.log.debug(result.stderr.rstrip())
        if result.returncode != 0:
            raise RuntimeError(
                f"make failed (exit {result.returncode}):\n{result.stderr[-2000:]}"
            )
