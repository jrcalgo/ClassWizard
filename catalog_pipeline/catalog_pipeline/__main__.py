"""Allows ``python -m catalog_pipeline``."""
import sys

from .cli import main

sys.exit(main())
