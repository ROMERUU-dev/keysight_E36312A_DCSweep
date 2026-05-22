from __future__ import annotations

import argparse
import logging
import sys

from src.utils.logger import setup_logging


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Keysight E36312A DC sweep GUI")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable verbose SCPI/application logging.",
    )
    parser.add_argument(
        "--fullscreen",
        action="store_true",
        help="Start the application in full screen mode.",
    )
    parser.add_argument(
        "--windowed",
        action="store_true",
        help="Start the application in a normal window instead of maximized.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    setup_logging(logging.DEBUG if args.debug else logging.INFO)

    try:
        from PySide6.QtWidgets import QApplication
        from src.gui.main_window import MainWindow
    except ImportError as exc:
        print(
            "Missing GUI dependency. Install with: "
            "python -m pip install -r requirements.txt",
            file=sys.stderr,
        )
        print(str(exc), file=sys.stderr)
        return 1

    app = QApplication(sys.argv)
    window = MainWindow()
    if args.windowed:
        window.show()
    elif args.fullscreen:
        window.enter_full_screen()
    else:
        window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
