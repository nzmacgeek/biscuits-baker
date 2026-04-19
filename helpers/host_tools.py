"""
helpers/host_tools.py - Host-tool discovery helpers for confined environments.

Baker often runs inside a snap where the host's build tools live under
``/var/lib/snapd/hostfs`` instead of the active PATH.  These helpers make it
easy to consistently run subprocesses with access to that toolchain.
"""

from __future__ import annotations

import os
from typing import Dict, Optional

HOSTFS_ROOT = "/var/lib/snapd/hostfs"
HOSTFS_PATHFIX_DIR = "/tmp/hostfs-bin-pathfix"


def hostfs_exists() -> bool:
    return os.path.isdir(HOSTFS_ROOT)


def host_git_exec_path() -> str | None:
    candidates = [
        os.path.join(HOSTFS_ROOT, "usr", "lib", "git-core"),
        os.path.join(HOSTFS_ROOT, "usr", "libexec", "git-core"),
    ]
    for candidate in candidates:
        if os.path.isdir(candidate):
            return candidate
    return None


def host_path_entries() -> list[str]:
    entries: list[str] = []
    if os.path.isdir(HOSTFS_PATHFIX_DIR):
        entries.append(HOSTFS_PATHFIX_DIR)
    for candidate in (
        os.path.join(HOSTFS_ROOT, "usr", "bin"),
        os.path.join(HOSTFS_ROOT, "usr", "sbin"),
        os.path.join(HOSTFS_ROOT, "bin"),
        os.path.join(HOSTFS_ROOT, "sbin"),
    ):
        if os.path.isdir(candidate):
            entries.append(candidate)
    return entries


def _write_wrapper(path: str, target: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("#!/usr/bin/env bash\n")
        fh.write("set -e\n")
        fh.write(f"exec {target} \"$@\"\n")
    os.chmod(path, 0o755)


def ensure_host_pathfix() -> None:
    if not hostfs_exists():
        return

    os.makedirs(HOSTFS_PATHFIX_DIR, exist_ok=True)
    targets = {
        "file": os.path.join(HOSTFS_ROOT, "usr", "bin", "file"),
        "makeinfo": os.path.join(HOSTFS_ROOT, "usr", "bin", "texi2any"),
        "texi2any": os.path.join(HOSTFS_ROOT, "usr", "bin", "texi2any"),
    }
    for name, target in targets.items():
        if os.path.isfile(target):
            _write_wrapper(os.path.join(HOSTFS_PATHFIX_DIR, name), target)


def build_host_env(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    env = dict(os.environ)
    ensure_host_pathfix()

    path_entries = host_path_entries()
    if path_entries:
        existing = env.get("PATH", "")
        env["PATH"] = os.pathsep.join(path_entries + ([existing] if existing else []))

    git_exec_path = host_git_exec_path()
    if git_exec_path:
        env.setdefault("GIT_EXEC_PATH", git_exec_path)

    if hostfs_exists():
        env.setdefault("HOST_SYSROOT", HOSTFS_ROOT)
        host_libs = [
            os.path.join(HOSTFS_ROOT, "usr", "lib", "x86_64-linux-gnu"),
            os.path.join(HOSTFS_ROOT, "lib", "x86_64-linux-gnu"),
            os.path.join(HOSTFS_ROOT, "usr", "lib"),
            os.path.join(HOSTFS_ROOT, "lib"),
        ]
        resolved_libs = [path for path in host_libs if os.path.isdir(path)]
        if resolved_libs:
            existing_ld = env.get("LD_LIBRARY_PATH", "")
            env["LD_LIBRARY_PATH"] = os.pathsep.join(
                resolved_libs + ([existing_ld] if existing_ld else [])
            )
        bison_pkgdatadir = os.path.join(HOSTFS_ROOT, "usr", "share", "bison")
        if os.path.isdir(bison_pkgdatadir):
            env.setdefault("BISON_PKGDATADIR", bison_pkgdatadir)
        host_m4 = os.path.join(HOSTFS_ROOT, "usr", "bin", "m4")
        if os.path.isfile(host_m4):
            env.setdefault("M4", host_m4)

    if extra:
        env.update(extra)

    return env
