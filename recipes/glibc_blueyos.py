"""
recipes/glibc_blueyos.py - Recipe for the glibc-blueyos bootstrap workspace.

This recipe builds the stage-1 BlueyOS glibc toolchain/runtime, installs the
runtime bits into the target sysroot, and packages the runtime/devel dimsim
artifacts exposed by the upstream repo.
"""

from __future__ import annotations

import glob
import os
import shutil

from helpers.host_tools import build_host_env
from recipes.base import BaseRecipe, RecipeError


class GlibcBlueyosRecipe(BaseRecipe):
    """Build and package the BlueyOS glibc bootstrap workspace."""

    name = "glibc-blueyos"
    version = "2.43.0"
    dependencies = ["musl-blueyos"]
    install_paths = [
        "lib/ld-blueyos.so.1",
        "lib/libc.so",
        "lib/libc.so.6",
        "lib/libm.so",
        "lib/libm.so.6",
        "lib/libpthread.so",
        "lib/libpthread.so.0",
    ]

    def __init__(self, config):
        super().__init__(config)
        self._source_dir = os.path.join(config.abs_sources_dir, "glibc-blueyos")
        self._build_dir = os.path.join(config.abs_build_dir, "glibc-blueyos")
        self._gcc_prefix = os.path.join(self._build_dir, "toolchains", "i686-pc-blueyos")
        self._sysroot = os.path.join(self._build_dir, "sysroots", "i686-pc-blueyos")

    def build(self) -> None:
        src = self._source_dir
        if not os.path.isdir(src):
            raise RecipeError(
                f"{self.name} source not found at {src}. Run 'baker prepare' first."
            )

        headers_dir = self._bootstrap_headers_dir()
        env = build_host_env(
            {
                "GCC_PREFIX": self._gcc_prefix,
                "SYSROOT": self._sysroot,
                "BOOTSTRAP_HEADERS_DIR": headers_dir,
                **self._host_compiler_env(),
            }
        )
        for target in (
            "fetch",
            "build-gcc-target",
            "build-glibc-target",
            "sync-glibc-install",
            "sync-gcc-sysroot",
        ):
            self.run(["make", target], cwd=src, env=env)

    def install(self) -> None:
        runtime_root = self._runtime_root()
        lib_dir = os.path.join(runtime_root, "lib")
        if not os.path.isdir(lib_dir):
            raise RecipeError(f"glibc runtime directory not found: {lib_dir}")

        self.sysroot.install_tree(lib_dir, "lib")
        include_dir = os.path.join(runtime_root, "include")
        if os.path.isdir(include_dir):
            self.sysroot.install_tree(include_dir, os.path.join("usr", "glibc-blueyos", "include"))
        self.log.info("Installed glibc-blueyos runtime into %s", self.config.abs_sysroot)

    def package(self) -> str | None:
        src = self._source_dir
        env = build_host_env(
            {
                "GCC_PREFIX": self._gcc_prefix,
                "SYSROOT": self._sysroot,
                "BOOTSTRAP_HEADERS_DIR": self._bootstrap_headers_dir(),
                **self._host_compiler_env(),
            }
        )
        self.run(["make", "dpk"], cwd=src, env=env)

        dpk_files = glob.glob(os.path.join(src, "dist", "*.dpk"))
        if not dpk_files:
            raise RecipeError(f"No .dpk files produced for {self.name} in {src}/dist")

        copied = []
        for dpk_file in sorted(dpk_files):
            dest = os.path.join(self.config.abs_output_dir, os.path.basename(dpk_file))
            shutil.copy2(dpk_file, dest)
            copied.append(dest)
        self.log.info("Packages: %s", ", ".join(copied))
        return copied[0]

    def _bootstrap_headers_dir(self) -> str:
        for candidate in (
            os.path.join(self.config.abs_musl_prefix, "include"),
            os.path.join(self.config.abs_musl_prefix, "usr", "include"),
        ):
            if os.path.isdir(candidate):
                return candidate
        raise RecipeError(
            f"musl bootstrap headers not found under {self.config.abs_musl_prefix}; run 'baker toolchain' first."
        )

    def _runtime_root(self) -> str:
        candidates = [
            self.config.abs_glibc_prefix,
            os.path.join(self._source_dir, "build", "glibc-root", "i686-pc-blueyos"),
        ]
        for candidate in candidates:
            if os.path.isdir(candidate):
                return candidate
        raise RecipeError("glibc install root not found after build")

    def _host_compiler_env(self) -> dict[str, str]:
        env: dict[str, str] = {}

        cc = shutil.which("gcc") or shutil.which("cc")
        if cc:
            env["CC"] = cc
            env["CPP"] = f"{cc} -E"

        cxx = shutil.which("g++") or shutil.which("c++")
        if cxx:
            env["CXX"] = cxx
            env["CXXCPP"] = f"{cxx} -E"

        return env
