"""JSON diagnostics rendering."""

from __future__ import annotations

import json

from litlaunch.inspect.models import DiagnosticsReport


class JSONDiagnosticsRenderer:
    """Render structured diagnostics to deterministic JSON."""

    def render(self, report: DiagnosticsReport) -> str:
        """Render a diagnostics report as pretty JSON."""

        return json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n"
