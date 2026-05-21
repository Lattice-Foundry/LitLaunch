"""Sanitized support bundle rendering."""

from __future__ import annotations

from litlaunch.inspect.models import DiagnosticItem, DiagnosticsReport
from litlaunch.redaction import redact_sensitive_text
from litlaunch.version import __version__


class SanitizedBundleRenderer:
    """Render a concise copyable support bundle."""

    SANITIZATION_NOTE = (
        "This report is sanitized with pattern-based redaction and avoids raw "
        "environment dumps, raw environment variables, and shutdown tokens. "
        "Review it before sharing; encoded, URL-wrapped, reformatted, or "
        "app-specific secrets may not always be detected."
    )

    def __init__(self, *, include_details: bool = True) -> None:
        self.include_details = include_details

    def render(self, report: DiagnosticsReport) -> str:
        """Render a sanitized text support bundle."""

        status = "ok" if report.ok else "failed"
        lines = [
            "LitLaunch Support Bundle",
            f"Version: {__version__}",
            f"Generated at: {redact_sensitive_text(report.generated_at_utc)}",
            f"Summary: {status}; {report.errors} errors; {report.warnings} warnings",
            f"Note: {self.SANITIZATION_NOTE}",
            "",
        ]
        for section in report.sections:
            lines.append(redact_sensitive_text(section.title))
            for item in section.items:
                lines.append(f"- {_render_item(item)}")
                if self.include_details and item.detail:
                    detail = redact_sensitive_text(item.detail)
                    for detail_line in detail.splitlines():
                        lines.append(f"  {detail_line}")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"


def _render_item(item: DiagnosticItem) -> str:
    name = redact_sensitive_text(item.name)
    message = redact_sensitive_text(item.message)
    return f"[{item.status.value.upper()}] {name}: {message}"
