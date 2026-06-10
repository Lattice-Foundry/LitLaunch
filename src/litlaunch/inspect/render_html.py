"""Standalone HTML diagnostics rendering."""

from __future__ import annotations

from collections.abc import Mapping
from html import escape

from litlaunch.inspect.models import DiagnosticsReport

PATH_VALUE_NAMES = {
    "Python executable",
    "Resolved app path",
    "Working directory",
}


class HTMLDiagnosticsRenderer:
    """Render structured diagnostics to a sanitized standalone HTML report."""

    SANITIZATION_NOTE = (
        "This report is sanitized with pattern-based redaction and avoids raw "
        "environment dumps, raw environment variables, and shutdown tokens."
    )
    PRIVACY_NOTE = (
        "Review this report before sharing. Pattern-based redaction may not "
        "detect encoded, URL-wrapped, reformatted, or app-specific secrets."
    )

    def __init__(self, *, include_details: bool = True) -> None:
        self.include_details = include_details

    def render(self, report: DiagnosticsReport) -> str:
        """Render a diagnostics report as dependency-free HTML."""

        data = report.to_dict()
        status_text = "OK" if data["ok"] else "Needs attention"
        status_class = "summary-ok" if data["ok"] else "summary-error"
        raw_sections = data["sections"]
        sections = raw_sections if isinstance(raw_sections, list) else []
        profile_name = _find_profile_name(sections)
        lines = [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '  <meta charset="utf-8">',
            '  <meta name="viewport" content="width=device-width, initial-scale=1">',
            f"  <title>{_html(data['title'])}</title>",
            "  <style>",
            "    :root {",
            "      color-scheme: light dark;",
            "      --bg: #f7f8fa;",
            "      --panel: #ffffff;",
            "      --text: #1f2933;",
            "      --muted: #5f6b7a;",
            "      --border: #d9dee7;",
            "      --blue: #1c83e1;",
            "      --green: #17803d;",
            "      --warning: #8a7700;",
            "      --red: #c50f1f;",
            "      --code-bg: #f1f4f8;",
            "    }",
            "    @media (prefers-color-scheme: dark) {",
            "      :root {",
            "        --bg: #111418;",
            "        --panel: #171b21;",
            "        --text: #e7ecf3;",
            "        --muted: #a8b3c2;",
            "        --border: #303741;",
            "        --warning: #f9f1a5;",
            "        --code-bg: #202631;",
            "      }",
            "    }",
            "    * { box-sizing: border-box; }",
            "    body {",
            "      margin: 0;",
            "      background: var(--bg);",
            "      color: var(--text);",
            "      font-family: system-ui, -apple-system, Segoe UI, sans-serif;",
            "      line-height: 1.5;",
            "    }",
            "    main { max-width: 1080px; margin: 0 auto; padding: 2rem; }",
            "    header { margin-bottom: 1.5rem; }",
            "    h1 { margin: 0 0 .35rem; "
            "font-size: clamp(1.8rem, 4vw, 2.6rem); line-height: 1.1; }",
            "    h2 { margin: 0 0 .85rem; font-size: 1.12rem; line-height: 1.2; }",
            "    .meta, .note { color: var(--muted); }",
            "    .meta { margin: 0; }",
            "    .summary {",
            "      display: grid;",
            "      gap: .85rem;",
            "      grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));",
            "      margin: 1.4rem 0;",
            "    }",
            "    .summary-card, .note-card, section {",
            "      background: var(--panel);",
            "      border: 1px solid var(--border);",
            "      border-radius: 8px;",
            "      box-shadow: 0 1px 2px rgb(0 0 0 / 6%);",
            "    }",
            "    .summary-card { padding: .85rem 1rem; }",
            "    .summary-label { color: var(--muted); font-size: .78rem; "
            "font-weight: 700; text-transform: uppercase; }",
            "    .summary-value { display: block; margin-top: .2rem; "
            "font-size: 1.35rem; font-weight: 750; }",
            "    .summary-ok { color: var(--green); }",
            "    .summary-error { color: var(--red); }",
            "    .note-card { border-left: 4px solid var(--blue); "
            "padding: 1rem; margin: 0 0 1.25rem; }",
            "    .note-card p { margin: 0; }",
            "    .note-card p + p { margin-top: .45rem; }",
            "    section { overflow: hidden; margin-top: 1rem; }",
            "    section h2 { padding: 1rem 1rem 0; }",
            "    .table-wrap { overflow-x: auto; }",
            "    table { border-collapse: collapse; width: 100%; min-width: 720px; }",
            "    th, td {",
            "      border-top: 1px solid var(--border);",
            "      padding: .72rem 1rem;",
            "      text-align: left;",
            "      vertical-align: top;",
            "    }",
            "    th {",
            "      color: var(--muted);",
            "      font-size: .76rem;",
            "      letter-spacing: .02em;",
            "      text-transform: uppercase;",
            "      background: color-mix(in srgb, var(--panel), var(--bg) 45%);",
            "    }",
            "    td { word-break: break-word; overflow-wrap: anywhere; }",
            "    .status {",
            "      display: inline-block;",
            "      min-width: 5.8rem;",
            "      border-radius: 999px;",
            "      padding: .18rem .55rem;",
            "      font-size: .75rem;",
            "      font-weight: 800;",
            "      text-align: center;",
            "      border: 1px solid currentColor;",
            "    }",
            "    .status-ok { color: var(--green); }",
            "    .status-warning { color: var(--warning); }",
            "    .status-error { color: var(--red); }",
            "    .status-info { color: var(--blue); }",
            "    code {",
            "      display: inline-block;",
            "      max-width: 100%;",
            "      background: var(--code-bg);",
            "      border-radius: 6px;",
            "      padding: .08rem .28rem;",
            "      white-space: pre-wrap;",
            "      word-break: break-word;",
            "      overflow-wrap: anywhere;",
            "    }",
            "    @media print {",
            "      body { background: #fff; }",
            "      main { max-width: none; padding: 0; }",
            "      .summary-card, .note-card, section { box-shadow: none; "
            "break-inside: avoid; }",
            "    }",
            "  </style>",
            "</head>",
            "<body>",
            "<main>",
            "  <header>",
            f"    <h1>{_html(data['title'])}</h1>",
            (
                f'    <p class="meta">Generated by {_html(data["generated_by"])} '
                f"{_html(data['litlaunch_version'])} at "
                f"{_html(data['generated_at_utc'])}</p>"
            ),
            "  </header>",
            '  <div class="summary" aria-label="Diagnostics summary">',
            (
                '    <div class="summary-card"><span class="summary-label">'
                "Status</span>"
                f'<span class="summary-value {_html_attr(status_class)}">'
                f"{_html(status_text)}</span></div>"
            ),
            (
                '    <div class="summary-card"><span class="summary-label">'
                "Errors</span>"
                f'<span class="summary-value summary-error">'
                f"{_html(data['errors'])}</span></div>"
            ),
            (
                '    <div class="summary-card"><span class="summary-label">'
                "Warnings</span>"
                f'<span class="summary-value">{_html(data["warnings"])}</span></div>'
            ),
        ]
        if profile_name is not None:
            lines.append(
                '    <div class="summary-card"><span class="summary-label">'
                "Profile</span>"
                f'<span class="summary-value">{_html(profile_name)}</span></div>'
            )
        lines.extend(
            [
                "  </div>",
                '  <div class="note-card">',
                f"    <p>{_html(self.SANITIZATION_NOTE)}</p>",
                f"    <p>{_html(self.PRIVACY_NOTE)}</p>",
                "  </div>",
            ]
        )
        for section in sections:
            lines.extend(self._render_section(section))
        lines.extend(["</main>", "</body>", "</html>", ""])
        return "\n".join(lines)

    def _render_section(self, section: object) -> list[str]:
        section_data: Mapping[str, object] = (
            section if isinstance(section, Mapping) else {}
        )
        title = section_data.get("title", "")
        items = section_data.get("items", [])
        lines = [
            "  <section>",
            f"    <h2>{_html(title)}</h2>",
            '    <div class="table-wrap">',
            "    <table>",
            "      <thead><tr><th>Status</th><th>Name</th><th>Message</th>"
            "<th>Detail</th></tr></thead>",
            "      <tbody>",
        ]
        if isinstance(items, list):
            for item in items:
                lines.append(self._render_item(item))
        lines.extend(["      </tbody>", "    </table>", "    </div>", "  </section>"])
        return lines

    def _render_item(self, item: object) -> str:
        item_data = item if isinstance(item, Mapping) else {}
        status = str(item_data.get("status", "info"))
        name = str(item_data.get("name", ""))
        message = str(item_data.get("message", ""))
        detail = item_data.get("detail") if self.include_details else None
        detail_text = None if detail is None else str(detail)
        return (
            "        <tr>"
            f'<td><span class="status status-{_html_attr(status)}">'
            f"{_html(_status_label(status))}</span></td>"
            f"<td>{_html(name)}</td>"
            f"<td>{_render_message(name, message)}</td>"
            f"<td>{_render_detail(detail_text)}</td>"
            "</tr>"
        )


def _html(value: object) -> str:
    return escape(str(value), quote=True)


def _html_attr(value: object) -> str:
    text = str(value)
    safe = "".join(char for char in text if char.isalnum() or char in {"-", "_"})
    return escape(safe or "info", quote=True)


def _status_label(status: str) -> str:
    if status == "warning":
        return "WARNING"
    return status.upper()


def _find_profile_name(sections: object) -> str | None:
    if not isinstance(sections, list):
        return None
    for section in sections:
        if not isinstance(section, Mapping) or section.get("title") != "Profile":
            continue
        items = section.get("items")
        if not isinstance(items, list):
            return None
        for item in items:
            if not isinstance(item, Mapping) or item.get("name") != "Profile":
                continue
            message = str(item.get("message", "")).strip()
            return message or None
    return None


def _render_message(name: str, message: str) -> str:
    if name in PATH_VALUE_NAMES and message not in {"", "not set", "none"}:
        return f'<code class="value-code">{_html(message)}</code>'
    return _html(message)


def _render_detail(detail_text: str | None) -> str:
    if detail_text is None or detail_text == "":
        return '<span class="empty-detail" aria-label="No detail">&mdash;</span>'
    return f"<code>{_html(detail_text)}</code>"
