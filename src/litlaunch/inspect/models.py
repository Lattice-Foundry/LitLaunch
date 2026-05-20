"""Diagnostics report data model."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from litlaunch.redaction import redact_sensitive_text
from litlaunch.version import __version__

SCHEMA_VERSION = 1


class DiagnosticStatus(str, Enum):
    """Diagnostic item status values."""

    OK = "ok"
    WARNING = "warning"
    ERROR = "error"
    INFO = "info"


@dataclass(frozen=True)
class DiagnosticItem:
    """One diagnostic finding."""

    name: str
    status: DiagnosticStatus
    message: str
    detail: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "message", self.message.strip())
        if not self.name:
            raise ValueError("diagnostic item name cannot be empty.")
        if not self.message:
            raise ValueError("diagnostic item message cannot be empty.")
        if self.detail is not None:
            object.__setattr__(self, "detail", str(self.detail))

    def to_dict(self) -> dict[str, object]:
        """Return a sanitized stable dictionary representation."""

        data: dict[str, object] = {
            "name": redact_sensitive_text(self.name),
            "status": self.status.value,
            "message": redact_sensitive_text(self.message),
            "detail": None,
        }
        if self.detail is not None:
            data["detail"] = redact_sensitive_text(self.detail)
        return data


@dataclass(frozen=True)
class DiagnosticSection:
    """A titled group of diagnostic items."""

    title: str
    items: tuple[DiagnosticItem, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "title", self.title.strip())
        object.__setattr__(self, "items", tuple(self.items))
        if not self.title:
            raise ValueError("diagnostic section title cannot be empty.")

    def to_dict(self) -> dict[str, object]:
        """Return a sanitized stable dictionary representation."""

        return {
            "title": redact_sensitive_text(self.title),
            "items": [item.to_dict() for item in self.items],
        }


@dataclass(frozen=True)
class DiagnosticsReport:
    """Complete structured diagnostics report."""

    title: str
    sections: tuple[DiagnosticSection, ...] = ()
    generated_at_utc: str = field(default_factory=lambda: current_utc_timestamp())
    ok: bool = field(init=False)
    warnings: int = field(init=False)
    errors: int = field(init=False)

    def __post_init__(self) -> None:
        title = self.title.strip()
        sections = tuple(self.sections)
        generated_at = str(self.generated_at_utc).strip()
        warnings = _count_status(sections, DiagnosticStatus.WARNING)
        errors = _count_status(sections, DiagnosticStatus.ERROR)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "sections", sections)
        object.__setattr__(self, "generated_at_utc", generated_at)
        object.__setattr__(self, "warnings", warnings)
        object.__setattr__(self, "errors", errors)
        object.__setattr__(self, "ok", errors == 0)
        if not title:
            raise ValueError("diagnostics report title cannot be empty.")
        if not generated_at:
            raise ValueError("diagnostics report timestamp cannot be empty.")

    def to_dict(self) -> dict[str, object]:
        """Return a sanitized stable dictionary representation."""

        return {
            "schema_version": SCHEMA_VERSION,
            "generated_by": "litlaunch",
            "litlaunch_version": __version__,
            "generated_at_utc": redact_sensitive_text(self.generated_at_utc),
            "title": redact_sensitive_text(self.title),
            "ok": self.ok,
            "warnings": self.warnings,
            "errors": self.errors,
            "sections": [section.to_dict() for section in self.sections],
        }


def current_utc_timestamp() -> str:
    """Return a compact UTC ISO timestamp for diagnostics metadata."""

    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _count_status(
    sections: tuple[DiagnosticSection, ...],
    status: DiagnosticStatus,
) -> int:
    return sum(
        1 for section in sections for item in section.items if item.status == status
    )
