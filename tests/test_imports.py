import re
from importlib.metadata import version

import litlaunch
from litlaunch import (
    Architecture,
    BrowserCapability,
    BrowserChoice,
    BrowserKind,
    BrowserLauncher,
    BrowserLaunchResult,
    BrowserResolution,
    ConfigurationError,
    ConsoleMode,
    ConsoleRenderer,
    ConsoleTheme,
    DiagnosticCollector,
    DiagnosticItem,
    DiagnosticSection,
    DiagnosticsReport,
    DiagnosticStatus,
    HealthChecker,
    JSONDiagnosticsRenderer,
    LauncherConfig,
    LauncherRuntime,
    LaunchEvent,
    LaunchMode,
    LaunchResult,
    LaunchState,
    LitLaunchError,
    ManagedProcess,
    OperatingSystem,
    PlatformDetector,
    PlatformInfo,
    PortManager,
    ProcessManager,
    RuntimeSession,
    SanitizedBundleRenderer,
    ShutdownHook,
    ShutdownHookRegistry,
    ShutdownHookResult,
    ShutdownResult,
    StreamlitCommandBuilder,
    StreamlitLauncher,
    TextDiagnosticsRenderer,
    __version__,
)


def test_public_imports_are_available():
    assert LauncherConfig(app_path="app.py").mode == LaunchMode.BROWSER
    assert BrowserChoice.AUTO.value == "auto"
    assert BrowserKind.EDGE.value == "edge"
    assert BrowserCapability
    assert BrowserLaunchResult
    assert BrowserLauncher
    assert BrowserResolution
    assert ConsoleMode.NORMAL.value == "normal"
    assert ConsoleRenderer
    assert ConsoleTheme
    assert DiagnosticCollector
    assert DiagnosticItem
    assert DiagnosticSection
    assert DiagnosticStatus.OK.value == "ok"
    assert DiagnosticsReport
    assert HealthChecker
    assert JSONDiagnosticsRenderer
    assert issubclass(ConfigurationError, LitLaunchError)
    assert LaunchState.CREATED.value == "created"
    assert LaunchEvent
    assert LaunchResult
    assert OperatingSystem.WINDOWS.value == "windows"
    assert Architecture.X64.value == "x64"
    assert PlatformDetector
    assert PlatformInfo
    assert ManagedProcess
    assert PortManager
    assert ProcessManager
    assert RuntimeSession
    assert SanitizedBundleRenderer
    assert LauncherRuntime
    assert ShutdownHook
    assert ShutdownHookRegistry
    assert ShutdownHookResult
    assert ShutdownResult
    assert StreamlitCommandBuilder
    assert StreamlitLauncher
    assert TextDiagnosticsRenderer


def test_public_all_is_explicit():
    assert sorted(litlaunch.__all__) == [
        "Architecture",
        "BrowserCapability",
        "BrowserChoice",
        "BrowserKind",
        "BrowserLaunchResult",
        "BrowserLauncher",
        "BrowserResolution",
        "ConfigurationError",
        "ConsoleMode",
        "ConsoleRenderer",
        "ConsoleTheme",
        "DiagnosticCollector",
        "DiagnosticItem",
        "DiagnosticSection",
        "DiagnosticStatus",
        "DiagnosticsReport",
        "HealthChecker",
        "JSONDiagnosticsRenderer",
        "LaunchEvent",
        "LaunchMode",
        "LaunchResult",
        "LaunchState",
        "LauncherConfig",
        "LauncherRuntime",
        "LitLaunchError",
        "ManagedProcess",
        "OperatingSystem",
        "PlatformDetector",
        "PlatformInfo",
        "PortManager",
        "ProcessManager",
        "RuntimeSession",
        "SanitizedBundleRenderer",
        "ShutdownHook",
        "ShutdownHookRegistry",
        "ShutdownHookResult",
        "ShutdownResult",
        "StreamlitCommandBuilder",
        "StreamlitLauncher",
        "TextDiagnosticsRenderer",
        "__version__",
    ]
    assert not hasattr(litlaunch, "ConsoleColor")


def test_version_is_public_and_internal_baseline():
    assert litlaunch.__version__ == "0.13.0"
    assert __version__ == "0.13.0"
    assert re.fullmatch(r"\d+\.\d+\.\d+", litlaunch.__version__)


def test_package_metadata_version_matches_public_version():
    assert version("litlaunch") == litlaunch.__version__
