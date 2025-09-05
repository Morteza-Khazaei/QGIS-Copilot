import os
import sys
from datetime import datetime

# -- Project information -----------------------------------------------------

project = 'QGIS Copilot'
author = 'QGIS Copilot Team'
copyright = f"{datetime.now().year}, {author}"
release = ''

# -- General configuration ---------------------------------------------------

extensions = [
    'sphinx.ext.autosectionlabel',
    'sphinx.ext.napoleon',
]

autosectionlabel_prefix_document = True
templates_path = ['_templates']
exclude_patterns = ['_build']

# -- Options for HTML output -------------------------------------------------

html_theme = 'sphinx_rtd_theme'
html_static_path = ['_static']
html_theme_options = {
    'collapse_navigation': False,
    'navigation_depth': 3,
}

