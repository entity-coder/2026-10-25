"""FeeTrack database layer — pure SQLite, no UI imports.

Money is stored as REAL rupees and always rounded to 2 decimals when it is
summed or displayed (see ``money()``). That keeps the code readable for a
small school app; the 1-paise binary-float edge case is documented in the
README trade-offs, exactly as in the earlier sellable apps.

Tables:
  students   — one row per pupil. ``active`` is 0 after deactivation; a
               student is never hard-deleted while payments exist, so
               receipts can always be traced back to them.
  fee_heads  — one charge per (class, head name), e.g. Class 5 / Tuition.
               A student's total fee is the sum of the heads for their class.
               The total is computed at read time, so editing a head
               changes the dues of every student in that class — that is
               deliberate: a fee revision *should* apply to the whole class.
               Amounts already paid are never rewritten.
  payments   — one row per collection, with a sequential receipt number
               (FT-0001, FT-0002, ...). Payments are append-only: there is
               no delete or edit, because a receipt that has been printed
               must stay auditable.
  settings   — simple key/value store (school name, etc.).
"""

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    class_name TEXT NOT NULL,
    section TEXT NOT NULL DEFAULT '',
    roll_no TEXT NOT NULL DEFAULT '',
    guardian_phone TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS fee_heads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_name TEXT NOT NULL,
    name TEXT NOT NULL,
    amount REAL NOT NULL CHECK (amount >= 0),
    UNIQUE (class_name, name)
);
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id),
    receipt_no TEXT NOT NULL UNIQUE,
    amount REAL NOT NULL CHECK (amount > 0),
    method TEXT NOT NULL DEFAULT 'Cash',
    pay_date TEXT NOT NULL,  -- ISO date YYYY-MM-DD
    note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def money(value):
    """Round a rupee amount to 2 decimals (the single money rule)."""
    return round(float(value) + 1e-9, 2)


