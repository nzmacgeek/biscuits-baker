"""
stages/kernel.py - Kernel build stage for Baker.

Configures and builds the Biscuits kernel, then installs the kernel
image and modules into the sysroot.
"""

from __future__ import annotations

import os
import shutil
import subprocess

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

        self.log.info("Building kernel in %s", src)

        # Apply .config if available
        kconfig = os.path.join(src, cfg.kernel.config)
        if os.path.exists(kconfig):
            self.log.info("Using kernel config: %s", kconfig)
        else:
            self.log.info("No .config found; running make defconfig")
            self._make(["make", "defconfig"], src)

        # Build the kernel
        make_flags = cfg.kernel.make_flags.split()
        self.log.info("Running make %s", " ".join(make_flags))
        self._make(["make"] + make_flags + [f"ARCH={cfg.arch}"], src)

        # Install the kernel image into sysroot/boot/
        boot_dir = os.path.join(cfg.abs_sysroot, "boot")
        os.makedirs(boot_dir, exist_ok=True)

        # Look for common kernel image files
        image_candidates = [
            "arch/x86/boot/bzImage",
            "arch/x86_64/boot/bzImage",
            "vmlinux",
            "vmlinuz",
        ]
        for candidate in image_candidates:
            candidate_path = os.path.join(src, candidate)
            if os.path.exists(candidate_path):
                dest = os.path.join(boot_dir, "vmlinuz")
                shutil.copy2(candidate_path, dest)
                self.log.info("Kernel image installed: %s → %s", candidate_path, dest)
                break
        else:
            self.log.warning("No kernel image found after build.")

        # Install modules if configured
        if cfg.kernel.install_modules:
            self.log.info("Installing kernel modules")
            self._make(
                [
                    "make",
                    "modules_install",
                    f"ARCH={cfg.arch}",
                    f"INSTALL_MOD_PATH={cfg.abs_sysroot}",
                ],
                src,
            )

        self.log.info("Kernel stage complete.")

    # ------------------------------------------------------------------

    def _make(self, cmd: list, cwd: str) -> None:
        if shutil.which("make") is None:
            self.log.warning("make not found; skipping: %s", " ".join(cmd))
            return
        self.log.debug("Running: %s", " ".join(cmd))
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"make failed (exit {result.returncode}):\n{result.stderr}"
            )
