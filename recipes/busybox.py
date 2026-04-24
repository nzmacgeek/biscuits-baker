"""
recipes/busybox.py - BusyBox 1.36.1 for BlueyOS (i386, static musl).

BusyBox provides ~200 POSIX utilities in a single statically-linked binary,
including:
  sh, ls, cp, mv, rm, mkdir, cat, echo, grep, sed, awk, find, xargs,
  sort, uniq, head, tail, wc, cut, tr, tar, gzip, bzip2, xz,
  ifconfig, route, ping, ps, kill, mount, umount, df, du, ...

This is especially important for self-hosting: autoconf-based ./configure
scripts rely on sh, sed, awk, grep, find, xargs, sort, etc.

BusyBox uses Kconfig (like the Linux kernel).  We start from defconfig
(a minimal, safe base) and then apply our overrides via a .config fragment:
  - CONFIG_STATIC=y       — fully static binary (no .so dependency)
  - CONFIG_EXTRA_CFLAGS="-m32"  — ensure 32-bit code generation
  - Disable applets requiring headers we haven't ported (udhcpc, ip, ...)

The resulting binary is installed to /bin/busybox with symlinks for each
applet under /bin/ and /usr/bin/.
"""

from __future__ import annotations

import os

from recipes._port_recipe import PortRecipe
from recipes.base import RecipeError

_VERSION = "1.36.1"

# Minimal .config fragment applied ON TOP of defconfig.
_CONFIG_FRAGMENT = """\
CONFIG_STATIC=y
CONFIG_EXTRA_CFLAGS="-m32"
CONFIG_EXTRA_LDFLAGS="-static"
# CONFIG_FEATURE_SUID is not set
# CONFIG_SELINUX is not set
# CONFIG_UDHCPC is not set
# CONFIG_UDHCPD is not set
# CONFIG_FEATURE_UDHCP_RFC3397 is not set
# CONFIG_IPCALC is not set
# CONFIG_IP is not set
# CONFIG_IPLINK is not set
# CONFIG_IPROUTE is not set
# CONFIG_IPNEIGH is not set
# CONFIG_IPRULE is not set
# CONFIG_IPTUNNEL is not set
# CONFIG_IPADDR is not set
# CONFIG_PING6 is not set
# CONFIG_TRACEROUTE6 is not set
CONFIG_FEATURE_PREFER_APPLETS=y
CONFIG_FEATURE_SH_IS_ASH=y
CONFIG_FEATURE_BASH_IS_NONE=y
CONFIG_ASH=y
CONFIG_ASH_JOB_CONTROL=y
CONFIG_HUSH=n
CONFIG_SH_MATH_SUPPORT=y
CONFIG_SED=y
CONFIG_AWK=y
CONFIG_GREP=y
CONFIG_EGREP=y
CONFIG_FGREP=y
CONFIG_FIND=y
CONFIG_XARGS=y
CONFIG_SORT=y
CONFIG_UNIQ=y
CONFIG_HEAD=y
CONFIG_TAIL=y
CONFIG_WC=y
CONFIG_CUT=y
CONFIG_TR=y
CONFIG_TAR=y
CONFIG_FEATURE_TAR_LONG_OPTIONS=y
CONFIG_GZIP=y
CONFIG_GUNZIP=y
CONFIG_BUNZIP2=y
CONFIG_FEATURE_BZIP2_DECOMPRESS=y
CONFIG_WGET=y
CONFIG_FEATURE_WGET_HTTPS=n
CONFIG_LESS=y
CONFIG_VI=y
CONFIG_DIFF=y
CONFIG_PATCH=y
CONFIG_EXPR=y
CONFIG_TEST=y
CONFIG_PRINTF=y
CONFIG_ECHO=y
CONFIG_CAT=y
CONFIG_LS=y
CONFIG_CP=y
CONFIG_MV=y
CONFIG_RM=y
CONFIG_MKDIR=y
CONFIG_CHMOD=y
CONFIG_CHOWN=y
CONFIG_CHGRP=y
CONFIG_PS=y
CONFIG_KILL=y
CONFIG_KILLALL=y
CONFIG_MOUNT=y
CONFIG_UMOUNT=y
CONFIG_DF=y
CONFIG_DU=y
CONFIG_IFCONFIG=y
CONFIG_PING=y
CONFIG_HOSTNAME=y
CONFIG_DATE=y
CONFIG_BASENAME=y
CONFIG_DIRNAME=y
CONFIG_ID=y
CONFIG_WHOAMI=y
CONFIG_PWD=y
CONFIG_ENV=y
CONFIG_SLEEP=y
CONFIG_TOUCH=y
CONFIG_LN=y
CONFIG_READLINK=y
CONFIG_REALPATH=y
CONFIG_STAT=y
CONFIG_MD5SUM=y
CONFIG_SHA256SUM=y
CONFIG_WHICH=y
CONFIG_STRINGS=y
CONFIG_HEXDUMP=y
CONFIG_OD=y
CONFIG_CPIO=y
CONFIG_DD=y
CONFIG_MKTEMP=y
CONFIG_TEE=y
CONFIG_YES=y
CONFIG_TRUE=y
CONFIG_FALSE=y
CONFIG_NOHUP=y
"""


