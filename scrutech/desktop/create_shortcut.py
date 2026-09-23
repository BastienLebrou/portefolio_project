"""Put a ScruTech launcher on the user's machine (Windows).

Writes the Mantis emblem as an .ico next to the app, then a shortcut that starts ScruTech with
the windowed interpreter of its own environment: no console window, no command to remember.

Run:  uv run python create_shortcut.py [DOSSIER]     (default: %USERPROFILE%\\Desktop\\ScruTech)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "src" / "scrutech_desktop" / "assets"
DEFAULT_FOLDER = Path.home() / "Desktop" / "ScruTech"


def make_icon(target: Path) -> Path:
    """The emblem as an .ico, drawn by Qt."""
    from PySide6.QtCore import QSize
    from PySide6.QtWidgets import QApplication

    from scrutech_desktop.icons import pixmap

    app = QApplication.instance() or QApplication([])
    pixmap("mantis-emblem", QSize(256, 256)).save(str(target), "ICO")
    del app
    return target


def windowed_python() -> Path:
    """The interpreter of this environment that opens no console (pythonw.exe)."""
    windowed = Path(sys.executable).with_name("pythonw.exe")
    return windowed if windowed.is_file() else Path(sys.executable)


def make_shortcut(folder: Path) -> Path:
    """A ScruTech.lnk in ``folder`` starting the app, with its icon."""
    folder.mkdir(parents=True, exist_ok=True)
    icon = make_icon(ASSETS / "scrutech.ico")
    link = folder / "ScruTech.lnk"
    script = (
        f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{link}');"
        f"$s.TargetPath = '{windowed_python()}';"
        "$s.Arguments = '-m scrutech_desktop.app';"
        f"$s.WorkingDirectory = '{HERE}';"
        f"$s.IconLocation = '{icon}';"
        "$s.Description = 'ScruTech : diagnostic de territoire';"
        "$s.Save()"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        check=True,
        capture_output=True,
    )
    return link


def main() -> int:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_FOLDER
    if sys.platform != "win32":
        print("Raccourci Windows seulement : lancez « scrutech » dans cet environnement.")
        return 1
    print(f"Raccourci créé : {make_shortcut(folder)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
