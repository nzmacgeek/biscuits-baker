"""
helpers/packaging.py - Package creation helpers for Baker.

Produces discrete tar.gz artifacts per component, ready for distribution
or installation into a target system.
"""

from __future__ import annotations

import json
import logging
import os
import tarfile
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PackageBuilder:
    """Assembles a component's installed files into a distributable package."""

    def __init__(self, output_dir: str) -> None:
        self.output_dir = os.path.abspath(output_dir)
        os.makedirs(self.output_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_package(
        self,
        name: str,
        version: str,
        sysroot: str,
        include_paths: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        compression: str = "gz",
    ) -> str:
        """Create a package archive from files inside *sysroot*.

        Args:
            name: Component name (e.g. ``"busybox"``).
            version: Version string (e.g. ``"1.36.1"``).
            sysroot: Absolute path to the sysroot to package from.
            include_paths: List of sysroot-relative paths to include.
                           If *None*, the entire sysroot is packaged.
            metadata: Extra key/value pairs added to the package manifest.
            compression: Compression method: ``"gz"`` (default), ``"bz2"``, ``"xz"``.

        Returns:
            Absolute path to the produced package file.
        """
        pkg_name = f"{name}-{version}.tar.{compression}"
        pkg_path = os.path.join(self.output_dir, pkg_name)

        logger.info("Building package: %s", pkg_name)

        manifest: Dict[str, Any] = {
            "name": name,
            "version": version,
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            **(metadata or {}),
        }
        manifest_json = json.dumps(manifest, indent=2).encode()

        with tarfile.open(pkg_path, f"w:{compression}") as tar:
            # Add manifest
            self._add_bytes(tar, manifest_json, f"{name}-{version}/MANIFEST.json")

            # Add files from sysroot
            if include_paths:
                for rel in include_paths:
                    src = os.path.join(sysroot, rel.lstrip(os.sep))
                    if os.path.exists(src):
                        arcname = os.path.join(f"{name}-{version}", rel.lstrip(os.sep))
                        tar.add(src, arcname=arcname, recursive=True)
                    else:
                        logger.warning("Packaging: path not found in sysroot: %s", rel)
            else:
                # Package entire sysroot
                for root, _dirs, files in os.walk(sysroot):
                    for fname in files:
                        abs_file = os.path.join(root, fname)
                        rel_file = os.path.relpath(abs_file, sysroot)
                        arcname = os.path.join(f"{name}-{version}", rel_file)
                        tar.add(abs_file, arcname=arcname)

        logger.info("Package written: %s (%.1f KB)", pkg_path, os.path.getsize(pkg_path) / 1024)
        return pkg_path

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_packages(self) -> List[str]:
        """Return the names of all packages in the output directory."""
        result = []
        for fname in sorted(os.listdir(self.output_dir)):
            if fname.endswith((".tar.gz", ".tar.bz2", ".tar.xz")):
                result.append(fname)
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _add_bytes(tar: tarfile.TarFile, data: bytes, arcname: str) -> None:
        """Add raw *data* bytes to *tar* under *arcname*."""
        import io

        info = tarfile.TarInfo(name=arcname)
        info.size = len(data)
        info.mtime = int(time.time())
        tar.addfile(info, io.BytesIO(data))
