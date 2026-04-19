"""
stages/toolchain.py - Toolchain and musl-blueyos build stage for Baker.

This stage:
1. Runs ``tools/make-libc-toolchain.sh`` from the biscuits repo to build the
   i686-elf cross-compiler and install it to ``toolchain_prefix``
   (default: /opt/blueyos-cross).
2. Runs ``tools/build-musl.sh`` from the biscuits repo to build/install
   musl-blueyos to:
   - ``build/musl``          — repo-local prefix (always writeable)
   - ``musl_prefix``         — authoritative musl install (from config)
   - ``toolchain_prefix/musl`` — alongside the cross toolchain

Install destinations for the sysroot and cross-musl are derived from
``cfg.toolchain_prefix`` and ``cfg.abs_musl_prefix``; no paths are
hard-coded.  Destinations that are not writeable are silently skipped.

Both scripts are idempotent: re-running the stage after a successful build
is fast because they skip already-installed artefacts.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import tempfile

from helpers.host_tools import build_host_env
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
            gcc_bin = os.path.join(cfg.abs_toolchain_prefix, "bin", "i686-elf-gcc")
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
                os.makedirs(cfg.abs_toolchain_prefix, exist_ok=True)
                generated = self._write_toolchain_script(cfg.abs_toolchain_prefix)
                self._run_script(generated, cwd=src)
            self._ensure_blueyos_target_aliases(cfg.abs_toolchain_prefix)
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

        # Authoritative musl destination comes from config.  When it equals the
        # local build prefix (the default fallback) we also try to install to
        # the cross-toolchain sysroot path alongside the toolchain.
        musl_sysroot_dest = cfg.abs_musl_prefix
        cross_musl_dest = os.path.join(cfg.abs_toolchain_prefix, "musl")

        self.log.info("Building musl-blueyos via %s", musl_script)
        self.log.info("  local prefix  : %s", local_prefix)
        self.log.info("  sysroot dest  : %s", musl_sysroot_dest)
        self.log.info("  cross prefix  : %s", cross_musl_dest)

        # Build args: always install to local prefix; conditionally to sysroot and cross
        build_args = [
            "bash",
            musl_script,
            f"--source={musl_source}",
            f"--prefix={local_prefix}",
            "--target=i386-linux-gnu",
            f"--jobs={os.cpu_count() or 4}",
        ]

        # Attempt sysroot + cross installs; skip gracefully if not writable
        if self._is_writable_or_creatable(musl_sysroot_dest):
            build_args += [f"--sysroot={musl_sysroot_dest}"]
        else:
            self.log.info(
                "  %s not writable; skipping sysroot install "
                "(use sudo or set musl_prefix in baker.yaml).",
                musl_sysroot_dest,
            )
            build_args.append("--skip-sysroot")

        if self._is_writable_or_creatable(cross_musl_dest):
            build_args += [f"--cross-prefix={cross_musl_dest}"]
        else:
            self.log.info(
                "  %s not writable; skipping cross install.",
                cross_musl_dest,
            )
            build_args.append("--skip-cross")

        self._run_script_args(build_args, cwd=src)
        self._repair_musl_wrapper(local_prefix)
        if os.path.isdir(musl_sysroot_dest):
            self._repair_musl_wrapper(musl_sysroot_dest)
        if os.path.isdir(cross_musl_dest):
            self._repair_musl_wrapper(cross_musl_dest)

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
                f"Script failed (exit {result.returncode}):\n{result.stderr[-2000:]}"
            )

    @staticmethod
    def _is_writable_or_creatable(path: str) -> bool:
        """Return True if *path* exists and is writable, or its parent is writable."""
        if os.path.exists(path):
            return os.access(path, os.W_OK)
        parent = os.path.dirname(path)
        return os.path.isdir(parent) and os.access(parent, os.W_OK)

    def _write_toolchain_script(self, toolchain_prefix: str) -> str:
        fd, path = tempfile.mkstemp(
            prefix="baker-toolchain-",
            suffix=".sh",
            dir=self.config.abs_build_dir,
            text=True,
        )
        script = f"""#!/usr/bin/env bash
set -euo pipefail

PREFIX={toolchain_prefix!r}
BINUTILS_VERSION=2.41
GCC_VERSION=13.2.0

download() {{
  local url="$1"
  local out="$2"
  if command -v curl >/dev/null 2>&1; then
    curl --fail --location --output "$out" "$url"
  elif command -v wget >/dev/null 2>&1; then
    wget -O "$out" "$url"
  elif command -v python3 >/dev/null 2>&1; then
    python3 - "$url" "$out" <<'PY'
import sys
from urllib.request import urlopen

url, out = sys.argv[1], sys.argv[2]
with urlopen(url) as response, open(out, "wb") as fh:
    while True:
        chunk = response.read(1024 * 1024)
        if not chunk:
            break
        fh.write(chunk)
PY
  else
    echo "curl, wget, or python3 is required to download toolchain sources" >&2
    exit 1
  fi
}}

[ -f "binutils-${{BINUTILS_VERSION}}.tar.xz" ] || download "https://ftp.gnu.org/gnu/binutils/binutils-${{BINUTILS_VERSION}}.tar.xz" "binutils-${{BINUTILS_VERSION}}.tar.xz"
[ -f "gcc-${{GCC_VERSION}}.tar.xz" ] || download "https://ftp.gnu.org/gnu/gcc/gcc-${{GCC_VERSION}}/gcc-${{GCC_VERSION}}.tar.xz" "gcc-${{GCC_VERSION}}.tar.xz"
[ -d "binutils-${{BINUTILS_VERSION}}" ] || tar xf "binutils-${{BINUTILS_VERSION}}.tar.xz"
[ -d "gcc-${{GCC_VERSION}}" ] || tar xf "gcc-${{GCC_VERSION}}.tar.xz"

