"""Build GhostRec for Windows: dist/GhostRec/GhostRec.exe (+ installer).

    pip install -r requirements.txt pyinstaller
    python packaging/build.py

Produces:
  dist/GhostRec/                       the app folder (GhostRec.exe inside)
  dist/GhostRec-<version>-portable.zip run-anywhere zip of that folder
  dist/GhostRec-Setup-<version>.exe    installer, when Inno Setup's ISCC is
                                       installed (CI installs it; locally optional)
  dist/SHA256SUMS.txt                  checksums users can verify downloads with
"""

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ghostrec import __version__  # noqa: E402

DIST = ROOT / "dist"
ICON = ROOT / "ghostrec" / "ui" / "assets" / "app.ico"


def find_iscc():
    found = shutil.which("iscc")
    if found:
        return found
    for base in (os.environ.get("ProgramFiles(x86)"),
                 os.environ.get("ProgramFiles"),
                 os.environ.get("LOCALAPPDATA") and
                 os.path.join(os.environ["LOCALAPPDATA"], "Programs")):
        if base:
            candidate = Path(base) / "Inno Setup 6" / "ISCC.exe"
            if candidate.exists():
                return str(candidate)
    return None


def version_file():
    """Windows file properties (Details tab). Unsigned exes without them look
    more suspicious to SmartScreen and antivirus heuristics."""
    nums = tuple(int(x) for x in __version__.split(".")) + (0,)
    text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={nums}, prodvers={nums}),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('CompanyName', 'jaeef'),
    StringStruct('FileDescription', 'GhostRec - record one window with OBS'),
    StringStruct('FileVersion', '{__version__}'),
    StringStruct('InternalName', 'GhostRec'),
    StringStruct('LegalCopyright', 'Copyright (c) 2026 jaeef. All rights reserved.'),
    StringStruct('OriginalFilename', 'GhostRec.exe'),
    StringStruct('ProductName', 'GhostRec'),
    StringStruct('ProductVersion', '{__version__}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])])
"""
    path = ROOT / "build" / "version_info.txt"
    path.parent.mkdir(exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_checksums():
    lines = []
    for f in sorted(DIST.glob("GhostRec-*")):
        if f.is_file() and f.suffix in (".exe", ".zip"):
            digest = hashlib.sha256(f.read_bytes()).hexdigest()
            lines.append(f"{digest}  {f.name}")
    # LF endings so `sha256sum -c` works too, not only Get-FileHash
    (DIST / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n",
                                         encoding="utf-8", newline="\n")
    print("[build] " + str(DIST / "SHA256SUMS.txt"))


def main():
    import PyInstaller.__main__

    # ponytail: onedir, not onefile, starts faster and trips antivirus less
    PyInstaller.__main__.run([
        str(ROOT / "app.py"),
        "--name=GhostRec",
        "--windowed",
        "--noconfirm",
        "--clean",
        f"--icon={ICON}",
        f"--version-file={version_file()}",
        f"--add-data={ROOT / 'ghostrec' / 'ui' / 'assets'}{os.pathsep}"
        "ghostrec/ui/assets",
        f"--distpath={DIST}",
        f"--workpath={ROOT / 'build'}",
        f"--specpath={ROOT / 'build'}",
    ])

    app_dir = DIST / "GhostRec"
    shutil.copy(ROOT / "LICENSE", app_dir / "LICENSE.txt")
    zip_base = DIST / f"GhostRec-{__version__}-portable"
    shutil.make_archive(str(zip_base), "zip", DIST, "GhostRec")
    print(f"[build] {app_dir / 'GhostRec.exe'}")
    print(f"[build] {zip_base}.zip")

    iscc = find_iscc()
    if not iscc:
        print("[build] Inno Setup not found - skipped the installer "
              "(install it from jrsoftware.org, or let CI build it)")
        write_checksums()
        return
    subprocess.run([iscc, f"/DMyAppVersion={__version__}",
                    f"/DSourceDir={app_dir}", f"/DOutputDir={DIST}",
                    str(ROOT / "packaging" / "installer.iss")], check=True)
    print(f"[build] {DIST / f'GhostRec-Setup-{__version__}.exe'}")
    write_checksums()


if __name__ == "__main__":
    main()
