"""
recipes/base.py - Base recipe class for Baker.

Every component in the build system is defined by a Recipe subclass.
Recipes encapsulate the fetch, configure, build, install, and package
steps for a single software component.
"""

from __future__ import annotations

import abc
import logging
import os
import shutil
import subprocess
import tarfile
from typing import Any, Dict, List, Optional

from config import Config
from helpers.host_tools import build_host_env
from helpers.sysroot import SysrootInstaller

logger = logging.getLogger(__name__)


class RecipeError(Exception):
    """Raised when a recipe step fails."""


def safe_extract(tarball_path: str, dest_dir: str) -> None:
    """Extract *tarball_path* into *dest_dir*, guarding against path traversal.

    Raises:
        RecipeError: if any archive member would extract outside *dest_dir*.
    """
    dest_dir = os.path.realpath(dest_dir)
    with tarfile.open(tarball_path) as tf:
        for member in tf.getmembers():
            # Resolve the member path relative to dest_dir
            member_path = os.path.realpath(os.path.join(dest_dir, member.name))
            if not (member_path == dest_dir or member_path.startswith(dest_dir + os.sep)):
                raise RecipeError(
                    f"Refusing to extract {member.name!r}: path traversal detected "
                    f"(would write outside {dest_dir!r})"
                )
        tf.extractall(dest_dir)  # noqa: S202 — members validated above


class BaseRecipe(abc.ABC):
    """Abstract base class for all Baker recipes.

    Subclasses must define at minimum:
        * :attr:`name`
        * :attr:`version`
        * :meth:`build`

    And should override :meth:`install` to place files into the sysroot.
    """

    #: Unique component name (must match key used in dependency graph)
    name: str = ""
    #: Component version string
    version: str = "0.0.0"
    #: List of component names that must be built before this one
    dependencies: List[str] = []
    #: Sysroot-relative paths that this component contributes (for packaging)
    install_paths: List[str] = []

    def __init__(self, config: Config) -> None:
        if not self.name:
            raise ValueError(f"{self.__class__.__name__} must define 'name'")
        self.config = config
        self.log = logging.getLogger(f"baker.recipe.{self.name}")
        self.sysroot = SysrootInstaller(config.abs_sysroot)
        self._source_dir = os.path.join(config.abs_sources_dir, self.name)
        self._build_dir = os.path.join(config.abs_build_dir, self.name)

    # ------------------------------------------------------------------
    # Template methods (override as needed)
    # ------------------------------------------------------------------

    def fetch(self) -> None:
        """Fetch/update the source code for this component.

        Default implementation is a no-op.  Override to clone/download.
        """

    def configure(self) -> None:
        """Configure the component for building.

        Default implementation is a no-op.  Override to run ./configure,
        cmake, meson, etc.
        """

    @abc.abstractmethod
    def build(self) -> None:
        """Build the component.  Must be overridden by subclasses."""

    def install(self) -> None:
        """Install the built component into the sysroot.

        Default implementation is a no-op.  Override to copy files.
        """

    def package(self) -> Optional[str]:
        """Create a distributable package for this component.

        Default implementation delegates to :class:`PackageBuilder`.
        Returns the path to the created package, or *None*.
        """
        from helpers.packaging import PackageBuilder

        builder = PackageBuilder(self.config.abs_output_dir)
        pkg_path = builder.build_package(
            name=self.name,
            version=self.version,
            sysroot=self.config.abs_sysroot,
            include_paths=self.install_paths if self.install_paths else None,
            metadata={"arch": self.config.arch},
        )
        return pkg_path

    def resolve_dpkbuild(self) -> str:
        """Return the usable `dpkbuild` path or raise a clear error.

        Baker prefers a host-installed `dpkbuild`, then a locally built copy
        from the dimsim source tree, then a copy installed into the sysroot.
        """
        candidates = [
            shutil.which("dpkbuild"),
            os.path.join(self.config.abs_sources_dir, "dimsim", "bin", "dpkbuild"),
            os.path.join(self.config.abs_sysroot, "usr", "bin", "dpkbuild"),
        ]
        for candidate in candidates:
            if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate

        raise RecipeError(
            "dpkbuild not found. Build the 'dimsim' component first or install dpkbuild on PATH."
        )

    # ------------------------------------------------------------------
    # Convenience helpers for subclasses
    # ------------------------------------------------------------------

    def run(self, cmd: List[str], cwd: Optional[str] = None, env: Optional[Dict[str, str]] = None) -> None:
        """Run a shell command, raising :class:`RecipeError` on failure.

        Args:
            cmd: Command and arguments as a list.
            cwd: Working directory.  Defaults to the source directory.
            env: Additional environment variables to merge with the current env.
        """
        work_dir = cwd or self._source_dir
        merged_env: Optional[Dict[str, str]] = None
        if env:
            merged_env = {**os.environ, **env}

        cmd_str = " ".join(str(c) for c in cmd)
        self.log.debug("Running: %s  (cwd=%s)", cmd_str, work_dir)

        result = subprocess.run(
            cmd,
            cwd=work_dir,
            env=build_host_env(merged_env),
            capture_output=True,
            text=True,
        )
        if result.stdout:
            self.log.debug(result.stdout.rstrip())
        if result.stderr:
            self.log.debug(result.stderr.rstrip())
        if result.returncode != 0:
            raise RecipeError(
                f"Command failed (exit {result.returncode}): {cmd_str}\n{result.stderr}"
            )

    def ensure_build_dir(self) -> str:
        """Create and return the build directory for this component."""
        os.makedirs(self._build_dir, exist_ok=True)
        return self._build_dir

    def ensure_source_dir(self) -> str:
        """Create and return the source directory for this component."""
        os.makedirs(self._source_dir, exist_ok=True)
        return self._source_dir

    @property
    def source_dir(self) -> str:
        return self._source_dir

    @property
    def build_dir(self) -> str:
        return self._build_dir

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Recipe {self.name} {self.version}>"
