"""
helpers/sysroot.py - Sysroot installation helpers for Baker.

Provides utilities for populating the sysroot directory with built
binaries, libraries, headers, and configuration files.
"""

from __future__ import annotations

import logging
import os
import shutil
from typing import List, Optional

logger = logging.getLogger(__name__)


class SysrootInstaller:
    """Manages file installation into a sysroot directory."""

    def __init__(self, sysroot: str) -> None:
        self.sysroot = os.path.abspath(sysroot)

    # ------------------------------------------------------------------
    # Directory helpers
    # ------------------------------------------------------------------

    def ensure_dir(self, *rel_path_parts: str) -> str:
        """Create *rel_path_parts* inside the sysroot if it doesn't exist.

        Returns the absolute path.
        """
        path = os.path.join(self.sysroot, *rel_path_parts)
        os.makedirs(path, exist_ok=True)
        logger.debug("ensured dir: %s", path)
        return path

    def makedirs(self, *rel_paths: str) -> None:
        """Create multiple directories inside the sysroot."""
        for rel in rel_paths:
            self.ensure_dir(rel)

    # ------------------------------------------------------------------
    # File installation
    # ------------------------------------------------------------------

    def install_file(
        self,
        src: str,
        dest_rel: str,
        mode: Optional[int] = None,
        owner_uid: int = 0,
        owner_gid: int = 0,
    ) -> str:
        """Copy *src* to *dest_rel* (relative to sysroot).

        Args:
            src: Absolute or relative source file path.
            dest_rel: Destination path relative to sysroot.
            mode: File permission bits (e.g. 0o755).  Preserved from source if None.
            owner_uid: UID to assign (only effective when running as root).
            owner_gid: GID to assign (only effective when running as root).

        Returns:
            Absolute destination path.
        """
        dest = os.path.join(self.sysroot, dest_rel.lstrip(os.sep))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(src, dest)
        if mode is not None:
            os.chmod(dest, mode)
        try:
            os.lchown(dest, owner_uid, owner_gid)
        except (AttributeError, PermissionError):
            pass  # Not root or platform doesn't support chown
        logger.debug("installed %s → %s", src, dest)
        return dest

    def install_tree(self, src_dir: str, dest_rel: str, symlinks: bool = True) -> str:
        """Recursively copy *src_dir* into *dest_rel* inside the sysroot.

        If *dest_rel* is ``'.'``, ``''``, or otherwise resolves to the sysroot
        root, the *contents* of *src_dir* are merged into the sysroot rather
        than replacing it entirely.  This prevents accidentally deleting the
        whole sysroot when installing a payload whose top-level directory maps
        to ``/``.

        Returns:
            Absolute destination path.
        """
        dest = os.path.normpath(os.path.join(self.sysroot, dest_rel.lstrip(os.sep)))

        # Guard: if dest resolves to the sysroot root itself, merge contents
        # instead of rmtree + copytree (which would wipe the sysroot).
        if os.path.normpath(dest) == os.path.normpath(self.sysroot):
            for item in os.listdir(src_dir):
                s = os.path.join(src_dir, item)
                d = os.path.join(self.sysroot, item)
                if os.path.isdir(s) and not os.path.islink(s):
                    if os.path.isdir(d):
                        shutil.rmtree(d)
                    elif os.path.exists(d):
                        os.remove(d)
                    shutil.copytree(s, d, symlinks=symlinks)
                else:
                    shutil.copy2(s, d)
            logger.debug("merged tree %s → %s (sysroot root)", src_dir, self.sysroot)
            return self.sysroot

        if os.path.exists(dest):
            shutil.rmtree(dest)
        shutil.copytree(src_dir, dest, symlinks=symlinks)
        logger.debug("installed tree %s → %s", src_dir, dest)
        return dest

    def install_binary(self, src: str, dest_rel: Optional[str] = None) -> str:
        """Install an executable binary into bin/ (or *dest_rel*) with mode 0o755."""
        if dest_rel is None:
            dest_rel = os.path.join("usr", "bin", os.path.basename(src))
        return self.install_file(src, dest_rel, mode=0o755)

    def install_library(self, src: str, dest_rel: Optional[str] = None) -> str:
        """Install a shared library into lib/ (or *dest_rel*) with mode 0o644."""
        if dest_rel is None:
            dest_rel = os.path.join("usr", "lib", os.path.basename(src))
        return self.install_file(src, dest_rel, mode=0o644)

    def install_header(self, src: str, dest_rel: Optional[str] = None) -> str:
        """Install a header file into usr/include/ (or *dest_rel*)."""
        if dest_rel is None:
            dest_rel = os.path.join("usr", "include", os.path.basename(src))
        return self.install_file(src, dest_rel, mode=0o644)

    # ------------------------------------------------------------------
    # Symlinks
    # ------------------------------------------------------------------

    def symlink(self, target: str, link_rel: str) -> str:
        """Create a symbolic link at *link_rel* (inside sysroot) pointing to *target*.

        Returns:
            Absolute link path.
        """
        link_abs = os.path.join(self.sysroot, link_rel.lstrip(os.sep))
        os.makedirs(os.path.dirname(link_abs), exist_ok=True)
        if os.path.lexists(link_abs):
            os.remove(link_abs)
        os.symlink(target, link_abs)
        logger.debug("symlink %s → %s", link_abs, target)
        return link_abs

    # ------------------------------------------------------------------
    # Filesystem layout
    # ------------------------------------------------------------------

    def create_standard_layout(self) -> None:
        """Create the standard FHS-like directory layout inside the sysroot."""
        standard_dirs = [
            "bin",
            "sbin",
            "lib",
            "lib64",
            "usr/bin",
            "usr/sbin",
            "usr/lib",
            "usr/lib64",
            "usr/include",
            "usr/share",
            "usr/share/man",
            "etc",
            "var",
            "var/log",
            "var/run",
            "proc",
            "sys",
            "dev",
            "tmp",
            "home",
            "root",
            "boot",
        ]
        for d in standard_dirs:
            self.ensure_dir(d)
        logger.info("Standard sysroot layout created at %s", self.sysroot)

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def abs_path(self, *rel_parts: str) -> str:
        """Return the absolute path of a sysroot-relative path."""
        return os.path.join(self.sysroot, *rel_parts)

    def exists(self, rel_path: str) -> bool:
        """Return True if *rel_path* exists inside the sysroot."""
        return os.path.exists(self.abs_path(rel_path))

    def list_installed_files(self) -> List[str]:
        """Walk the sysroot and return all file paths (relative to sysroot)."""
        result: List[str] = []
        for root, _dirs, files in os.walk(self.sysroot):
            for fname in files:
                abs_file = os.path.join(root, fname)
                result.append(os.path.relpath(abs_file, self.sysroot))
        return sorted(result)
