from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "tests" / "qa_artifacts" / "installed_app_gui_readiness.json"
INSTALLER = ROOT / "dist" / "pb_studio_setup_v0.5.0.exe"
PAYLOAD = ROOT / "dist" / "pb_studio_setup_v0.5.0.nsisbin"
NSI = ROOT / "installer" / "pb_studio.nsi"
INSTALLED_EXE = Path(os.environ.get("PB_INSTALLED_EXE", r"C:\Program Files\PB Studio\pb_studio.exe"))
INSTALL_CANDIDATES = [
    INSTALLED_EXE,
    Path(r"C:\Program Files\PB Studio\pb_studio.exe"),
    Path(r"C:\Program Files (x86)\PB Studio\pb_studio.exe"),
    Path(os.environ.get("LOCALAPPDATA", "")) / "PB Studio" / "pb_studio.exe",
]


def _run(command: list[str], timeout: int = 30) -> dict[str, object]:
    proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    return {
        "command": command,
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _powershell() -> str | None:
    return shutil.which("pwsh") or shutil.which("powershell")


def _authenticode(path: Path) -> dict[str, object]:
    shell = _powershell()
    if not shell:
        return {"checked": False, "status": "powershell-missing", "signed": False}
    if not path.exists():
        return {"checked": False, "status": "missing", "signed": False}
    ps = (
        f"(Get-AuthenticodeSignature -LiteralPath {json.dumps(str(path))}) | "
        "Select-Object Status,StatusMessage,SignerCertificate | ConvertTo-Json -Depth 4"
    )
    result = _run([shell, "-NoProfile", "-Command", ps])
    if result["returncode"] != 0 or not result["stdout"]:
        return {"checked": False, "status": "command-failed", "signed": False, "raw": result}
    parsed = json.loads(str(result["stdout"]))
    status = str(parsed.get("Status"))
    return {
        "checked": True,
        "status": status,
        "status_message": parsed.get("StatusMessage"),
        "signed": status == "Valid" or status == "0",
        "signer_certificate": parsed.get("SignerCertificate"),
        "raw": result,
    }


def _nsi_install_policy() -> dict[str, object]:
    text = NSI.read_text(encoding="utf-8", errors="replace") if NSI.exists() else ""
    return {
        "path": str(NSI),
        "exists": NSI.exists(),
        "requests_admin": "RequestExecutionLevel admin" in text,
        "program_files_default": "$PROGRAMFILES64\\PB Studio" in text,
        "writes_hklm_uninstall_key": "WriteRegStr   HKLM" in text,
    }


def _registry_uninstall_entries() -> dict[str, object]:
    shell = _powershell()
    if not shell:
        return {"checked": False, "error": "powershell-missing", "entries": []}
    ps = r"""
$roots = @(
  'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
  'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
  'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*'
)
$items = foreach ($root in $roots) {
  Get-ItemProperty -Path $root -ErrorAction SilentlyContinue |
    Where-Object {
      $_.DisplayName -like '*PB Studio*' -or
      $_.InstallLocation -like '*PB Studio*' -or
      $_.DisplayIcon -like '*pb_studio.exe*'
    } |
    Select-Object PSPath,DisplayName,DisplayVersion,Publisher,InstallLocation,DisplayIcon,UninstallString
}
$items | ConvertTo-Json -Depth 4
"""
    result = _run([shell, "-NoProfile", "-Command", ps])
    entries: list[object] = []
    if result["stdout"]:
        parsed = json.loads(str(result["stdout"]))
        entries = parsed if isinstance(parsed, list) else [parsed]
    return {"checked": result["returncode"] == 0, "entries": entries, "raw": result}


def _installed_candidates() -> list[dict[str, object]]:
    unique: list[Path] = []
    for candidate in INSTALL_CANDIDATES:
        if candidate and str(candidate) and candidate not in unique:
            unique.append(candidate)
    return [_file_info(path) for path in unique]


def _file_info(path: Path) -> dict[str, object]:
    return {
        "path": str(path),
        "exists": path.exists(),
        "is_file": path.is_file(),
        "size_bytes": path.stat().st_size if path.is_file() else 0,
    }


def main() -> int:
    nsi_policy = _nsi_install_policy()
    installer_signature = _authenticode(INSTALLER)
    installed_signature = _authenticode(INSTALLED_EXE)
    registry_entries = _registry_uninstall_entries()
    installed_candidates = _installed_candidates()
    installed_candidate_found = any(candidate["is_file"] for candidate in installed_candidates)
    registry_installed = bool(registry_entries.get("entries"))

    blockers = []
    if not INSTALLER.is_file():
        blockers.append("installer-stub-missing")
    if not PAYLOAD.is_file():
        blockers.append("nsisbi-payload-missing")
    if PAYLOAD.is_file() and PAYLOAD.stat().st_size <= 1024**3:
        blockers.append("nsisbi-payload-too-small")
    if nsi_policy["requests_admin"] and not _is_admin():
        blockers.append("installer-requires-admin-current-process-not-admin")
    if not installed_candidate_found:
        blockers.append("installed-exe-missing")
    if not registry_installed:
        blockers.append("installed-app-registry-entry-missing")
    if not installer_signature["signed"]:
        blockers.append("installer-not-signed")

    result = {
        "status": "pass",
        "installed_app_gui_ready": not blockers,
        "current_process_is_admin": _is_admin(),
        "installer": _file_info(INSTALLER),
        "payload": _file_info(PAYLOAD),
        "installed_exe": _file_info(INSTALLED_EXE),
        "installed_exe_candidates": installed_candidates,
        "installed_app_registry_entries": registry_entries,
        "nsi_install_policy": nsi_policy,
        "installer_authenticode": installer_signature,
        "installed_exe_authenticode": installed_signature,
        "blockers": blockers,
        "note": (
            "This preflight does not install PB Studio and does not run the "
            "installed-app GUI workflow. It cannot clear GUI-001."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
