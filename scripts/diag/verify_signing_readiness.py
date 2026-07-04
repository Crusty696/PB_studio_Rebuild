from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "tests" / "qa_artifacts" / "signing_readiness.json"
INSTALLER = ROOT / "dist" / "pb_studio_setup_v0.5.0.exe"
WINDOWS_KITS_BIN = Path(r"C:\Program Files (x86)\Windows Kits\10\bin")
SIGNING_REQUIRED_FOR_PRIVATE_DISTRIBUTION = False


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


def _signtool() -> dict[str, object]:
    path_signtool = shutil.which("signtool")
    if path_signtool:
        return {"path": path_signtool, "source": "PATH", "candidates": [path_signtool]}

    candidates: list[str] = []
    if WINDOWS_KITS_BIN.is_dir():
        candidates = [str(path) for path in sorted(WINDOWS_KITS_BIN.glob(r"*\x64\signtool.exe"), reverse=True)]
        if not candidates:
            candidates = [str(path) for path in sorted(WINDOWS_KITS_BIN.rglob("signtool.exe"), reverse=True)]
    return {
        "path": candidates[0] if candidates else None,
        "source": "Windows Kits" if candidates else "missing",
        "candidates": candidates,
    }


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
        f"$sig = Get-AuthenticodeSignature -LiteralPath {json.dumps(str(path))}; "
        "[pscustomobject]@{"
        "Status=[string]$sig.Status;"
        "StatusMessage=$sig.StatusMessage;"
        "SignerSubject=if($sig.SignerCertificate){$sig.SignerCertificate.Subject}else{$null};"
        "SignerIssuer=if($sig.SignerCertificate){$sig.SignerCertificate.Issuer}else{$null};"
        "SignerThumbprint=if($sig.SignerCertificate){$sig.SignerCertificate.Thumbprint}else{$null};"
        "SignerNotAfter=if($sig.SignerCertificate){$sig.SignerCertificate.NotAfter.ToString('o')}else{$null}"
        "} | ConvertTo-Json -Depth 3"
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
        "signer_subject": parsed.get("SignerSubject"),
        "signer_issuer": parsed.get("SignerIssuer"),
        "signer_thumbprint": parsed.get("SignerThumbprint"),
        "signer_not_after": parsed.get("SignerNotAfter"),
        "raw": result,
    }


def main() -> int:
    signtool = _signtool()
    current_user = _code_signing_certs("CurrentUser")
    local_machine = _code_signing_certs("LocalMachine")
    signature = _authenticode(INSTALLER) if INSTALLER.exists() else {
        "checked": False,
        "status": "installer-missing",
        "signed": False,
    }

    blockers = []
    if not signtool["path"]:
        blockers.append("signtool-missing")
    if current_user["count"] == 0 and local_machine["count"] == 0:
        blockers.append("code-signing-certificate-missing")
    if SIGNING_REQUIRED_FOR_PRIVATE_DISTRIBUTION and not signature["signed"]:
        blockers.append("installer-not-signed")

    result = {
        "status": "pass",
        "release_signing_ready": not blockers,
        "signing_required_for_private_distribution": SIGNING_REQUIRED_FOR_PRIVATE_DISTRIBUTION,
        "unsigned_installer_allowed_for_private_distribution": (
            not SIGNING_REQUIRED_FOR_PRIVATE_DISTRIBUTION and not signature["signed"]
        ),
        "installer": str(INSTALLER),
        "installer_exists": INSTALLER.exists(),
        "signtool": signtool["path"],
        "signtool_path_source": signtool["source"],
        "signtool_candidates": signtool["candidates"],
        "current_user_code_signing_certs": current_user,
        "local_machine_code_signing_certs": local_machine,
        "authenticode": signature,
        "blockers": blockers,
        "note": (
            "This preflight reports signing capability and Authenticode state. "
            "Unsigned installers are allowed for the current private distribution policy."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True, default=str), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
