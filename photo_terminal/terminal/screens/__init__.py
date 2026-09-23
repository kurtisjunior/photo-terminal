"""The full-screen interactive screens.

Every screen in the app lives here, and they share everything that is not
specific to one of them: one :class:`~photo_terminal.terminal.session.TerminalSession`
for the terminal's state, one reader for keys, one
:class:`~photo_terminal.terminal.layout.Layout` for geometry, one
:class:`~photo_terminal.terminal.preview.service.PreviewService` for previews,
and one :class:`~photo_terminal.terminal.screens.widgets.ListView` for bounded
navigation and scrolling.
"""
