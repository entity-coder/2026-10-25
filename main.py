"""FeeTrack — school fee manager. Run:  python main.py

Data lives in ~/.feetrack/ (feetrack.db, receipts/, backups/, reports/)
so rebuilding the .exe never touches a school's records.
"""

import sys
from pathlib import Path

import db
from ui import FeeTrackApp


def data_dir():
    if getattr(sys, "frozen", False):
        # PyInstaller build: keep data next to the .exe on the school PC.
        return Path(sys.executable).resolve().parent
    return Path.home() / ".feetrack"


def main():
    folder = data_dir()
    folder.mkdir(parents=True, exist_ok=True)
    conn = db.connect(folder / "feetrack.db")
    app = FeeTrackApp(conn, folder)
    app.mainloop()


if __name__ == "__main__":
    main()
