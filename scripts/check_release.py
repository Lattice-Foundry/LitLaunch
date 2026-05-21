"""Build and inspect LitLaunch release artifacts."""

from __future__ import annotations

import argparse
import ast
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import venv
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from email.parser import Parser
from pathlib import Path, PurePosixPath

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = PROJECT_ROOT / "dist"
VERSION_FILE = PROJECT_ROOT / "src" / "litlaunch" / "version.py"

FORBIDDEN_ARCHIVE_COMPONENTS = frozenset(
    {
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".claude",
        ".git",
        ".venv",
    }
)
FORBIDDEN_ARCHIVE_SUFFIXES = (".pyc", ".pyo")
MALFORMED_VERSION_FRAGMENT_PATTERN = re.compile(r"^\d+(?:\.\d+){1,3}`?$")
FORBIDDEN_REPO_CACHE_DIRS = frozenset({"__pycache__"})
FORBIDDEN_REPO_BYTECODE_SUFFIXES = (".pyc", ".pyo")
IGNORED_REPO_TREE_DIRS = frozenset(
    {".git", ".venv", ".pytest_cache", ".ruff_cache", "dist"}
)
REPO_ROOT_TEMP_DIR_PATTERN = re.compile(r"^litlaunch-test-")
STALE_REPO_ROOT_GENERATED_NAMES = frozenset(
    {
        "litlaunch-report.html",
        "litlaunch-support-bundle.zip",
    }
)


@dataclass(frozen=True)
class ReleaseArtifacts:
    """Built release artifact paths."""

    wheel: Path
    sdist: Path