def connect(path):
    """Open the database at ``path`` and make sure the schema exists."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


# ---------------------------------------------------------------- students

def add_student(conn, name, class_name, section="", roll_no="", guardian_phone=""):
    name = name.strip()
    class_name = class_name.strip()
    if not name or not class_name:
        raise ValueError("Student name and class are required.")
    cur = conn.execute(
        "INSERT INTO students (name, class_name, section, roll_no, guardian_phone)"
        " VALUES (?, ?, ?, ?, ?)",
        (name, class_name, section.strip(), roll_no.strip(), guardian_phone.strip()),
    )
    conn.commit()
    return cur.lastrowid


def list_students(conn, search="", class_name="", active_only=True):
    """Students matching the filters, ordered by class then name."""
    sql = "SELECT * FROM students WHERE 1 = 1"
    args = []
    if active_only:
        sql += " AND active = 1"
    if class_name:
        sql += " AND class_name = ?"
        args.append(class_name)
    if search:
        sql += " AND (name LIKE ? OR guardian_phone LIKE ? OR roll_no LIKE ?)"
        like = f"%{search}%"
        args += [like, like, like]
    sql += " ORDER BY class_name, name"
    return [dict(r) for r in conn.execute(sql, args)]


def get_student(conn, student_id):
    row = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    return dict(row) if row else None


def update_student(conn, student_id, name, class_name, section, roll_no, guardian_phone):
    if not name.strip() or not class_name.strip():
        raise ValueError("Student name and class are required.")
    conn.execute(
        "UPDATE students SET name=?, class_name=?, section=?, roll_no=?,"
        " guardian_phone=? WHERE id=?",
        (name.strip(), class_name.strip(), section.strip(), roll_no.strip(),
         guardian_phone.strip(), student_id),
    )
    conn.commit()


def deactivate_student(conn, student_id):
    """Soft-delete: the student disappears from lists but history stays."""
    conn.execute("UPDATE students SET active = 0 WHERE id = ?", (student_id,))
    conn.commit()


def delete_student(conn, student_id):
    """Hard delete is allowed only when the student has no payments."""
    paid = conn.execute(
        "SELECT COUNT(*) FROM payments WHERE student_id = ?", (student_id,)
    ).fetchone()[0]
    if paid:
        raise ValueError("Cannot delete a student with payment history; deactivate instead.")
    conn.execute("DELETE FROM students WHERE id = ?", (student_id,))
    conn.commit()


def distinct_classes(conn):
    rows = conn.execute(
        "SELECT DISTINCT class_name FROM students ORDER BY class_name"
    ).fetchall()
    return [r[0] for r in rows]


# ---------------------------------------------------------------- fee heads

def add_fee_head(conn, class_name, name, amount):
    class_name = class_name.strip()
    name = name.strip()
    amount = money(amount)
    if not class_name or not name:
        raise ValueError("Class and fee-head name are required.")
    if amount < 0:
        raise ValueError("Fee amount cannot be negative.")
    try:
        cur = conn.execute(
            "INSERT INTO fee_heads (class_name, name, amount) VALUES (?, ?, ?)",
            (class_name, name, amount),
        )
    except sqlite3.IntegrityError:
        raise ValueError(f"Fee head '{name}' already exists for {class_name}.")
    conn.commit()
    return cur.lastrowid


def list_fee_heads(conn, class_name=""):
    sql = "SELECT * FROM fee_heads"
    args = []
    if class_name:
        sql += " WHERE class_name = ?"
        args.append(class_name)
    sql += " ORDER BY class_name, name"
    return [dict(r) for r in conn.execute(sql, args)]


def delete_fee_head(conn, head_id):
    conn.execute("DELETE FROM fee_heads WHERE id = ?", (head_id,))
    conn.commit()


def class_total(conn, class_name):
    row = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM fee_heads WHERE class_name = ?",
        (class_name,),
    ).fetchone()
    return money(row[0])


def student_dues(conn, student_id):
    """Return (total_fee, paid, due) for one student, all rounded."""
    student = get_student(conn, student_id)
    if student is None:
        raise ValueError("Student not found.")
    total = class_total(conn, student["class_name"])
    paid = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE student_id = ?",
        (student_id,),
    ).fetchone()[0]
    paid = money(paid)
    # A due can never go below zero, even if heads were lowered after payment.
    due = max(0.0, money(total - paid))
    return total, paid, due


# ---------------------------------------------------------------- payments

def next_receipt_no(conn):
    count = conn.execute("SELECT COUNT(*) FROM payments").fetchone()[0]
    return f"FT-{count + 1:04d}"


def add_payment(conn, student_id, amount, method, pay_date, note=""):
    """Record a collection. Refuses overpayment and payment for inactive pupils.

    The amount is capped by the student's current due: a school register
    must never show a negative due, and an overpayment is a data-entry
    mistake, not a credit — the operator corrects the amount instead.
    """
    student = get_student(conn, student_id)
    if student is None:
        raise ValueError("Student not found.")
    if not student["active"]:
        raise ValueError("Cannot collect from a deactivated student.")
    amount = money(amount)
    if amount <= 0:
        raise ValueError("Payment amount must be greater than zero.")
    _, _, due = student_dues(conn, student_id)
    if amount > due:
        raise ValueError(f"Payment of Rs {amount:.2f} exceeds the due of Rs {due:.2f}.")
    receipt_no = next_receipt_no(conn)
    cur = conn.execute(
        "INSERT INTO payments (student_id, receipt_no, amount, method, pay_date, note)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (student_id, receipt_no, amount, method, pay_date, note.strip()),
    )
    conn.commit()
    return receipt_no, cur.lastrowid


def list_payments(conn, student_id=None, limit=200):
    sql = ("SELECT p.*, s.name AS student_name, s.class_name FROM payments p"
           " JOIN students s ON s.id = p.student_id")
    args = []
    if student_id is not None:
        sql += " WHERE p.student_id = ?"
        args.append(student_id)
    sql += " ORDER BY p.pay_date DESC, p.id DESC LIMIT ?"
    args.append(limit)
    return [dict(r) for r in conn.execute(sql, args)]


def get_payment(conn, payment_id):
    row = conn.execute(
        "SELECT p.*, s.name AS student_name, s.class_name, s.section, s.roll_no"
        " FROM payments p JOIN students s ON s.id = p.student_id WHERE p.id = ?",
        (payment_id,),
    ).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------- defaulters & reports

def defaulters(conn, class_name=""):
    """Students with a due above zero, largest due first.

    Computed in Python, not one SQL query, because a due is
    (class fee-head total) minus (payments) — two different aggregates.
    The student list is small for a small school, so this stays fast.
    """
    students = list_students(conn, class_name=class_name, active_only=True)
    out = []
    for student in students:
        total, paid, due = student_dues(conn, student["id"])
        if due > 0:
            student = dict(student)
            student.update(total=total, paid=paid, due=due)
            out.append(student)
    out.sort(key=lambda s: (-s["due"], s["class_name"], s["name"]))
    return out


def class_summary(conn):
    """One row per class: pupils, total fees, collected, pending."""
    rows = []
    for class_name in distinct_classes(conn):
        students = list_students(conn, class_name=class_name, active_only=True)
        total = money(sum(student_dues(conn, s["id"])[0] for s in students))
        paid = money(sum(student_dues(conn, s["id"])[1] for s in students))
        rows.append({
            "class_name": class_name,
            "students": len(students),
            "total": total,
            "collected": paid,
            "pending": money(total - paid),
        })
    return rows


def monthly_totals(conn):
    """Collection per calendar month (YYYY-MM), newest first."""
    rows = conn.execute(
        "SELECT substr(pay_date, 1, 7) AS month, COALESCE(SUM(amount), 0) AS total,"
        " COUNT(*) AS receipts FROM payments GROUP BY month ORDER BY month DESC"
    ).fetchall()
    return [{"month": r["month"], "total": money(r["total"]), "receipts": r["receipts"]}
            for r in rows]


def total_collected(conn):
    row = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM payments").fetchone()
    return money(row[0])


def collected_on(conn, pay_date):
    row = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE pay_date = ?",
        (pay_date,),
    ).fetchone()
    return money(row[0])


# ---------------------------------------------------------------- settings

def get_setting(conn, key, default=""):
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row[0] if row else default


def set_setting(conn, key, value):
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key)"
        " DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()
