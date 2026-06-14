"""Windows shortcut helpers shared by launch and shortcut generation."""

from __future__ import annotations

import hashlib
import subprocess
import tempfile
from pathlib import Path

from litlaunch.exceptions import ConfigurationError


def write_windows_shortcut(
    *,
    shortcut_path: Path,
    target_path: str,
    arguments: str,
    working_directory: Path,
    icon_path: Path | None = None,
    app_user_model_id: str | None = None,
) -> None:
    """Create a Windows .lnk shortcut through the supported Shell COM API."""

    script = (
        "param(\n"
        "  [string]$ShortcutPath,\n"
        "  [string]$TargetPath,\n"
        "  [string]$ShortcutArguments,\n"
        "  [string]$WorkingDirectory,\n"
        "  [string]$IconPath,\n"
        "  [string]$AppUserModelId\n"
        ")\n"
        "$ErrorActionPreference = 'Stop'\n"
        "$shell = New-Object -ComObject WScript.Shell\n"
        "$shortcut = $shell.CreateShortcut($ShortcutPath)\n"
        "$shortcut.TargetPath = $TargetPath\n"
        "$shortcut.Arguments = $ShortcutArguments\n"
        "$shortcut.WorkingDirectory = $WorkingDirectory\n"
        "if ($IconPath) { $shortcut.IconLocation = $IconPath }\n"
        "$shortcut.Save()\n"
        "[System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($shortcut) "
        "| Out-Null\n"
        "[System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($shell) "
        "| Out-Null\n"
        "$shortcut = $null\n"
        "$shell = $null\n"
        "[System.GC]::Collect()\n"
        "[System.GC]::WaitForPendingFinalizers()\n"
        "if ($AppUserModelId) {\n"
        'Add-Type -TypeDefinition @"\n'
        "using System;\n"
        "using System.Runtime.InteropServices;\n"
        "\n"
        "[ComImport]\n"
        '[Guid("00021401-0000-0000-C000-000000000046")]\n'
        "public class ShellLink {}\n"
        "\n"
        "[ComImport]\n"
        "[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]\n"
        '[Guid("0000010b-0000-0000-C000-000000000046")]\n'
        "public interface IPersistFile\n"
        "{\n"
        "    void GetClassID(out Guid pClassID);\n"
        "    void IsDirty();\n"
        "    void Load([MarshalAs(UnmanagedType.LPWStr)] string pszFileName, "
        "uint dwMode);\n"
        "    void Save([MarshalAs(UnmanagedType.LPWStr)] string pszFileName, "
        "bool fRemember);\n"
        "    void SaveCompleted([MarshalAs(UnmanagedType.LPWStr)] string "
        "pszFileName);\n"
        "    void GetCurFile([MarshalAs(UnmanagedType.LPWStr)] out string "
        "ppszFileName);\n"
        "}\n"
        "\n"
        "[ComImport]\n"
        "[InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]\n"
        '[Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99")]\n'
        "public interface IPropertyStore\n"
        "{\n"
        "    void GetCount(out uint cProps);\n"
        "    void GetAt(uint iProp, out PROPERTYKEY pkey);\n"
        "    void GetValue(ref PROPERTYKEY key, out PROPVARIANT pv);\n"
        "    void SetValue(ref PROPERTYKEY key, ref PROPVARIANT pv);\n"
        "    void Commit();\n"
        "}\n"
        "\n"
        "[StructLayout(LayoutKind.Sequential, Pack = 4)]\n"
        "public struct PROPERTYKEY\n"
        "{\n"
        "    public Guid fmtid;\n"
        "    public uint pid;\n"
        "}\n"
        "\n"
        "[StructLayout(LayoutKind.Sequential)]\n"
        "public struct PROPVARIANT\n"
        "{\n"
        "    public ushort vt;\n"
        "    public ushort wReserved1;\n"
        "    public ushort wReserved2;\n"
        "    public ushort wReserved3;\n"
        "    public IntPtr p;\n"
        "}\n"
        "\n"
        "public static class LitLaunchShortcutProperties\n"
        "{\n"
        "    private const ushort VT_LPWSTR = 31;\n"
        "    private const uint STGM_READWRITE = 2;\n"
        "    private static readonly Guid AppUserModelFmtid = new Guid("
        '"9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3");\n'
        "\n"
        '    [DllImport("Ole32.dll")]\n'
        "    private static extern int PropVariantClear(ref PROPVARIANT pvar);\n"
        "\n"
        "    public static void SetAppUserModelId(string shortcutPath, "
        "string appUserModelId)\n"
        "    {\n"
        "        var link = new ShellLink();\n"
        "        var file = (IPersistFile)link;\n"
        "        file.Load(shortcutPath, STGM_READWRITE);\n"
        "        var store = (IPropertyStore)link;\n"
        "        var key = new PROPERTYKEY { fmtid = AppUserModelFmtid, pid = 5 };\n"
        "        var value = FromString(appUserModelId);\n"
        "        try\n"
        "        {\n"
        "            store.SetValue(ref key, ref value);\n"
        "            store.Commit();\n"
        "            file.Save(shortcutPath, true);\n"
        "        }\n"
        "        finally\n"
        "        {\n"
        "            PropVariantClear(ref value);\n"
        "            Marshal.FinalReleaseComObject(store);\n"
        "            Marshal.FinalReleaseComObject(file);\n"
        "            Marshal.FinalReleaseComObject(link);\n"
        "        }\n"
        "    }\n"
        "\n"
        "    private static PROPVARIANT FromString(string value)\n"
        "    {\n"
        "        return new PROPVARIANT\n"
        "        {\n"
        "            vt = VT_LPWSTR,\n"
        "            p = Marshal.StringToCoTaskMemUni(value),\n"
        "        };\n"
        "    }\n"
        "}\n"
        '"@\n'
        "[LitLaunchShortcutProperties]::SetAppUserModelId($ShortcutPath, "
        "$AppUserModelId)\n"
        "}\n"
    )
    shortcut_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="litlaunch-shortcut-") as temp_dir:
        script_path = Path(temp_dir) / "create-shortcut.ps1"
        script_path.write_text(script, encoding="utf-8")
        command = (
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            str(shortcut_path),
            target_path,
            arguments,
            str(working_directory),
            str(icon_path) if icon_path is not None else "",
            app_user_model_id or "",
        )
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            detail = getattr(exc, "stderr", "") or str(exc)
            raise ConfigurationError(
                f"Could not create Windows shortcut: {detail}"
            ) from exc


def join_windows_arguments(parts: tuple[str, ...]) -> str:
    """Return a Windows shortcut argument string."""

    return " ".join(_quote_windows_argument(part) for part in parts)


def windows_app_user_model_id(root: Path, title: str, app_icon: Path) -> str:
    """Return a stable app identity for Windows webapp icon presentation."""

    label = _app_user_model_label(title or root.name or "app")
    seed = "|".join((str(root.resolve()), title.strip(), str(app_icon.resolve())))
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
    value = f"LatticeFoundry.LitLaunch.{label}.{digest}"
    return value[:128].rstrip(".")


def _quote_windows_argument(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _app_user_model_label(value: str) -> str:
    parts: list[str] = []
    current: list[str] = []
    for char in value.strip():
        if char.isalnum():
            current.append(char)
        elif current:
            parts.append("".join(current))
            current = []
    if current:
        parts.append("".join(current))
    return ".".join(parts)[:64].strip(".") or "App"
