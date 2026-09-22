"""Pillow, and nothing else.

Scanning a folder for images, optimizing one to a target size, and running a
batch of them through that optimizer into a temp directory. No terminal, no
AWS, and no opinion about how progress is drawn - progress goes to the
:class:`~photo_terminal.domain.progress.ProgressReporter` the caller supplies.
"""
