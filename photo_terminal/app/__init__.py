"""The composition layer: what the CLI decides, as opposed to what it computes.

Phase 5 lands the first tenant, :mod:`photo_terminal.app.reporter` - the
concrete :class:`~photo_terminal.progress.ProgressReporter` the CLI hands to
library code. Phase 6 adds the pipeline and its typed context, and ``__main__``
shrinks to argv parsing.
"""
