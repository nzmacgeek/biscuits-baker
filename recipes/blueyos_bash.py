"""
recipes/blueyos_bash.py - Recipe for blueyos-bash.

blueyos-bash is a wrapper repository that builds bash (with readline and
ncurses) statically against musl-blueyos.  Its Makefile calls
``scripts/build-bash.sh`` internally.

The produced binary is placed at ``build/bash/bin/bash`` inside the
source tree.  Baker installs it to ``sysroot/bin/bash`` and creates a
``/bin/sh`` symlink.
"""

from __future__ import annotations

import os

from recipes.base import RecipeError
from recipes._musl_package import MuslPackageRecipe


class BlueyosBashRecipe(MuslPackageRecipe):
    """bash built against musl-blueyos for BlueyOS."""

    name = "blueyos-bash"
    version = "5.2.0"
    dependencies = ["musl-blueyos"]
    install_paths = ["bin/bash", "bin/sh"]

    def install(self) -> None:
        src = self._source_dir
        # The bash binary is placed under build/bash/bin/bash by the wrapper Makefile
        candidates = [
            os.path.join(src, "build", "bash", "bin", "bash"),
            os.path.join(src, "build", "bash"),
            os.path.join(src, "bash", "bash"),
        ]
        for path in candidates:
            if os.path.isfile(path):
                self.sysroot.ensure_dir("bin")
                self.sysroot.install_binary(path, "bin/bash")
                self.sysroot.symlink("/bin/bash", "bin/sh")
                self.log.info("Installed bash → sysroot/bin/bash")
                return
        self.log.warning("bash binary not found after build; skipping install.")
