"""Start ScruTech: ``scrutech`` on the command line, or the shortcut on the desktop."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .theme import QSS
from .window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("ScruTech")
    app.setOrganizationName("ScruTech")
    app.setStyleSheet(QSS)
    window = MainWindow()
    window.resize(1280, 820)
    window.show()
    window.first_run_hint()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
