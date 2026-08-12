"""Markdown summary report writer for ha_sim_test runs.

Writes a human- and machine-readable Markdown summary alongside the
existing plain-text log report produced by :class:`LogMonitor`.

The summary contains:

- Run metadata (timestamp, container, elapsed, pass/fail counts)
- Per-recipe timing table
- Individual check results (PASS/FAIL lines)
- Links to the corresponding log report file

Both single-container and parallel runs use the same writer; the
parallel runner passes a list of per-container results.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .const import InstanceConfig


@dataclass
class RunSummary:
    """Collected summary data for a single test run.

    Used for both single-container and parallel runs.  In parallel mode,
    one :class:`RunSummary` is built per container and merged into a
    combined report.
    """

    instance: InstanceConfig
    started_wall: float = 0.0
    elapsed: float = 0.0
    passed: int = 0
    failed: int = 0
    recipe_stats: dict[str, dict[str, Any]] = field(default_factory=dict)
    results: list[str] = field(default_factory=list)
    log_report_path: str | None = None
    error: str | None = None

    @property
    def total(self) -> int:
        """Total checks (passed + failed)."""
        return self.passed + self.failed

    @property
    def status(self) -> str:
        """Overall status string: ``PASS``, ``FAIL``, or ``ERROR``."""
        if self.error:
            return "ERROR"
        return "FAIL" if self.failed > 0 else "PASS"


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences from *text*."""
    import re

    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def write_summary_report(
    summaries: list[RunSummary],
    *,
    reports_dir: Path,
    log_report_paths: dict[str, str] | None = None,
) -> Path:
    """Write a Markdown summary report for one or more containers.

    :param summaries: One :class:`RunSummary` per container (single-element
        list for single-container mode).
    :param reports_dir: Directory to write the report into.  Created if
        it does not exist.
    :param log_report_paths: Optional mapping of container name to the
        plain-text log report path, for cross-referencing.
    :return: Path to the written Markdown report.
    """
    reports_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")

    # Single-container: use container name in filename.
    # Parallel: use "parallel" prefix.
    if len(summaries) == 1:
        container = summaries[0].instance.name
        filename = f"summary_{container}_{ts}.md"
    else:
        filename = f"summary_parallel_{ts}.md"

    path = reports_dir / filename

    total_passed = sum(s.passed for s in summaries)
    total_failed = sum(s.failed for s in summaries)
    total_elapsed = max(s.elapsed for s in summaries) if summaries else 0.0
    overall_status = "PASS" if total_failed == 0 else "FAIL"

    lines: list[str] = []
    lines.append("# ha_sim_test Summary Report")
    lines.append("")
    lines.append(f"**Generated:** {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**Status:** {overall_status}")
    lines.append(
        f"**Totals:** {total_passed} passed, {total_failed} failed,"
        f" {total_passed + total_failed} total"
    )
    lines.append(f"**Wall time:** {total_elapsed:.1f}s ({total_elapsed / 60:.1f} min)")
    lines.append(f"**Containers:** {len(summaries)}")
    lines.append("")

    # -- Per-container overview -------------------------------------------
    if len(summaries) > 1:
        lines.append("## Per-container overview")
        lines.append("")
        lines.append("| Container | Pass | Fail | Time (s) | Status |")
        lines.append("|-----------|------|------|----------|--------|")
        for s in summaries:
            lines.append(
                f"| {s.instance.name} | {s.passed} | {s.failed}"
                f" | {s.elapsed:.1f} | {s.status} |"
            )
        lines.append("")

    # -- Per-recipe timing -------------------------------------------------
    all_stats: dict[str, dict[str, Any]] = {}
    for s in summaries:
        for rid, stats in s.recipe_stats.items():
            all_stats[rid] = {**stats, "container": s.instance.name}

    if all_stats:
        lines.append("## Per-recipe timing")
        lines.append("")
        if len(summaries) > 1:
            lines.append("| Recipe | Container | Pass | Fail | Time (s) | Title |")
            lines.append("|--------|-----------|------|------|----------|-------|")
            for rid in sorted(all_stats):
                st = all_stats[rid]
                lines.append(
                    f"| {rid} | {st.get('container', '?')} "
                    f"| {st.get('passed', 0)} | {st.get('failed', 0)}"
                    f" | {st.get('duration', 0.0):.1f}"
                    f" | {st.get('title', '')} |"
                )
        else:
            lines.append("| Recipe | Pass | Fail | Time (s) | Title |")
            lines.append("|--------|------|------|----------|-------|")
            for rid in sorted(all_stats):
                st = all_stats[rid]
                lines.append(
                    f"| {rid} | {st.get('passed', 0)} | {st.get('failed', 0)}"
                    f" | {st.get('duration', 0.0):.1f}"
                    f" | {st.get('title', '')} |"
                )
        lines.append("")

    # -- Check results -----------------------------------------------------
    lines.append("## Check results")
    lines.append("")
    for s in summaries:
        if not s.results:
            continue
        if len(summaries) > 1:
            lines.append(f"### {s.instance.name}")
            lines.append("")
        for line in s.results:
            clean = _strip_ansi(line).strip()
            lines.append(f"- {clean}")
        lines.append("")

    # -- Errors ------------------------------------------------------------
    error_summaries = [s for s in summaries if s.error]
    if error_summaries:
        lines.append("## Container errors")
        lines.append("")
        for s in error_summaries:
            lines.append(f"- **{s.instance.name}:** {s.error}")
        lines.append("")

    # -- Log report references ---------------------------------------------
    log_paths = log_report_paths or {}
    referenced = {
        s.instance.name: s.log_report_path for s in summaries if s.log_report_path
    }
    # Merge explicit paths over per-summary ones
    for name, p in log_paths.items():
        referenced[name] = p

    if referenced:
        lines.append("## Log reports")
        lines.append("")
        for name in sorted(referenced):
            p = referenced[name]
            if p:
                lines.append(f"- `{name}`: {p}")
        lines.append("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
