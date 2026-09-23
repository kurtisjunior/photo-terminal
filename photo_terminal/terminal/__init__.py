"""Terminal I/O bounded context.

This is the only package allowed to touch stdin and stdout. Everything in it
either returns bytes or writes them through :class:`~photo_terminal.terminal.frame.Frame`,
which means the whole render path can be asserted on in a test.
"""
