"""S3, behind ports.

:mod:`photo_terminal.storage.ports` states what the layers above need from
storage; the rest of the package is the boto3 implementation of it. Screens and
pipeline steps depend on the port, which is why the S3 browser can be driven by
a list of strings in a test and why nothing outside this package imports boto3.
"""
