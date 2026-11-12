"""
cui - Cython bindings for the cui UI framework.

Example usage:
    >>> import cui
    >>> cui.add(1, 2)
    3
    >>> cui.greet("World")
    'Hello, World!'
"""

from cui._core import add, greet

__all__ = ["add", "greet"]
__version__ = "0.1.0"
