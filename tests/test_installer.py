"""Installer scripts: syntax, no published default password, required options."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INSTALL_PS1 = ROOT / "install.ps1"
INSTALL_BAT = ROOT / "install.bat"
failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(("PASS  " if condition else "FAIL  ") + name + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(name)


def powershell_syntax_errors(path: Path) -> str:
    quoted = str(path).replace("'", "''")
    script = (
        "$errors = $null; "
        f"[void][System.Management.Automation.Language.Parser]::ParseFile('{quoted}', [ref]$null, [ref]$errors); "
        "if ($errors -and $errors.Count -gt 0) { $errors | ForEach-Object { $_.Message }; exit 1 }"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.stdout.strip() if result.returncode != 0 else ""


def main() -> int:
    check("install.ps1 exists", INSTALL_PS1.is_file())
    check("install.bat exists", INSTALL_BAT.is_file())
    if not (INSTALL_PS1.is_file() and INSTALL_BAT.is_file()):
        print("\nINSTALLER RESULT: FAIL")
        return 1

    text = INSTALL_PS1.read_text(encoding="utf-8")
    bat = INSTALL_BAT.read_text(encoding="utf-8")

    errors = powershell_syntax_errors(INSTALL_PS1)
    check("install.ps1 parses", not errors, errors[:200])
    check("install.bat calls install.ps1", "install.ps1" in bat and "-File" in bat)

    for option in ("-Source", "-InstallDir", "-SkipDeps", "-Run", "-PythonExe", "-Port"):
        check(f"option {option} documented", option in text)

    check("no published default password in the installer", "123admin" not in text and "123admin" not in bat)
    check("installer keeps user data", "data" in text and "kept on upgrade" in text)
    check("installer downloads a GitHub archive", "codeload.github.com" in text)

    copy_block = re.search(r"\$copyItems = @\((.*?)\)", text, re.S)
    listed = copy_block.group(1) if copy_block else ""
    for item in ("app", "web", "run.py", "requirements.txt", "install.ps1"):
        check(f"copies {item}", f'"{item}"' in listed)
    for unwanted in ('"tests"', '"data"', '".venv"', '".git"'):
        check(f"does not copy {unwanted.strip(chr(34))}", unwanted not in listed)

    print("\nINSTALLER RESULT:", "PASS" if not failures else f"FAIL ({len(failures)}): {failures}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
