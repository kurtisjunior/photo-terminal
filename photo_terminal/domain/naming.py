"""The S3 key scheme.

Two pure functions that decide where an image lands in a bucket. They used to
be private to ``uploader``, which meant ``dry_run`` imported
``_normalize_prefix`` and ``_construct_s3_key`` across a module boundary by
their underscored names to work out the same answer - two modules sharing a
rule that neither of them owned.

The rule is domain knowledge, so it lives in the domain and both callers import
it by its public name.
"""

from __future__ import annotations

__all__ = ["construct_s3_key", "normalize_prefix"]


def normalize_prefix(prefix: str) -> str:
    """Strip whitespace and trailing slashes from an S3 prefix.

    Examples:
        ``""`` -> ``""``
        ``"japan"`` -> ``"japan"``
        ``"japan/"`` -> ``"japan"``
        ``"japan/tokyo/"`` -> ``"japan/tokyo"``
    """
    return prefix.strip().rstrip("/")


def construct_s3_key(prefix: str, filename: str) -> str:
    """Join a normalized prefix and a filename into an S3 key.

    Examples:
        ``("japan/tokyo", "image.jpg")`` -> ``"japan/tokyo/image.jpg"``
        ``("", "image.jpg")`` -> ``"image.jpg"``
    """
    if prefix:
        return f"{prefix}/{filename}"
    return filename
