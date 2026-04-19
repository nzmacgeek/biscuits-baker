"""
helpers/sysroot.py - Sysroot installation helpers for Baker.

Provides utilities for populating the sysroot directory with built
binaries, libraries, headers, and configuration files.
"""

from __future__ import annotations

import errno
import logging
import os
import shutil
import subprocess
from typing import List, Optional

logger = logging.getLogger(__name__)


class SysrootInstaller:
    """Manages file installation into a sysroot directory."""

    def __init__(self, sysroot: str) -> None:
        self.sysroot = os.path.abspath(sysroot)

    # ------------------------------------------------------------------
    # Sudo escalation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _run_sudo(cmd: List[str]) -> None:
        """Run *cmd* prefixed with sudo, raising PermissionError on failure."""
        full_cmd = ["sudo"] + cmd
        result = subprocess.run(full_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise PermissionError(
                f"sudo command failed (exit {result.returncode}): {' '.join(full_cmd)}\n"
                f"{result.stderr.strip()}"
            )

    def _fs_makedirs(self, path: str) -> None:
        try:
            os.makedirs(path, exist_ok=True)
        except PermissionError as e:
            if e.errno != errno.EACCES:
                raise
            logger.debug("makedirs %s: permission denied, retrying with sudo", path)
            self._run_sudo(["mkdir", "-p", path])

    def _fs_copy_file(self, src: str, dest: str) -> None:
        try:
            shutil.copy2(src, dest)
        except PermissionError as e:
            if e.errno != errno.EACCES:
                raise
            logger.debug("copy %s → %s: permission denied, retrying with sudo", src, dest)
            self._run_sudo(["cp", "-p", src, dest])

    def _fs_copy_tree(self, src: str, dest: str) -> None:
        """Copy *src* tree to *dest* (dest must not already exist)."""
        try:
            shutil.copytree(src, dest, symlinks=True)
        except PermissionError as e:
            if e.errno != errno.EACCES:
                raise
            logger.debug("copytree %s → %s: permission denied, retrying with sudo", src, dest)
            self._run_sudo(["cp", "-a", src, dest])

    def _fs_remove(self, path: str) -> None:
        try:
            if os.path.isdir(path) and not os.path.islink(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
        except PermissionError as e:
            if e.errno != errno.EACCES:
                raise
            logger.debug("remove %s: permission denied, retrying with sudo", path)
            self._run_sudo(["rm", "-rf", path])

    def _fs_chmod(self, path: str, mode: int) -> None:
        try:
            os.chmod(path, mode)
        except PermissionError as e:
            if e.errno != errno.EACCES:
                raise
            logger.debug("chmod %s: permission denied, retrying with sudo", path)
            self._run_sudo(["chmod", f"{mode:o}", path])

    def _fs_chown(self, path: str, uid: int, gid: int) -> None:
        try:
            os.lchown(path, uid, gid)
        except PermissionError as e:
            if e.errno == errno.EACCES:
                logger.debug("chown %s: permission denied, retrying with sudo", path)
                self._run_sudo(["chown", "-h", f"{uid}:{gid}", path])
            # EPERM means caller lacks privilege to assign this uid/gid (e.g. non-root
            # trying to chown to uid 0) — silently skip rather than escalate.
        except AttributeError:
            pass  # Platform doesn't support chown

    def _fs_symlink(self, target: str, link_path: str) -> None:
        try:
            os.symlink(target, link_path)
        except PermissionError as e:
            if e.errno != errno.EACCES:
                raise
            logger.debug("symlink %s → %s: permission denied, retrying with sudo", link_path, target)
            self._run_sudo(["ln", "-sf", target, link_path])

    # ------------------------------------------------------------------
    # Directory helpers
    # ------------------------------------------------------------------

    def ensure_dir(self, *rel_path_parts: str) -> str:
        """Create *rel_path_parts* inside the sysroot if it doesn't exist.

        Returns the absolute path.
        """
        path = os.path.join(self.sysroot, *rel_path_parts)
        self._fs_makedirs(path)
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
            owner_uid: UID to assign (only effective when running as root or with sudo).
            owner_gid: GID to assign (only effective when running as root or with sudo).

        Returns:
            Absolute destination path.
        """
        dest = os.path.join(self.sysroot, dest_rel.lstrip(os.sep))
        self._fs_makedirs(os.path.dirname(dest))
        self._fs_copy_file(src, dest)
        if mode is not None:
            self._fs_chmod(dest, mode)
        self._fs_chown(dest, owner_uid, owner_gid)
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
                self._merge_path(s, d, symlinks=symlinks)
            logger.debug("merged tree %s → %s (sysroot root)", src_dir, self.sysroot)
            return self.sysroot

        if os.path.exists(dest):
            self._fs_remove(dest)
        self._fs_copy_tree(src_dir, dest)
        logger.debug("installed tree %s → %s", src_dir, dest)
        return dest

    def _merge_path(self, src: str, dest: str, symlinks: bool = True) -> None:
        """Merge *src* into *dest* without deleting unrelated existing contents."""
        if os.path.islink(src) and symlinks:
            if os.path.lexists(dest):
                self._remove_existing(dest)
            self._fs_makedirs(os.path.dirname(dest))
            self._fs_symlink(os.readlink(src), dest)
            return

        if os.path.isdir(src):
            if os.path.lexists(dest) and not os.path.isdir(dest):
                self._remove_existing(dest)
            self._fs_makedirs(dest)
            for item in os.listdir(src):
                self._merge_path(
                    os.path.join(src, item),
                    os.path.join(dest, item),
                    symlinks=symlinks,
                )
            return

        if os.path.isdir(dest) and not os.path.islink(dest):
            self._fs_remove(dest)
        elif os.path.lexists(dest):
            self._fs_remove(dest)
        self._fs_makedirs(os.path.dirname(dest))
        self._fs_copy_file(src, dest)

    def _remove_existing(self, path: str) -> None:
        self._fs_remove(path)

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
        self._fs_makedirs(os.path.dirname(link_abs))
        if os.path.lexists(link_abs):
            self._fs_remove(link_abs)
        self._fs_symlink(target, link_abs)
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
