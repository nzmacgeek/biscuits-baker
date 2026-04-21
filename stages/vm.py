"""
stages/vm.py - VM launch stage for Baker.

Boots the BlueyOS disk image in QEMU for interactive testing.  By default the
image is opened in snapshot mode so the on-disk image is never modified.

Usage:
    baker vm                  # launch with config defaults
    baker vm --build          # rebuild image then launch
    baker vm --fresh          # clean sysroot, rebuild all components + image, then launch
    baker vm --no-snapshot    # persistent boot (image is written to)
    baker vm --display gtk    # graphical window instead of serial console
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess

from stage_runner import Stage

logger = logging.getLogger(__name__)

QEMU_BINARY = "qemu-system-i386"


def _resolve_image_path(cfg) -> str:
    """Return the absolute path to the configured disk image."""
    p = cfg.image.output
    return p if os.path.isabs(p) else os.path.join(os.getcwd(), p)


class VmStage(Stage):
    """Boot the BlueyOS disk image in QEMU."""

    name = "vm"

    # Set by baker.py before run() is called
    build_image_first: bool = False
    fresh_build: bool = False          # clean sysroot+output, rebuild all, rebuild image
    snapshot_override: bool | None = None   # None = use cfg.vm.snapshot
    ram_override: int | None = None
    cpus_override: int | None = None
    display_override: str | None = None

    def run(self) -> None:
        cfg = self.config

        if not shutil.which(QEMU_BINARY):
            raise RuntimeError(
                f"{QEMU_BINARY} not found on PATH. "
                "Install qemu-system-x86 (or qemu-system-i386) to use 'baker vm'."
            )

        if self.fresh_build:
            self._fresh_rebuild(cfg)
        elif self.build_image_first:
            from stages.image import ImageStage
            image_stage = ImageStage(cfg)
            image_stage.run()

        image_path = _resolve_image_path(cfg)
        if not os.path.isfile(image_path):
            raise RuntimeError(
                f"Disk image not found: {image_path}\n"
                "Run 'baker image' (or 'baker vm --build') to create it first."
            )

        vm = cfg.vm
        ram_mb = self.ram_override if self.ram_override is not None else vm.ram_mb
        cpus = self.cpus_override if self.cpus_override is not None else vm.cpus
        display = self.display_override if self.display_override is not None else vm.display
        use_snapshot = self.snapshot_override if self.snapshot_override is not None else vm.snapshot

        cmd = self._build_qemu_cmd(cfg, image_path, ram_mb, cpus, display, use_snapshot)

        self.log.info("Disk image : %s", image_path)
        self.log.info("RAM: %dMB  CPUs: %d  Display: %s  Snapshot: %s",
                      ram_mb, cpus, display, use_snapshot)
        if use_snapshot:
            self.log.info("Running in snapshot mode — disk image will NOT be modified")
        else:
            self.log.warning("Snapshot disabled — disk image will be modified by this run")
        self.log.info("QEMU command: %s", " ".join(cmd))

        result = subprocess.run(cmd)
        if result.returncode not in (0, 1):
            # QEMU exits 1 on normal shutdown; anything else is an error
            raise RuntimeError(f"QEMU exited with code {result.returncode}")

    def _fresh_rebuild(self, cfg) -> None:
        """Wipe sysroot + output, rebuild all components, rebuild the disk image."""
        import shutil as _shutil

        for path, label in [
            (cfg.abs_sysroot, "sysroot"),
            (cfg.abs_output_dir, "output"),
        ]:
            if os.path.isdir(path):
                self.log.info("Cleaning %s: %s", label, path)
                _shutil.rmtree(path)

        self.log.info("Rebuilding all components...")
        from stages.build import BuildStage
        build_stage = BuildStage(cfg)
        build_stage.run()

        self.log.info("Rebuilding disk image...")
        from stages.image import ImageStage
        image_stage = ImageStage(cfg)
        image_stage.run()

    def _build_qemu_cmd(self, cfg, image_path: str, ram_mb: int, cpus: int,
                        display: str, snapshot: bool) -> list[str]:
        vm = cfg.vm
        cmd = [
            QEMU_BINARY,
            "-drive", f"file={image_path},format=raw,if=ide,index=0",
            "-boot", "c",
            "-m", f"{ram_mb}M",
            "-smp", str(cpus),
            "-netdev", "user,id=usernet",
            "-device", "ne2k_pci,netdev=usernet",
            "-no-reboot",
            "-no-shutdown",
        ]

        if snapshot:
            cmd.append("-snapshot")

        use_kvm = vm.kvm == "enabled" or (
            vm.kvm == "auto" and os.access("/dev/kvm", os.R_OK | os.W_OK)
        )
        if use_kvm:
            cmd.append("-enable-kvm")

        if display == "gtk":
            cmd += ["-display", "gtk", "-vga", "std", "-serial", "stdio"]
        else:
            # none/headless: serial to stdio so the console is interactive
            cmd += ["-display", "none", "-serial", "stdio"]

        # Optional FAT log disk produced alongside the disk image
        log_disk = os.path.join(cfg.abs_kernel_source, "build", "blueyos-log-fat.img")
        if os.path.isfile(log_disk):
            cmd += ["-drive", f"file={log_disk},format=raw,if=ide,index=1"]

        cmd += vm.extra_args
        return cmd
