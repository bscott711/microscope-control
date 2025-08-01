# src/microscope/core/engine/__init__.py

"""
Initializes the engine package.

This file makes the 'engine' directory a Python package and exposes the main
CustomPLogicMDAEngine class for easy importing.
"""

from .main import CustomPLogicMDAEngine

__all__ = ["CustomPLogicMDAEngine"]
