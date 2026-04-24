"""
recipes/vim.py - Vim text editor for BlueyOS (i386, static musl, tiny features).

Builds Vim with --with-features=tiny against the ncurses library already in
the sysroot.  GUI, X11, Perl/Python/Ruby interpreters and NLS are all
disabled to keep the build simple and the binary small.
"""

from __future__ import annotations

import os

from recipes._port_recipe import PortRecipe
from recipes.base import RecipeError

_VERSION = "9.1.0016"
_SHORT = "9.1"


class VimRecipe(PortRecipe):
    name = "vim"
    version = _VERSION
    description = "Vi IMproved text editor — tiny build (static, i386)"
    dependencies = ["musl-blueyos", "ncurses"]
    install_paths = ["usr/bin/vim", "usr/share/vim"]
    pkg_depends = []

    tarball_url = (
        f"https://github.com/vim/vim/archive/refs/tags/v{_VERSION}.tar.gz"
    )
    tarball_name = f"vim-{_VERSION}.tar.gz"
    src_subdir = f"vim-{_VERSION}"

    def build(self) -> None:
        src = self._source_dir
        if not os.path.isdir(src):
            raise RecipeError(
                f"vim source not found at {src}. Run 'baker prepare' first."
            )

        musl_gcc = self._musl_gcc()
        sysroot = self.config.abs_sysroot
        env = {
            "CC": musl_gcc,
            "CFLAGS": f"-O2 -I{sysroot}/usr/include",
            "LDFLAGS": f"-L{sysroot}/usr/lib -static",
            # Tell configure we are cross-compiling so it skips run-tests.
            "vim_cv_toupper_broken": "no",
            "vim_cv_terminfo": "yes",
            "vim_cv_tty_group": "world",
            "vim_cv_tty_mode": "0620",
            "vim_cv_getcwd_broken": "no",
            "vim_cv_stat_ignores_slash": "yes",
            "vim_cv_memmove_handles_overlap": "yes",
            "ac_cv_sizeof_int": "4",
            "ac_cv_sizeof_long": "4",
            "ac_cv_sizeof_time_t": "4",
        }

        self.log.info("Configuring vim %s for i386 static musl", self.version)
        self.run(
            [
                "./configure",
                *self._autoconf_host_flags,
                "--prefix=/usr",
                "--with-features=tiny",
                "--disable-gui",
                "--without-x",
                "--disable-xsmp",
                "--disable-xsmp-interact",
                "--disable-netbeans",
                "--disable-channel",
                "--disable-nls",
                "--disable-acl",
                "--disable-gpm",
                "--disable-sysmouse",
                "--disable-selinux",
                "--disable-smack",
                "--disable-multibyte",
                "--disable-rightleft",
                "--disable-arabic",
                "--disable-farsi",
                "--disable-darwin",
                "--with-tlib=ncurses",
            ],
            cwd=src,
            env=env,
        )

        self.log.info("Building vim %s", self.version)
        make_flags = self.config.kernel.make_flags.split()
        self.run(["make"] + make_flags, cwd=src, env=env)

    def install(self) -> None:
        src = self._source_dir
        staging = self._staging_dir
        os.makedirs(staging, exist_ok=True)

        self.log.info("Installing vim into staging at %s", staging)
        self.run(
            ["make", f"DESTDIR={staging}", "install"],
            cwd=src,
        )