def build_parser() -> argparse.ArgumentParser:
    """Build the release hygiene argument parser."""

    parser = argparse.ArgumentParser(
        description=(
            "Build LitLaunch release artifacts, validate metadata, inspect archive "
            "contents, and run installed-wheel smoke checks."
        ),
        epilog="Requires dev tooling from .[dev], including build and twine.",
    )
    parser.add_argument(
        "--keep-dist",
        action="store_true",
        help="Do not remove the existing dist directory before building.",
    )
    parser.add_argument(
        "--skip-smoke",
        action="store_true",
        help="Skip temporary-venv installed-wheel smoke checks.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run release hygiene checks."""

    args = build_parser().parse_args(argv)
    version = read_project_version()
    ensure_no_suspicious_repo_root_artifacts()

    if not args.keep_dist:
        clean_dist()

    run_command((sys.executable, "-m", "build"))
    artifacts = find_release_artifacts(version)
    run_twine_check(artifacts)
    inspect_wheel(artifacts.wheel, version)
    inspect_sdist(artifacts.sdist, version)

    if not args.skip_smoke:
        run_installed_wheel_smoke(artifacts.wheel, version)

    print(f"Release hygiene checks passed for litlaunch {version}.")
    return 0


def read_project_version(version_file: Path = VERSION_FILE) -> str:
    """Read the package version without importing LitLaunch."""

    module = ast.parse(version_file.read_text(encoding="utf-8"))
    for node in module.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "__version__"
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            return node.value.value
    raise RuntimeError(f"Could not find __version__ in {version_file}")


def clean_dist(dist_dir: Path = DIST_DIR) -> None:
    """Safely remove the project dist directory."""

    resolved_dist = dist_dir.resolve()
    expected_dist = (PROJECT_ROOT / "dist").resolve()
    if resolved_dist != expected_dist:
        raise RuntimeError(f"Refusing to clean unexpected dist path: {dist_dir}")
    if dist_dir.exists():
        shutil.rmtree(dist_dir)


def run_command(
    command: Sequence[str],
    *,
    cwd: Path | None = PROJECT_ROOT,
    env: dict[str, str] | None = None,
    allowed_return_codes: tuple[int, ...] = (0,),
) -> None:
    """Run a command with shell-free argument passing."""

    printable = " ".join(str(part) for part in command)
    print(f"+ {printable}")
    result = subprocess.run(tuple(str(part) for part in command), cwd=cwd, env=env)
    if result.returncode not in allowed_return_codes:
        raise subprocess.CalledProcessError(result.returncode, result.args)


def find_release_artifacts(
    version: str,
    dist_dir: Path = DIST_DIR,
) -> ReleaseArtifacts:
    """Find exactly one wheel and one sdist for the requested version."""

    wheels = sorted(dist_dir.glob(f"litlaunch-{version}-*.whl"))
    sdists = sorted(dist_dir.glob(f"litlaunch-{version}.tar.gz"))
    if len(wheels) != 1:
        raise RuntimeError(f"Expected one wheel for {version}, found {len(wheels)}")
    if len(sdists) != 1:
        raise RuntimeError(f"Expected one sdist for {version}, found {len(sdists)}")
    return ReleaseArtifacts(wheel=wheels[0], sdist=sdists[0])


def run_twine_check(artifacts: ReleaseArtifacts) -> None:
    """Run twine metadata and README validation."""

    run_command(
        (
            sys.executable,
            "-m",
            "twine",
            "check",
            str(artifacts.sdist),
            str(artifacts.wheel),
        )
    )


def inspect_wheel(wheel_path: Path, version: str) -> None:
    """Inspect wheel contents and metadata without extraction."""

    with zipfile.ZipFile(wheel_path) as archive:
        names = tuple(archive.namelist())
        ensure_no_forbidden_archive_entries(names)
        require_archive_entry(
            names, "litlaunch package", lambda name: name == "litlaunch/__init__.py"
        )
        require_archive_entry(
            names, "py.typed marker", lambda name: name == "litlaunch/py.typed"
        )
        require_archive_entry(
            names, "METADATA", lambda name: name.endswith(".dist-info/METADATA")
        )
        require_archive_entry(
            names, "WHEEL", lambda name: name.endswith(".dist-info/WHEEL")
        )
        require_archive_entry(
            names,
            "console entry points",
            lambda name: name.endswith(".dist-info/entry_points.txt"),
        )
        require_archive_entry(names, "LICENSE", _is_license_entry)

        metadata_name = next(
            name for name in names if name.endswith(".dist-info/METADATA")
        )
        metadata = Parser().parsestr(archive.read(metadata_name).decode("utf-8"))
        if metadata.get("Version") != version:
            found_version = metadata.get("Version")
            raise RuntimeError(
                f"Wheel metadata version mismatch: {found_version} != {version}"
            )
        license_value = metadata.get("License-Expression") or metadata.get("License")
        if license_value != "MIT":
            raise RuntimeError(f"Unexpected wheel license metadata: {license_value!r}")
        if metadata.get("Description-Content-Type") != "text/markdown":
            raise RuntimeError("Wheel long description is not marked as Markdown.")
        if "LitLaunch" not in metadata.get_payload():
            raise RuntimeError(
                "Wheel long description does not contain README content."
            )

        entry_points_name = next(
            name for name in names if name.endswith(".dist-info/entry_points.txt")
        )
        entry_points = archive.read(entry_points_name).decode("utf-8")
        if "litlaunch = litlaunch.cli:main" not in entry_points:
            raise RuntimeError("Wheel is missing the litlaunch console script entry.")


def inspect_sdist(sdist_path: Path, version: str) -> None:
    """Inspect sdist contents without extraction."""

    with tarfile.open(sdist_path, "r:gz") as archive:
        names = tuple(member.name for member in archive.getmembers())

    inspect_sdist_names(names, version)


def inspect_sdist_names(names: Sequence[str], version: str) -> None:
    """Inspect sdist member names without reading an archive file."""

    ensure_no_forbidden_archive_entries(names)
    prefix = f"litlaunch-{version}/"
    required_suffixes = (
        "pyproject.toml",
        "README.md",
        "LICENSE",
        "src/litlaunch/__init__.py",
        "src/litlaunch/py.typed",
    )
    for suffix in required_suffixes:
        expected = f"{prefix}{suffix}"
        require_archive_entry(
            names, expected, lambda name, value=expected: name == value
        )
    require_archive_entry(
        names,
        "public docs",
        lambda name: name == f"{prefix}docs/overview.md",
    )
    internal_prefix = f"{prefix}docs/internal/"
    if any(name.startswith(internal_prefix) for name in names):
        raise RuntimeError("Internal integration docs must not be included in sdist.")


def find_suspicious_repo_root_artifacts(
    root: Path = PROJECT_ROOT,
) -> tuple[Path, ...]:
    """Return suspicious root-level files that should not ship accidentally."""

    suspicious: list[Path] = []
    for path in root.iterdir():
        if not path.is_file():
            continue
        name = path.name
        if "`" in name:
            suspicious.append(path)
            continue
        if path.stat().st_size == 0 and _looks_like_accidental_root_artifact(name):
            suspicious.append(path)
    return tuple(suspicious)


def ensure_no_suspicious_repo_root_artifacts(root: Path = PROJECT_ROOT) -> None:
    """Raise if the repo root contains obvious accidental shell artifacts."""

    suspicious = find_suspicious_repo_root_artifacts(root)
    if suspicious:
        joined = ", ".join(path.name for path in suspicious)
        raise RuntimeError(f"Suspicious repo-root artifacts found: {joined}")

    forbidden = find_forbidden_repo_tree_artifacts(root)
    if forbidden:
        joined = ", ".join(_display_path(path, root) for path in forbidden)
        raise RuntimeError(f"Forbidden repo-tree artifacts found: {joined}")


def find_forbidden_repo_tree_artifacts(root: Path = PROJECT_ROOT) -> tuple[Path, ...]:
    """Return generated cache/temp artifacts that should not remain in the repo."""

    forbidden: list[Path] = []
    ignored = {root / name for name in IGNORED_REPO_TREE_DIRS}
    for path in root.rglob("*"):
        if _is_under_ignored_dir(path, ignored):
            continue
        if path.is_dir():
            if path.name in FORBIDDEN_REPO_CACHE_DIRS or (
                path.parent == root and REPO_ROOT_TEMP_DIR_PATTERN.match(path.name)
            ):
                forbidden.append(path)
            continue
        if path.suffix in FORBIDDEN_REPO_BYTECODE_SUFFIXES or (
            path.parent == root and path.name in STALE_REPO_ROOT_GENERATED_NAMES
        ):
            forbidden.append(path)
    return tuple(sorted(forbidden))


def find_forbidden_archive_entries(names: Sequence[str]) -> tuple[str, ...]:
    """Return archive entries that should never appear in release artifacts."""

    forbidden: list[str] = []
    for raw_name in names:
        name = raw_name.replace("\\", "/")
        path = PurePosixPath(name)
        if name.startswith("/") or ".." in path.parts:
            forbidden.append(raw_name)
            continue
        if any(part in FORBIDDEN_ARCHIVE_COMPONENTS for part in path.parts):
            forbidden.append(raw_name)
            continue
        if path.suffix in FORBIDDEN_ARCHIVE_SUFFIXES:
            forbidden.append(raw_name)
    return tuple(forbidden)


def ensure_no_forbidden_archive_entries(names: Sequence[str]) -> None:
    """Raise if release artifacts contain junk or unsafe paths."""

    forbidden = find_forbidden_archive_entries(names)
    if forbidden:
        joined = ", ".join(forbidden)
        raise RuntimeError(f"Forbidden archive entries found: {joined}")


def require_archive_entry(
    names: Sequence[str],
    description: str,
    predicate: Callable[[str], bool],
) -> None:
    """Require at least one archive entry matching a predicate."""

    if not any(predicate(name) for name in names):
        raise RuntimeError(f"Missing required archive entry: {description}")


def _looks_like_accidental_root_artifact(name: str) -> bool:
    return (
        MALFORMED_VERSION_FRAGMENT_PATTERN.fullmatch(name) is not None
        or name in {"'", '"'}
        or name.endswith(("`", "'", '"'))
    )


def _is_under_ignored_dir(path: Path, ignored: set[Path]) -> bool:
    return any(
        path == ignored_dir or ignored_dir in path.parents for ignored_dir in ignored
    )


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def run_installed_wheel_smoke(wheel_path: Path, version: str) -> None:
    """Install the built wheel into a temp venv and run basic smoke checks."""

    with tempfile.TemporaryDirectory(prefix="litlaunch-release-") as temp_dir:
        venv_dir = Path(temp_dir) / "venv"
        venv.EnvBuilder(with_pip=True).create(venv_dir)
        python = _venv_python(venv_dir)
        litlaunch = _venv_script(venv_dir, "litlaunch")
        env = _smoke_env()

        run_command(
            (str(python), "-m", "pip", "install", str(wheel_path)), cwd=None, env=env
        )
        run_command(
            (
                str(python),
                "-c",
                (
                    "import litlaunch; "
                    f"assert litlaunch.__version__ == {version!r}; "
                    "print(litlaunch.__version__)"
                ),
            ),
            cwd=Path(temp_dir),
            env=env,
        )
        run_command((str(litlaunch), "version"), cwd=Path(temp_dir), env=env)
        run_command(
            (str(litlaunch), "platform", "--no-color"), cwd=Path(temp_dir), env=env
        )
        run_command(
            (str(litlaunch), "browsers", "--no-color"), cwd=Path(temp_dir), env=env
        )
        run_command((str(litlaunch), "help"), cwd=Path(temp_dir), env=env)
        run_command(
            (str(litlaunch), "inspect", "--no-color"),
            cwd=Path(temp_dir),
            env=env,
            allowed_return_codes=(0, 1),
        )
        run_command(
            (str(litlaunch), "report", "--no-color"),
            cwd=Path(temp_dir),
            env=env,
            allowed_return_codes=(0, 1),
        )
        example_app = PROJECT_ROOT / "examples" / "minimal_app" / "app.py"
        if example_app.is_file():
            run_command(
                (str(litlaunch), "inspect", str(example_app), "--no-color"),
                cwd=Path(temp_dir),
                env=env,
                allowed_return_codes=(0, 1),
            )
            run_command(
                (str(litlaunch), "command", str(example_app), "--no-color"),
                cwd=Path(temp_dir),
                env=env,
            )


def _venv_python(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _venv_script(venv_dir: Path, name: str) -> Path:
    if os.name == "nt":
        script = venv_dir / "Scripts" / f"{name}.exe"
        if script.is_file():
            return script
        return venv_dir / "Scripts" / name
    return venv_dir / "bin" / name


def _smoke_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    return env


def _is_license_entry(name: str) -> bool:
    path = PurePosixPath(name)
    return path.name == "LICENSE" and (
        ".dist-info" in path.parent.name or "licenses" in path.parts
    )


if __name__ == "__main__":
    raise SystemExit(main())
