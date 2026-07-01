from __future__ import annotations

import ctypes
import json
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "tests" / "qa_artifacts" / "clean_vm_readiness.json"
INSTALLER = ROOT / "dist" / "pb_studio_setup_v0.5.0.exe"
PAYLOAD = ROOT / "dist" / "pb_studio_setup_v0.5.0.nsisbin"


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


def _command_path(name: str) -> str | None:
    return shutil.which(name)


def _powershell_json(command: str) -> dict[str, object]:
    shell = _command_path("pwsh") or _command_path("powershell")
    if not shell:
        return {"checked": False, "error": "powershell-missing"}
    result = _run([shell, "-NoProfile", "-Command", command])
    payload: object = None
    if result["stdout"]:
        try:
            payload = json.loads(str(result["stdout"]))
        except json.JSONDecodeError:
            payload = result["stdout"]
    return {"checked": result["returncode"] == 0, "result": payload, "raw": result}


def main() -> int:
    hyperv_cmd = _command_path("Get-VM")
    vmrun = _command_path("vmrun")
    vboxmanage = _command_path("VBoxManage")
    hyperv_feature = _powershell_json(
        "Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All "
        "| Select-Object FeatureName,State | ConvertTo-Json -Depth 3"
    )
    hyperv_vms = _powershell_json(
        "if (Get-Command Get-VM -ErrorAction SilentlyContinue) "
        "{ Get-VM | Select-Object Name,State,Generation | ConvertTo-Json -Depth 3 } "
        "else { 'Get-VM missing' }"
    )

    blockers = []
    if not _is_admin():
        blockers.append("not-running-as-admin")
    if not hyperv_cmd and not vmrun and not vboxmanage:
        blockers.append("no-vm-control-tool-found")
    if not INSTALLER.is_file():
        blockers.append("installer-stub-missing")
    if not PAYLOAD.is_file():
        blockers.append("nsisbi-payload-missing")
    if PAYLOAD.is_file() and PAYLOAD.stat().st_size <= 1024**3:
        blockers.append("nsisbi-payload-too-small")

    result = {
        "status": "pass",
        "clean_vm_ready": not blockers,
        "is_admin": _is_admin(),
        "vm_tools": {
            "Get-VM": hyperv_cmd,
            "vmrun": vmrun,
            "VBoxManage": vboxmanage,
        },
        "hyperv_feature": hyperv_feature,
        "hyperv_vms": hyperv_vms,
        "installer": {
            "path": str(INSTALLER),
            "exists": INSTALLER.is_file(),
            "size_bytes": INSTALLER.stat().st_size if INSTALLER.is_file() else 0,
        },
        "payload": {
            "path": str(PAYLOAD),
            "exists": PAYLOAD.is_file(),
            "size_bytes": PAYLOAD.stat().st_size if PAYLOAD.is_file() else 0,
        },
        "blockers": blockers,
        "note": "This preflight does not run a clean VM install and cannot clear VM-001.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
