"""A usage dashboard for a repository: run the harness's checks, record and view them.

A **viewer, not an actor**. It runs the harness's own deterministic checks and
renders their outcome. It executes nothing on a model's behalf, adds no mutation
path and needs no server: the output is one self-contained HTML file.
"""

from harness.dashboard.render import render_html
from harness.dashboard.report import REPORT_VERSION, Check, Run, collect, provenance
from harness.dashboard.store import (
    DEFAULT_DIRNAME,
    History,
    ReportError,
    latest_run,
    list_runs,
    load_history,
    reports_dir,
    write_run,
)

__all__ = [
    "DEFAULT_DIRNAME",
    "REPORT_VERSION",
    "Check",
    "History",
    "ReportError",
    "Run",
    "collect",
    "latest_run",
    "list_runs",
    "load_history",
    "provenance",
    "render_html",
    "reports_dir",
    "write_run",
]
