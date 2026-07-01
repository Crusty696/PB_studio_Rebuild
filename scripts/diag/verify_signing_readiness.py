from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "tests" / "qa_artifacts" / "signing_readiness.json"
INSTALLER = ROOT / "dist" / "pb_studio_setup_v0.5.0.exe"


def _run(command: list[str], timeout: int = 30) -> dict[str, object]:
    proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    return {
        "command": command,
        "returncode": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def _powershell() -> str | None:
    return shutil.which("pwsh") or shutil.which("powershell")


def _code_signing_certs(scope: str) -> dict[str, object]:
    shell = _powershell()
    if not shell:
        return {"checked": False, "error": "powershell-missing", "count": 0, "certs": []}
    ps = (
        f"Get-ChildItem Cert:\\{scope}\\My -CodeSigningCert | "
        "Select-Object Subject,Issuer,NotAfter,Thumbprint | ConvertTo-Json -Depth 3"
    )
    result = _run([shell, "-NoProfile", "-Command", ps])
    raw = result["stdout"]
    certs: list[object]
    if not raw:
        certs = []
    else:
        parsed = json.loads(str(raw))
        certs = parsed if isinstance(parsed, list) else [parsed]
    return {"checked": result["returncode"] == 0, "count": len(certs), "certs": certs, "raw": result}


def _authenticode(path: Path) -> dict[str, object]:
    shell = _powershell()
    if not shell:
        return {"checked": False, "status": "powershell-missing", "signed": False}
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


def main() -> int:
    signtool = shutil.which("signtool")
    current_user = _code_signing_certs("CurrentUser")
    local_machine = _code_signing_certs("LocalMachine")
    signature = _authenticode(INSTALLER) if INSTALLER.exists() else {
        "checked": False,
        "status": "installer-missing",
        "signed": False,
    }

    blockers = []
    if not signtool:
        blockers.append("signtool-missing")
    if current_user["count"] == 0 and local_machine["count"] == 0:
        blockers.append("code-signing-certificate-missing")
    if not signature["signed"]:
        blockers.append("installer-not-signed")

    result = {
        "status": "pass",
        "release_signing_ready": not blockers,
        "installer": str(INSTALLER),
        "installer_exists": INSTALLER.exists(),
        "signtool": signtool,
        "current_user_code_signing_certs": current_user,
        "local_machine_code_signing_certs": local_machine,
        "authenticode": signature,
        "blockers": blockers,
        "note": "This preflight does not create or import certificates and does not sign the installer.",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
