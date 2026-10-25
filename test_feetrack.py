"""Headless tests for FeeTrack's database, backup and printing layers.

Run:  python test_feetrack.py
No window is opened, so this runs anywhere (CI, a server, this VM).
The UI itself is smoke-tested separately under Xvfb, not here.
"""

import tempfile
from pathlib import Path

import backup as backup_mod
import db
import printing


def check(name, condition):
    print(("PASS " if condition else "FAIL ") + name)
    assert condition, name


def main():
    tmp = Path(tempfile.mkdtemp())
    conn = db.connect(tmp / "feetrack.db")

    # Students + fee heads -------------------------------------------------
    a = db.add_student(conn, "Asha Patil", "Class 5", "A", "12", "9876543210")
    b = db.add_student(conn, "Rahul Verma", "Class 5", "A", "13", "")
    c = db.add_student(conn, "Meera Khan", "Class 6", "B", "4", "9123456789")
    check("search finds by name", len(db.list_students(conn, search="Asha")) == 1)
    check("search finds by phone",
          len(db.list_students(conn, search="9876")) == 1)
    check("class filter works",
          len(db.list_students(conn, class_name="Class 6")) == 1)
    db.add_fee_head(conn, "Class 5", "Tuition", 12000)
    db.add_fee_head(conn, "Class 5", "Transport", 3000)
    db.add_fee_head(conn, "Class 6", "Tuition", 14000)
    check("class total sums heads", db.class_total(conn, "Class 5") == 15000)
    check("class with no heads totals zero", db.class_total(conn, "Class 9") == 0)
    try:
        db.add_fee_head(conn, "Class 5", "Tuition", 100)
        check("duplicate fee head refused", False)
    except ValueError:
        check("duplicate fee head refused", True)

    # Dues + payments ------------------------------------------------------
    total, paid, due = db.student_dues(conn, a)
    check("due equals class total before payment", (total, paid, due) == (15000, 0, 15000))
    receipt, pid = db.add_payment(conn, a, 5000, "Cash", "2026-10-25")
    check("first receipt number", receipt == "FT-0001")
    total, paid, due = db.student_dues(conn, a)
    check("due falls after payment", (paid, due) == (5000, 10000))
    try:
        db.add_payment(conn, a, 10001, "Cash", "2026-10-25")
        check("overpayment refused", False)
    except ValueError:
        check("overpayment refused", True)
    try:
        db.add_payment(conn, a, 0, "Cash", "2026-10-25")
        check("zero payment refused", False)
    except ValueError:
        check("zero payment refused", True)
    receipt2, _ = db.add_payment(conn, a, 10000, "UPI", "2026-10-26", "final instalment")
    check("second receipt number", receipt2 == "FT-0002")
    check("fully paid student owes zero", db.student_dues(conn, a)[2] == 0)
    db.add_payment(conn, b, 3000, "Cash", "2026-10-25")
    db.add_payment(conn, c, 4000, "Bank Transfer", "2026-10-25")

    # Defaulters ------------------------------------------------------------
    defaulters = db.defaulters(conn)
    check("fully paid student is not a defaulter",
          all(d["id"] != a for d in defaulters))
    check("defaulters sorted by largest due first",
          [d["id"] for d in defaulters] == [b, c] or
          defaulters[0]["due"] >= defaulters[1]["due"])
    check("defaulter class filter",
          len(db.defaulters(conn, class_name="Class 6")) == 1)

    # Reports ---------------------------------------------------------------
    summary = {r["class_name"]: r for r in db.class_summary(conn)}
    check("class summary collected",
          summary["Class 5"]["collected"] == 18000)
    check("class summary pending",
          summary["Class 5"]["pending"] == 12000)
    months = {m["month"]: m for m in db.monthly_totals(conn)}
    check("monthly total for Oct 2026",
          months["2026-10"]["total"] == 22000)
    check("monthly receipt count", months["2026-10"]["receipts"] == 4)
    check("total collected", db.total_collected(conn) == 22000)
    check("collected on a day", db.collected_on(conn, "2026-10-25") == 12000)

    # Delete guards ---------------------------------------------------------
    try:
        db.delete_student(conn, a)
        check("delete with payments refused", False)
    except ValueError:
        check("delete with payments refused", True)
    d = db.add_student(conn, "Temp Pupil", "Class 5")
    db.delete_student(conn, d)
    check("delete without payments works",
          db.get_student(conn, d) is None)
    db.deactivate_student(conn, b)
    check("deactivated student hidden from lists",
          all(s["id"] != b for s in db.list_students(conn)))
    try:
        db.add_payment(conn, b, 100, "Cash", "2026-10-27")
        check("payment for deactivated student refused", False)
    except ValueError:
        check("payment for deactivated student refused", True)

    # Settings + backup ------------------------------------------------------
    db.set_setting(conn, "school_name", "Sunrise School")
    check("setting round-trip",
          db.get_setting(conn, "school_name") == "Sunrise School")
    dest = backup_mod.backup_db(tmp / "feetrack.db")
    check("backup file created", dest.exists())
    conn.close()
    safety = backup_mod.restore_db(tmp / "feetrack.db", dest)
    check("restore keeps a safety copy", safety.exists())
    conn2 = db.connect(tmp / "feetrack.db")
    check("restored data intact",
          db.get_setting(conn2, "school_name") == "Sunrise School")
    conn2.close()

    # Printing ----------------------------------------------------------------
    conn3 = db.connect(tmp / "feetrack.db")
    payment = db.get_payment(conn3, pid)
    total_c, paid_c, _ = db.student_dues(conn3, a)
    payment["total"] = total_c
    payment["paid_before"] = 0  # first payment for Asha
    a4 = printing.receipt_pdf_a4(payment, "Sunrise School", tmp / "r-a4.pdf")
    th = printing.receipt_pdf_thermal(payment, "Sunrise School", tmp / "r-th.pdf")
    check("A4 receipt is a valid PDF", a4.read_bytes()[:5] == b"%PDF-")
    check("thermal receipt is a valid PDF", th.read_bytes()[:5] == b"%PDF-")
    summary_pdf = printing.class_summary_pdf(
        db.class_summary(conn3), "Sunrise School", tmp / "summary.pdf")
    check("summary PDF valid", summary_pdf.read_bytes()[:5] == b"%PDF-")
    conn3.close()

    print("All FeeTrack tests passed.")


if __name__ == "__main__":
    main()
