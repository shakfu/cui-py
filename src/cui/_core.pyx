# cython: language_level=3
"""
cui Cython extension module.

Provides fast implementations of add and greet functions.
"""


cpdef int add(int a, int b):
    """Add two integers.

    Args:
        a: First integer.
        b: Second integer.

    Returns:
        Sum of a and b.
    """
    return a + b


cpdef str greet(str name):
    """Return a greeting string.

    Args:
        name: Name to greet.

    Returns:
        Greeting string.
    """
    return f"Hello, {name}!"
