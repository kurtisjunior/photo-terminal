"""Reports the user reads after the interactive part is over.

The dry-run report and the completion summary. Both are built as values and
rendered to text; printing them is the pipeline's decision, which is why these
functions return strings rather than calling ``print``.
"""
