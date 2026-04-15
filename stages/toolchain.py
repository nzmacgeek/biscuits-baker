"""
stages/toolchain.py - Toolchain and musl-blueyos build stage for Baker.

This stage:
1. Runs ``tools/make-libc-toolchain.sh`` from the biscuits repo to build the
   i686-elf cross-compiler and install it to ``toolchain_prefix``
   (default: /opt/blueyos-cross).
2. Runs ``tools/build-musl.sh`` from the biscuits repo to clone musl-blueyos
   (into ``<kernel_source>/musl-blueyos``) and build/install it to:
   - ``build/musl``           (repo-local, used by recipe builds)
   - ``/opt/blueyos-sysroot`` (runtime sysroot, used by ``make disk``)
   - ``/opt/blueyos-cross/musl`` (alongside the cross toolchain)

Both scripts are idempotent: re-running the stage after a successful build
is fast because they skip already-installed artefacts.
"""

from __future__ import annotations

import os
import shutil
import subprocess

from stage_runner import Stage


class ToolchainStage(Stage):
    """Build the cross-compiler toolchain and musl-blueyos."""

    name = "toolchain"

    def run(self) -> None:
        cfg = self.config
        src = cfg.abs_kernel_source

        if not os.path.isdir(src):
            self.log.warning(
                "Kernel source not found at %s.  Run 'baker prepare' first.", src
            )
            return

        # ------------------------------------------------------------------
        # 1. Cross-compiler toolchain (i686-elf binutils + GCC)
        # ------------------------------------------------------------------
        toolchain_script = os.path.join(src, "tools", "make-libc-toolchain.sh")
        if os.path.isfile(toolchain_script):
            # Check if the cross-compiler is already installed to avoid a long rebuild
            gcc_bin = os.path.join(cfg.toolchain_prefix, "bin", "i686-elf-gcc")
            if os.path.isfile(gcc_bin):
                self.log.info(
                    "Cross-compiler already installed at %s; skipping build.", gcc_bin
                )
            else:
                self.log.info(
                    "Building cross-compiler toolchain via %s", toolchain_script
                )
                self.log.info(
                    "This downloads binutils + GCC sources and takes several minutes."
                )
                self._run_script(toolchain_script, cwd=src)
        else:
            self.log.info(
                "tools/make-libc-toolchain.sh not found in %s; skipping cross-compiler build.",
                src,
            )

        # ------------------------------------------------------------------
        # 2. musl-blueyos build and install
        # ------------------------------------------------------------------
        musl_script = os.path.join(src, "tools", "build-musl.sh")
        if not os.path.isfile(musl_script):
            self.log.warning(
                "tools/build-musl.sh not found in %s; cannot build musl.", src
            )
            return

        musl_source = os.path.join(src, "musl-blueyos")
        if not os.path.isdir(musl_source):
            self.log.warning(
                "musl-blueyos source not found at %s.  Run 'baker prepare' first.",
                musl_source,
            )
            return

        local_prefix = os.path.join(cfg.abs_build_dir, "musl")
        os.makedirs(local_prefix, exist_ok=True)

        self.log.info("Building musl-blueyos via %s", musl_script)
        self.log.info("  local prefix  : %s", local_prefix)
        self.log.info("  sysroot dest  : /opt/blueyos-sysroot")
        self.log.info("  cross prefix  : /opt/blueyos-cross/musl")

        # Build args: only install to local prefix unless running as root
        # (sysroot and cross-prefix installs to /opt/... require elevated perms)
        build_args = [
            "bash",
            musl_script,
            f"--source={musl_source}",
            f"--prefix={local_prefix}",
            "--target=i386-linux-gnu",
            f"--jobs={os.cpu_count() or 4}",
        ]

        # Attempt sysroot + cross installs; skip gracefully if not writable
        if self._is_writable_or_creatable("/opt/blueyos-sysroot"):
            build_args += ["--sysroot=/opt/blueyos-sysroot"]
        else:
            self.log.info(
                "  /opt/blueyos-sysroot not writable; skipping sysroot install "
                "(use sudo or set musl_prefix in baker.yaml)."
            )
            build_args.append("--skip-sysroot")

        if self._is_writable_or_creatable("/opt/blueyos-cross/musl"):
            pass  # default: install
        else:
            self.log.info(
                "  /opt/blueyos-cross/musl not writable; skipping cross install."
            )
            build_args.append("--skip-cross")

        self._run_script_args(build_args, cwd=src)

        self.log.info("Toolchain stage complete.")
        self.log.info(
            "musl-blueyos is now available at %s", cfg.abs_musl_prefix
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _run_script(self, script_path: str, cwd: str) -> None:
        self._run_script_args(["bash", script_path], cwd=cwd)

    def _run_script_args(self, cmd: list, cwd: str) -> None:
        if shutil.which("bash") is None:
            self.log.warning("bash not found; skipping: %s", " ".join(cmd))
            return
        self.log.debug("Running: %s (cwd=%s)", " ".join(cmd), cwd)
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
        if result.stdout:
            self.log.debug(result.stdout.rstrip())
        if result.stderr:
            self.log.debug(result.stderr.rstrip())
        if result.returncode != 0:
            raise RuntimeError(
                f"Script failed (exit {result.returncode}):\n{result.stderr[-2000:]}"
            )

    @staticmethod
    def _is_writable_or_creatable(path: str) -> bool:
        """Return True if *path* exists and is writable, or its parent is writable."""
        if os.path.exists(path):
            return os.access(path, os.W_OK)
        parent = os.path.dirname(path)
        return os.path.isdir(parent) and os.access(parent, os.W_OK)
