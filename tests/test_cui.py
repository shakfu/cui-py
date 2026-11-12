"""Tests for cui Cython extension module."""

import cui


def test_add():
    """Test add function."""
    assert cui.add(1, 2) == 3
    assert cui.add(-1, 1) == 0
    assert cui.add(0, 0) == 0


def test_greet():
    """Test greet function."""
    assert cui.greet("World") == "Hello, World!"
    assert cui.greet("Python") == "Hello, Python!"
