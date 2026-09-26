"""argv in, exit code out.

What is left of ``main()``: parse the arguments, load the configuration, say
what is about to happen, and hand a :class:`~photo_terminal.app.context.PipelineContext`
to :func:`~photo_terminal.app.pipeline.execute`. Everything the run actually
does is a step in :mod:`photo_terminal.app.pipeline`.
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

from photo_terminal.app.config import load_config
from photo_terminal.app.context import CliOptions, PipelineContext
from photo_terminal.app.pipeline import execute, report_failure
from photo_terminal.app.reporter import ConsoleProgressReporter
from photo_terminal.app.wiring import build_deps
from photo_terminal.domain.errors import InvalidSourceFolder, PhotoTerminalError
from photo_terminal.domain.models import Config
from photo_terminal.domain.progress import ProgressReporter

__all__ = ["build_parser", "render_effective_config", "resolve_source", "run"]

_EPILOG = """
Examples:
  %(prog)s ./photo.jpg japan/tokyo
  %(prog)s ./photos italy/trapani
  %(prog)s ./vacation spain/barcelona --dry-run

Configuration:
  Edit photo-uploader.yaml to change default settings.
  CLI arguments override config file values.
"""

_DEBUG_LOG = "/tmp/photo_terminal_debug.log"


def build_parser(default_target_size_kb: int) -> argparse.ArgumentParser:
    """Build the small command-line surface."""
    parser = argparse.ArgumentParser(
        prog="pt",
        description="Upload and optimize photos to S3 with inline preview",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_EPILOG,
    )
    parser.add_argument("source_path", help="Image file or folder to upload")
    parser.add_argument(
        "destination",
        nargs="?",
        help='S3 folder path (e.g. "japan/tokyo"); omit to browse',
    )
    parser.add_argument(
        "--prefix",
        help=argparse.SUPPRESS,
        default=None,
    )
    parser.add_argument(
        "--target-size",
        type=int,
        metavar="KB",
        help=f"Target file size in KB (default: {default_target_size_kb})",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview without uploading")
    return parser


def resolve_source(source_path: str) -> Path:
    """Resolve and validate the source file or folder.

    Args:
        source_path: The path as it was typed.

    Returns:
        The resolved path.

    Raises:
        InvalidSourceFolder: If it does not exist.
    """
    path = Path(source_path).expanduser().resolve()

    if not path.exists():
        raise InvalidSourceFolder(f"Source path does not exist: {source_path}")

    return path


def render_effective_config(cfg: Config, options: CliOptions) -> str:
    """The banner describing what this run is about to do."""
    lines = [
        "Photo Upload Manager",
        "=" * 50,
        "",
        "Configuration:",
        f"  Source:         {options.source}",
        f"  S3 bucket:      {cfg.bucket}",
        f"  S3 prefix:      {options.prefix if options.prefix else '(root)'}",
        f"  AWS profile:    {cfg.aws_profile or '(env vars)'}",
        f"  Target size:    {cfg.target_size_kb} KB",
        f"  Dry-run mode:   {'Yes' if options.dry_run else 'No'}",
        "",
    ]

    target = f"s3://{cfg.bucket}/{options.prefix}/" if options.prefix else f"s3://{cfg.bucket}/"
    lines.append(f"Upload target: {target}")
    lines.append("")

    return "\n".join(lines)


def _enable_debug_logging() -> None:
    """Log to a file and the console when ``PHOTO_TERMINAL_DEBUG`` is set."""
    logging.basicConfig(
        filename=_DEBUG_LOG,
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        force=True,
    )
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    logging.getLogger().addHandler(console_handler)

    logging.info("=== Photo Terminal Debug Mode ===")
    logging.info("Terminal: %s", os.environ.get("TERM", "unknown"))
    logging.info("TERM_PROGRAM: %s", os.environ.get("TERM_PROGRAM", "unknown"))


def run(argv: list[str] | None = None, reporter: ProgressReporter | None = None) -> int:
    """Run the CLI.

    Args:
        argv: Arguments without the program name. Defaults to ``sys.argv[1:]``.
        reporter: Where output goes. Defaults to the console reporter.

    Returns:
        The process exit code.
    """
    report = reporter if reporter is not None else ConsoleProgressReporter()

    if os.environ.get("PHOTO_TERMINAL_DEBUG"):
        _enable_debug_logging()

    try:
        cfg = load_config(reporter=report)
    except PhotoTerminalError as e:
        return report_failure(report, e)

    args = build_parser(cfg.target_size_kb).parse_args(argv)

    if args.destination is not None and args.prefix is not None:
        report.warn("Error: Give the S3 folder once, as the second argument")
        return 2

    try:
        source = resolve_source(args.source_path)
    except PhotoTerminalError as e:
        return report_failure(report, e)

    options = CliOptions(
        source=source,
        prefix=args.destination if args.destination is not None else args.prefix,
        target_size_kb=args.target_size,
        dry_run=args.dry_run,
    )
    cfg = cfg.with_target_size(options.target_size_kb)

    report.info(render_effective_config(cfg, options))

    return execute(PipelineContext(config=cfg, options=options), build_deps(report))
