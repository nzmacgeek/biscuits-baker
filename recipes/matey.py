"""
recipes/matey.py - Recipe for matey (getty for BlueyOS).

matey is a single-file C program linked statically against musl-blueyos.
Its Makefile accepts ``MUSL_PREFIX`` and produces ``build/matey``.
``make package`` uses dpkbuild to create a ``.dpk``.
"""

from __future__ import annotations

from recipes._musl_package import MuslPackageRecipe


class MateyRecipe(MuslPackageRecipe):
    """matey — getty / login prompt for BlueyOS."""

    name = "matey"
    version = "1.0.0"
    dependencies = ["musl-blueyos", "claw"]
    binary_name = "matey"
    binary_dest = "sbin/matey"
    install_paths = ["sbin/matey"]
