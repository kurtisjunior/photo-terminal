"""The domain: what this tool knows, with nothing about how it is told.

Nothing in here prints, opens a socket, shells out, or imports another package
of ``photo_terminal``. That is the whole rule, and it is what makes this the
bottom layer of the dependency contract in ``pyproject.toml``: every other
package may import ``domain``, and ``domain`` may import none of them.

What lives here is the vocabulary the rest of the app speaks in - the models,
the S3 key scheme, the reorder rules, the confirmation text - plus the two
ports through which the layers above it report progress and failure.
"""
