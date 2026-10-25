# FeeTrack — School Fee Manager

A desktop fee-collection tracker for small private schools that still run
on registers: student-wise dues, printable receipts, defaulter lists and
class-wise reports. Offline-first, no account, no internet needed.

## What it does

- **Students** — name, class/section, roll number, guardian phone. Search by
  name, phone or roll number. Deactivate (never silently erase) a pupil who
  leaves; payment history is always kept.
- **Fee heads, per class** — configure charges like Tuition, Transport and
  Exam fees for each class. A student's total fee is the sum of the heads
  for their class, so a fee revision applies to the whole class at once.
- **Collection** — record a payment (Cash / UPI / Card / Bank Transfer /
  Cheque) and get a printable receipt instantly, in both A4 and 80mm
  thermal sizes. Receipt numbers run FT-0001, FT-0002, …
- **Defaulters** — unpaid dues per class, largest due first, with a total
  pending figure. One click filters by class.
- **Reports** — class-wise collection summary (pupils, total fees,
  collected, pending, exportable as an A4 PDF) and monthly collection totals.
- **Dashboard** — active pupils, total collected, collected today, total
  pending dues and defaulter count at a glance.
- **Backup & restore** — one-click timestamped backup; restore keeps a
  `.safety` copy of the current database first.

## Rules the app enforces (so the register stays honest)

- A payment can never exceed the student's current due — overpayment is
  refused, not stored as a negative due.
- Payments are append-only: no edit, no delete, so a printed receipt can
  always be traced.
- A student with payment history cannot be hard-deleted; deactivate instead.
- Amounts already paid are never rewritten when fee heads change — only the
  due moves.

## How to run

```bash
pip install -r requirements.txt
python main.py
```

On Windows, `build_exe.bat` builds a one-click `.exe` with PyInstaller
(`dist\FeeTrack\FeeTrack.exe`). Run it once on the school PC.

Data lives in `~/.feetrack/` when run from source (next to the `.exe` in
the PyInstaller build): `feetrack.db`, plus `receipts/`, `backups/` and
`reports/` folders. Rebuilding the `.exe` never touches that data.

## Files

- `main.py` — entry point, picks the data folder and starts the app
- `ui.py` — CustomTkinter screens (Dashboard, Students, Fee Heads,
  Collect Fee, Defaulters, Reports, Settings)
- `db.py` — SQLite layer: students, fee heads, payments, defaulters,
  reports, settings (no UI imports, fully testable headlessly)
- `printing.py` — A4 + 80mm thermal receipts and the class-summary PDF
  (reportlab)
- `backup.py` — timestamped backup and safety-copy restore
- `test_feetrack.py` — headless tests: `python test_feetrack.py`

## Interview notes

**What is this project?** FeeTrack is a small offline desktop app that
replaces a school's paper fee register. A school enters its pupils once,
sets the fee heads for each class, and then records collections against
individual pupils. Every collection produces a numbered receipt, and the
app always knows who still owes what, per class and per month.

**Why Python + CustomTkinter + SQLite?** The users are small schools on
ordinary Windows PCs with no IT staff. Python with CustomTkinter gives a
real native-feeling desktop app from one codebase with no build step for
development, and PyInstaller turns it into a double-click `.exe` they can
actually run. SQLite needs no server, no setup and no maintenance, and the
whole database is a single file — which is also what makes one-click
backup/restore trivial (just copy the file). A web app would have added
hosting and browser-printing friction for zero benefit here.

**Why is the fee total computed at read time instead of stored?**
Because fee heads are per class, not per pupil. Storing a snapshot per
pupil would mean a fee revision needs a migration over every pupil row
and risks stale dues. Computing `sum(heads for class) − sum(payments)`
at read time keeps one source of truth; the trade-off is that lowering a
head after collections can shrink a due to zero (handled by clamping the
due at zero, never below), and the app documents that a revision applies
to the whole class immediately.

**Why are payments append-only, and why is overpayment refused?**
A receipt is a financial record. If payments could be edited or deleted,
a printed receipt could disagree with the database and nobody could
prove which was right. Refusing overpayment (instead of storing a
negative due or a "credit") keeps the register's invariant simple:
`due = total − paid`, always `>= 0`. The cost is that a genuine
overpayment (e.g. a parent paying for next term early) has no place to
go — the honest extension is a separate "advance" ledger, not a negative
due.

**Main trade-offs / limitations**
- Single-user, single-machine: no multi-clerk locking and no cloud sync.
  Two people collecting on two PCs would diverge; that is a deliberate
  scope cut for a small school, and the fix would be a small server
  (e.g. SQLite over a shared drive is *not* safe — a real server DB
  would be needed).
- Money is stored as floating-point rupees and rounded to 2 decimals on
  every sum. For school-fee magnitudes this is fine, but a 1-paise
  binary-float edge exists (e.g. `445.50 × 5%` rounds to `22.27` in
  binary float rather than `22.28`); a stricter build would store integer
  paise throughout.
- Receipts are generated as PDFs, not sent straight to the printer — the
  operator prints from their PDF viewer. That avoids printer-driver
  surprises on unknown school hardware.
- The app was not compiled or device-tested on the author's machine for
  this build beyond the headless tests and UI smoke test; on the school
  PC, run `build_exe.bat` once and do one test collection before going live.

**How would I extend it?** Per-term fee schedules (instead of one flat
total per class), an "advance payment" ledger, SMS/WhatsApp reminders to
defaulters' guardians, and a multi-user mode with a small server database
and per-clerk login.