class BusyboxRecipe(PortRecipe):
    name = "busybox"
    version = _VERSION
    description = "BusyBox: ~200 POSIX utilities in one static i386 binary"
    dependencies = ["musl-blueyos"]
    install_paths = ["bin/busybox"]
    pkg_depends = []

    tarball_url = f"https://busybox.net/downloads/busybox-{_VERSION}.tar.bz2"
    tarball_name = f"busybox-{_VERSION}.tar.bz2"
    src_subdir = f"busybox-{_VERSION}"

    def build(self) -> None:
        src = self._source_dir
        if not os.path.isdir(src):
            raise RecipeError(
                f"BusyBox source not found at {src}. Run 'baker prepare' first."
            )

        musl_gcc = self._musl_gcc()
        make_flags = self.config.kernel.make_flags.split()

        # Step 1: generate base defconfig for i386
        self.log.info("Generating BusyBox defconfig")
        self.run(["make", "defconfig", "ARCH=i386"], cwd=src)

        # Step 2: apply our config fragment on top of defconfig
        config_path = os.path.join(src, ".config")
        with open(config_path, "a") as fh:
            fh.write("\n# BlueyOS overrides\n")
            fh.write(_CONFIG_FRAGMENT)

        # Step 3: olddefconfig resolves any conflicts introduced by the fragment
        self.log.info("Running olddefconfig to resolve conflicts")
        self.run(["make", "olddefconfig", "ARCH=i386"], cwd=src)

        # Step 4: build with musl-gcc
        self.log.info("Building BusyBox %s with musl-gcc", self.version)
        self.run(
            [
                "make",
                f"CC={musl_gcc}",
                "ARCH=i386",
                "CROSS_COMPILE=",   # disable prefix; we set CC directly
                "HOSTCC=gcc",
                "busybox",          # just the binary, not install target
            ]
            + make_flags,
            cwd=src,
        )

    def install(self) -> None:
        src = self._source_dir
        staging = self._staging_dir

        # BusyBox installs via 'make install CONFIG_PREFIX=<dir>'
        # This creates bin/busybox + symlinks in bin/ and sbin/
        os.makedirs(staging, exist_ok=True)
        self.log.info("Installing BusyBox into staging at %s", staging)
        self.run(
            [
                "make",
                "install",
                f"CONFIG_PREFIX={staging}",
                "ARCH=i386",
                "CROSS_COMPILE=",
            ],
            cwd=src,
        )

        # Add /usr/bin symlinks for the most common tools so autoconf scripts
        # that look in /usr/bin/sed etc. find them.
        usr_bin = os.path.join(staging, "usr", "bin")
        bin_dir = os.path.join(staging, "bin")
        os.makedirs(usr_bin, exist_ok=True)
        common_tools = [
            "sed", "awk", "grep", "egrep", "fgrep", "find", "xargs",
            "sort", "uniq", "head", "tail", "wc", "cut", "tr",
            "basename", "dirname", "realpath", "readlink", "which",
            "env", "printf", "expr", "test",
        ]
        for tool in common_tools:
            symlink_path = os.path.join(usr_bin, tool)
            target = os.path.join(bin_dir, tool)
            if os.path.exists(target) and not os.path.exists(symlink_path):
                os.symlink(f"../../bin/{tool}", symlink_path)
