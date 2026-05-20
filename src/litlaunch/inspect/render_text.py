"""Plain text diagnostics rendering."""

from __future__ import annotations

from litlaunch.inspect.models import DiagnosticItem, DiagnosticsReport
from litlaunch.redaction import redact_sensitive_text


class TextDiagnosticsRenderer:
    """Render structured diagnostics to plain text."""

    def __init__(self, *, include_details: bool = True) -> None:
        self.include_details = include_details

    def render(self, report: DiagnosticsReport) -> str:
        """Render a diagnostics report to a deterministic text string."""

        lines = [redact_sensitive_text(report.title), ""]
        for section in report.sections:
            lines.append(redact_sensitive_text(section.title))
            for item in section.items:
                lines.append(_render_item(item))
                if self.include_details and item.detail:
                    detail = redact_sensitive_text(item.detail)
                    for detail_line in detail.splitlines():
                        lines.append(f"    {detail_line}")
            lines.append("")
        lines.append("Summary")
        lines.append(f"{report.errors} errors, {report.warnings} warnings")
        return "\n".join(lines).rstrip() + "\n"


def _render_item(item: DiagnosticItem) -> str:
    name = redact_sensitive_text(item.name)
    message = redact_sensitive_text(item.message)
    return f"[{item.status.value.upper()}] {name}: {message}"
