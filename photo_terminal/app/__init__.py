"""The composition layer: what the CLI decides, as opposed to what it computes.

This is the top of the dependency contract - the only package allowed to import
every other one, and the only one that knows a screen and an S3 call belong in
the same sentence.

- :mod:`~photo_terminal.app.cli` turns argv into a context and an exit code.
- :mod:`~photo_terminal.app.pipeline` is the run, as an ordered list of steps.
- :mod:`~photo_terminal.app.context` is the state those steps thread and the
  collaborators they reach through.
- :mod:`~photo_terminal.app.wiring` fills those collaborators in for real.
- :mod:`~photo_terminal.app.config` reads ``photo-uploader.yaml``.
- :mod:`~photo_terminal.app.reporter` draws progress on the console.
"""