( cd "gcc-${{GCC_VERSION}}" && ./contrib/download_prerequisites )

rm -rf build-binutils
mkdir build-binutils
cd build-binutils
../binutils-${{BINUTILS_VERSION}}/configure --target=i686-elf \\
    --prefix="$PREFIX" --with-sysroot --disable-nls --disable-werror
make MAKEINFO=true -j"$(nproc)"
make MAKEINFO=true install
cd ..

rm -rf build-gcc
mkdir build-gcc
cd build-gcc
../gcc-${{GCC_VERSION}}/configure --target=i686-elf \\
    --prefix="$PREFIX" --disable-nls --enable-languages=c \\
    --without-headers
make MAKEINFO=true -j"$(nproc)" all-gcc all-target-libgcc
make MAKEINFO=true install-gcc install-target-libgcc
"""
        with os.fdopen(fd, "w") as fh:
            fh.write(script)
        os.chmod(path, 0o755)
        return path

    def _ensure_blueyos_target_aliases(self, toolchain_prefix: str) -> None:
        """Expose i386-blueyos-elf tool names for repos that expect that triplet."""
        bin_dir = os.path.join(toolchain_prefix, "bin")
        if not os.path.isdir(bin_dir):
            return

        aliases = {
            "i386-blueyos-elf-addr2line": "i686-elf-addr2line",
            "i386-blueyos-elf-ar": "i686-elf-ar",
            "i386-blueyos-elf-as": "i686-elf-as",
            "i386-blueyos-elf-cpp": "i686-elf-cpp",
            "i386-blueyos-elf-gcc": "i686-elf-gcc",
            "i386-blueyos-elf-gcc-ar": "i686-elf-gcc-ar",
            "i386-blueyos-elf-gcc-nm": "i686-elf-gcc-nm",
            "i386-blueyos-elf-gcc-ranlib": "i686-elf-gcc-ranlib",
            "i386-blueyos-elf-gcov": "i686-elf-gcov",
            "i386-blueyos-elf-gcov-dump": "i686-elf-gcov-dump",
            "i386-blueyos-elf-gcov-tool": "i686-elf-gcov-tool",
            "i386-blueyos-elf-gprof": "i686-elf-gprof",
            "i386-blueyos-elf-ld": "i686-elf-ld",
            "i386-blueyos-elf-nm": "i686-elf-nm",
            "i386-blueyos-elf-objcopy": "i686-elf-objcopy",
            "i386-blueyos-elf-objdump": "i686-elf-objdump",
            "i386-blueyos-elf-ranlib": "i686-elf-ranlib",
            "i386-blueyos-elf-readelf": "i686-elf-readelf",
            "i386-blueyos-elf-size": "i686-elf-size",
            "i386-blueyos-elf-strings": "i686-elf-strings",
            "i386-blueyos-elf-strip": "i686-elf-strip",
        }

        for alias, target in aliases.items():
            target_path = os.path.join(bin_dir, target)
            if not os.path.isfile(target_path):
                continue

            alias_path = os.path.join(bin_dir, alias)
            script = (
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                f'exec "{target_path}" "$@"\n'
            )
            with open(alias_path, "w", encoding="utf-8") as fh:
                fh.write(script)
            os.chmod(alias_path, 0o755)

        source_gcc_root = os.path.join(toolchain_prefix, "lib", "gcc", "i686-elf")
        compat_gcc_root = os.path.join(toolchain_prefix, "lib", "gcc", "i386-blueyos-elf")
        if os.path.isdir(source_gcc_root):
            os.makedirs(os.path.dirname(compat_gcc_root), exist_ok=True)
            if os.path.lexists(compat_gcc_root):
                if os.path.islink(compat_gcc_root) or os.path.isfile(compat_gcc_root):
                    os.unlink(compat_gcc_root)
            if not os.path.lexists(compat_gcc_root):
                os.symlink(source_gcc_root, compat_gcc_root)

    def _repair_musl_wrapper(self, prefix: str) -> None:
        wrapper_path = os.path.join(prefix, "bin", "musl-gcc")
        specs_path = os.path.join(prefix, "lib", "musl-gcc.specs")
        if not (os.path.isfile(wrapper_path) and os.path.isfile(specs_path)):
            return

        compiler_cmd: list[str] | None = None
        distro_cross = shutil.which("i686-linux-gnu-gcc")
        if distro_cross:
            compiler_cmd = [distro_cross, "-m32"]
        else:
            host_gcc = shutil.which("gcc")
            if host_gcc:
                compiler_cmd = [host_gcc, "-m32"]

        if not compiler_cmd:
            return

        parts = " ".join(shlex.quote(part) for part in compiler_cmd)
        script = (
            "#!/bin/sh\n"
            "case \"$1\" in\n"
            "  -print-file-name=*)\n"
            "    requested=${1#-print-file-name=}\n"
            f"    if [ -f {shlex.quote(os.path.join(prefix, 'lib'))}/\"$requested\" ]; then\n"
            f"      printf '%s\\n' {shlex.quote(os.path.join(prefix, 'lib'))}/\"$requested\"\n"
            "      exit 0\n"
            "    fi\n"
            "    ;;\n"
            "esac\n"
            f'exec {parts} -specs {shlex.quote(specs_path)} "$@"\n'
        )
        with open(wrapper_path, "w", encoding="utf-8") as fh:
            fh.write(script)
        os.chmod(wrapper_path, 0o755)
