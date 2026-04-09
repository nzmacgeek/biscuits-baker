"""
setup.py - Package setup for Baker.
"""

from setuptools import setup, find_packages

setup(
    name="biscuits-baker",
    version="0.1.0",
    description="Baker – bootstrapper for the Biscuits kernel and ClawOS system",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    python_requires=">=3.9",
    install_requires=[
        "PyYAML>=6.0",
    ],
    packages=find_packages(exclude=["tests*"]),
    py_modules=[
        "baker",
        "config",
        "stage_runner",
        "deps",
        "recipe_registry",
    ],
    entry_points={
        "console_scripts": [
            "baker=baker:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Software Development :: Build Tools",
    ],
)
