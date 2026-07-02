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
VBOX_DEFAULTS = [
    Path(r"C:\Program Files\Oracle\VirtualBox\VBoxManage.exe"),
    Path(r"C:\Program Files (x86)\Oracle\VirtualBox\VBoxManage.exe"),
]
VMRUN_DEFAULTS = [
    Path(r"C:\Program Files (x86)\VMware\VMware Workstation\vmrun.exe"),
    Path(r"C:\Program Files\VMware\VMware Workstation\vmrun.exe"),
]


def _run(command: list[str], timeout: int = 30) -> dict[str, object]:
    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        return {
            "command": command,
            "returncode": proc.returncode,
            "stdout": (stdout or "").strip(),
            "stderr": (stderr or "").strip(),
        }
    except subprocess.TimeoutExpired:
        if proc.pid:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                text=True,
                check=False,
            )
        stdout, stderr = proc.communicate(timeout=5)
        return {
            "command": command,
            "returncode": -9,
            "stdout": (stdout or "").strip(),
            "stderr": (stderr or "").strip(),
            "timeout_s": timeout,
        }


def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _command_path(name: str) -> str | None:
    return shutil.which(name)


def _known_tool(name: str, defaults: list[Path]) -> dict[str, object]:
    path = _command_path(name)
    candidates = [str(path)] if path else []
    for default in defaults:
        if default.is_file() and str(default) not in candidates:
            candidates.append(str(default))
    return {"path": candidates[0] if candidates else None, "candidates": candidates}


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


def _powershell_command(name: str) -> dict[str, object]:
    return _powershell_json(
        f"Get-Command {name} -ErrorAction SilentlyContinue "
        "| Select-Object Name,CommandType,Source | ConvertTo-Json -Depth 3"
    )


def _dism_hyperv_feature() -> dict[str, object]:
    dism = _command_path("dism.exe") or r"C:\Windows\System32\dism.exe"
    result = _run(
        [dism, "/Online", "/Get-FeatureInfo", "/FeatureName:Microsoft-Hyper-V-All"],
        timeout=60,
    )
    state = None
    restart_required = None
    for raw_line in str(result["stdout"]).splitlines():
        line = raw_line.strip()
        if line.startswith("Status :"):
            state = line.split(":", 1)[1].strip()
        elif line.startswith("Neustart erforderlich :") or line.startswith("Restart Required :"):
            restart_required = line.split(":", 1)[1].strip()
    return {
        "checked": result["returncode"] == 0,
        "state": state,
        "restart_required": restart_required,
        "raw": result,
    }


def main() -> int:
    hyperv_cmd = _powershell_command("Get-VM")
    vmrun = _known_tool("vmrun", VMRUN_DEFAULTS)
    vboxmanage = _known_tool("VBoxManage", VBOX_DEFAULTS)
    hyperv_feature = _powershell_json(
        "Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All "
        "| Select-Object FeatureName,State | ConvertTo-Json -Depth 3"
    )
    hyperv_feature_dism = _dism_hyperv_feature()
    hyperv_vms = _powershell_json(
        "if (Get-Command Get-VM -ErrorAction SilentlyContinue) "
        "{ Get-VM | Select-Object Name,State,Generation | ConvertTo-Json -Depth 3 } "
        "else { 'Get-VM missing' }"
    )

    blockers = []
    if not _is_admin():
        blockers.append("not-running-as-admin")
    hyperv_available = bool(hyperv_cmd.get("result"))
    if not hyperv_available and not vmrun["path"] and not vboxmanage["path"]:
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
        "hyperv_feature_dism": hyperv_feature_dism,
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
