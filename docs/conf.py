# pylint: skip-file
"""Sphinx configuration for Fools_Arena."""

import os
import sys

sys.path.insert(0, os.path.abspath(".."))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Fools_Arena.settings")

import django

django.setup()

project = "Fools_Arena"
copyright = "2026, Maksim Bayarchuk, Kiryl Alishkevich, Aliaksandr Saroka"
author = "Maksim Bayarchuk, Kiryl Alishkevich, Aliaksandr Saroka"
release = "0.1"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

napoleon_google_docstring = True
napoleon_numpy_docstring = False

html_theme = "alabaster"
html_static_path = ["_static"]

autodoc_default_options = {
    "members": True,
    "undoc-members": True,
    "show-inheritance": True,
}
