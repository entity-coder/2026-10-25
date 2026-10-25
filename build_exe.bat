@echo off
REM FeeTrack — one-click Windows .exe build (PyInstaller).
REM Run this once on the school PC. The .exe lands in dist\FeeTrack\.
REM Your data (feetrack.db, receipts\, backups\, reports\) lives next to
REM the .exe and is never touched by a rebuild.
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install pyinstaller
python -m PyInstaller --noconfirm --windowed --name FeeTrack ^
  main.py
echo.
echo Done. Run dist\FeeTrack\FeeTrack.exe
pause
