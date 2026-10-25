"""FeeTrack desktop UI — CustomTkinter, one screen per sidebar button.

Every screen is a frame with a ``refresh()`` method; the app calls it
whenever the screen is shown, so lists never go stale after an action
on another screen. All money and validation rules live in ``db.py`` —
this file only collects input, calls it, and shows the result.
"""

import tkinter.messagebox as messagebox
from datetime import date
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

import backup as backup_mod
import db
import printing

METHODS = ["Cash", "UPI", "Card", "Bank Transfer", "Cheque"]
NAV = ["Dashboard", "Students", "Fee Heads", "Collect Fee",
       "Defaulters", "Reports", "Settings"]


def clear(frame):
    for child in frame.winfo_children():
        child.destroy()


def row_label(parent, text, button_text=None, button_cmd=None):
    """One list row: a label, optionally with a button on the right."""
    frame = ctk.CTkFrame(parent)
    frame.pack(fill="x", padx=4, pady=3)
    ctk.CTkLabel(frame, text=text, anchor="w").pack(side="left", fill="x", expand=True)
    if button_text:
        ctk.CTkButton(frame, text=button_text, width=90,
                      command=button_cmd).pack(side="right", padx=4)
    return frame


class FeeTrackApp(ctk.CTk):
    def __init__(self, conn, data_dir):
        super().__init__()
        self.conn = conn
        self.data_dir = Path(data_dir)
        self.title("FeeTrack — School Fee Manager")
        self.geometry("980x640")
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        sidebar = ctk.CTkFrame(self, width=160, corner_radius=0)
        sidebar.pack(side="left", fill="y")
        ctk.CTkLabel(sidebar, text="FeeTrack",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(pady=16)
        self.nav_buttons = {}
        for name in NAV:
            btn = ctk.CTkButton(sidebar, text=name,
                                command=lambda n=name: self.show(n))
            btn.pack(fill="x", padx=10, pady=4)
            self.nav_buttons[name] = btn

        self.content = ctk.CTkFrame(self, corner_radius=0)
        self.content.pack(side="right", fill="both", expand=True)
        self.screens = {
            "Dashboard": DashboardScreen(self.content, self),
            "Students": StudentsScreen(self.content, self),
            "Fee Heads": FeeHeadsScreen(self.content, self),
            "Collect Fee": CollectScreen(self.content, self),
            "Defaulters": DefaultersScreen(self.content, self),
            "Reports": ReportsScreen(self.content, self),
            "Settings": SettingsScreen(self.content, self),
        }
        self.show("Dashboard")

    def show(self, name):
        for screen in self.screens.values():
            screen.pack_forget()
        screen = self.screens[name]
        screen.pack(fill="both", expand=True)
        screen.refresh()

    def reload_db(self):
        """Reopen the connection after a restore (the file was replaced)."""
        self.conn.close()
        self.conn = db.connect(self.data_dir / "feetrack.db")


# ---------------------------------------------------------------- dashboard

class DashboardScreen(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        ctk.CTkLabel(self, text="Dashboard",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(pady=12)
        self.cards = ctk.CTkFrame(self)
        self.cards.pack(fill="x", padx=12)
        self.labels = {}
        for key in ("students", "collected", "today", "pending", "defaulters"):
            box = ctk.CTkFrame(self.cards)
            box.pack(side="left", fill="x", expand=True, padx=6, pady=6)
            ctk.CTkLabel(box, text=key.replace("_", " ").title()).pack(pady=(8, 0))
            value = ctk.CTkLabel(box, text="—",
                                 font=ctk.CTkFont(size=18, weight="bold"))
            value.pack(pady=(0, 8))
            self.labels[key] = value
        self.hint = ctk.CTkLabel(self, text="", wraplength=700)
        self.hint.pack(pady=16)

    def refresh(self):
        conn = self.app.conn
        students = db.list_students(conn)
        pending = sum(d["due"] for d in db.defaulters(conn))
        self.labels["students"].configure(text=str(len(students)))
        self.labels["collected"].configure(text=f"Rs {db.total_collected(conn):.2f}")
        self.labels["today"].configure(
            text=f"Rs {db.collected_on(conn, date.today().isoformat()):.2f}")
        self.labels["pending"].configure(text=f"Rs {pending:.2f}")
        self.labels["defaulters"].configure(
            text=str(len(db.defaulters(conn))))
        school = db.get_setting(conn, "school_name", "")
        self.hint.configure(
            text=(f"School: {school}" if school else
                  "Set the school name under Settings — it appears on every receipt.")
            + "  Start with Students, then Fee Heads for each class, then Collect Fee.")


# ---------------------------------------------------------------- students

class StudentsScreen(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.editing_id = None
        ctk.CTkLabel(self, text="Students",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(pady=8)
        form = ctk.CTkFrame(self)
        form.pack(fill="x", padx=12, pady=4)
        self.entries = {}
        for key, label in (("name", "Name"), ("class_name", "Class"),
                           ("section", "Section"), ("roll_no", "Roll no."),
                           ("guardian_phone", "Guardian phone")):
            ctk.CTkLabel(form, text=label).pack(side="left", padx=4)
            entry = ctk.CTkEntry(form, width=110 if key != "name" else 150)
            entry.pack(side="left", padx=2)
            self.entries[key] = entry
        self.save_btn = ctk.CTkButton(form, text="Add student", command=self.save)
        self.save_btn.pack(side="left", padx=8)
        search_row = ctk.CTkFrame(self)
        search_row.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(search_row, text="Search").pack(side="left", padx=4)
        self.search = ctk.CTkEntry(search_row, width=300)
        self.search.pack(side="left")
        ctk.CTkButton(search_row, text="Search",
                      command=self.refresh).pack(side="left", padx=8)
        self.list_frame = ctk.CTkScrollableFrame(self)
        self.list_frame.pack(fill="both", expand=True, padx=12, pady=4)

    def save(self):
        values = {k: e.get() for k, e in self.entries.items()}
        try:
            if self.editing_id:
                db.update_student(self.app.conn, self.editing_id, **values)
                self.editing_id = None
                self.save_btn.configure(text="Add student")
            else:
                db.add_student(self.app.conn, **values)
        except ValueError as exc:
            messagebox.showerror("FeeTrack", str(exc))
            return
        for entry in self.entries.values():
            entry.delete(0, "end")
        self.refresh()

    def refresh(self):
        clear(self.list_frame)
        students = db.list_students(self.app.conn, search=self.search.get().strip())
        if not students:
            ctk.CTkLabel(self.list_frame, text="No students yet.").pack(pady=8)
            return
        for student in students:
            total, paid, due = db.student_dues(self.app.conn, student["id"])
            text = (f"{student['name']} — {student['class_name']}"
                    + (f" {student['section']}" if student["section"] else "")
                    + (f" (Roll {student['roll_no']})" if student["roll_no"] else "")
                    + (f" · {student['guardian_phone']}" if student["guardian_phone"] else "")
                    + f" · Due Rs {due:.2f} of Rs {total:.2f} (paid Rs {paid:.2f})")
            frame = row_label(self.list_frame, text)
            ctk.CTkButton(frame, text="Edit", width=60,
                          command=lambda s=student: self.edit(s)).pack(side="right")
            ctk.CTkButton(frame, text="Deactivate", width=90,
                          command=lambda s=student: self.deactivate(s)).pack(side="right")

    def edit(self, student):
        self.editing_id = student["id"]
        for key, entry in self.entries.items():
            entry.delete(0, "end")
            entry.insert(0, student[key])
        self.save_btn.configure(text="Save changes")

    def deactivate(self, student):
        if messagebox.askyesno("FeeTrack", f"Deactivate {student['name']}? "
                               "Payment history is kept."):
            db.deactivate_student(self.app.conn, student["id"])
            self.refresh()


# ---------------------------------------------------------------- fee heads

class FeeHeadsScreen(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        ctk.CTkLabel(self, text="Fee Heads (per class)",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(pady=8)
        form = ctk.CTkFrame(self)
        form.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(form, text="Class").pack(side="left", padx=4)
        self.class_entry = ctk.CTkEntry(form, width=100)
        self.class_entry.pack(side="left")
        ctk.CTkLabel(form, text="Head").pack(side="left", padx=4)
        self.head_entry = ctk.CTkEntry(form, width=140)
        self.head_entry.pack(side="left")
        ctk.CTkLabel(form, text="Amount Rs").pack(side="left", padx=4)
        self.amount_entry = ctk.CTkEntry(form, width=100)
        self.amount_entry.pack(side="left")
        ctk.CTkButton(form, text="Add head", command=self.add).pack(side="left", padx=8)
        filter_row = ctk.CTkFrame(self)
        filter_row.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(filter_row, text="Show class").pack(side="left", padx=4)
        self.filter_var = ctk.StringVar(value="All")
        self.filter_menu = ctk.CTkOptionMenu(filter_row, variable=self.filter_var,
                                             values=["All"], command=lambda _: self.refresh())
        self.filter_menu.pack(side="left")
        self.list_frame = ctk.CTkScrollableFrame(self)
        self.list_frame.pack(fill="both", expand=True, padx=12, pady=4)

    def add(self):
        try:
            amount = float(self.amount_entry.get())
        except ValueError:
            messagebox.showerror("FeeTrack", "Amount must be a number.")
            return
        try:
            db.add_fee_head(self.app.conn, self.class_entry.get(),
                            self.head_entry.get(), amount)
        except ValueError as exc:
            messagebox.showerror("FeeTrack", str(exc))
            return
        self.head_entry.delete(0, "end")
        self.amount_entry.delete(0, "end")
        self.refresh()

    def refresh(self):
        classes = ["All"] + db.distinct_classes(self.app.conn)
        self.filter_menu.configure(values=classes)
        if self.filter_var.get() not in classes:
            self.filter_var.set("All")
        chosen = "" if self.filter_var.get() == "All" else self.filter_var.get()
        clear(self.list_frame)
        heads = db.list_fee_heads(self.app.conn, class_name=chosen)
        if not heads:
            ctk.CTkLabel(self.list_frame,
                         text="No fee heads yet. Add e.g. Class 5 / Tuition / 12000.").pack(pady=8)
            return
        for head in heads:
            row_label(self.list_frame,
                      f"{head['class_name']} — {head['name']}: Rs {head['amount']:.2f}",
                      "Delete",
                      lambda h=head: self.delete(h))

    def delete(self, head):
        if messagebox.askyesno("FeeTrack", "Delete this fee head? "
                               "Dues for the whole class change immediately."):
            db.delete_fee_head(self.app.conn, head["id"])
            self.refresh()


# ---------------------------------------------------------------- collect

class CollectScreen(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.selected_id = None
        ctk.CTkLabel(self, text="Collect Fee",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(pady=8)
        search_row = ctk.CTkFrame(self)
        search_row.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(search_row, text="Find student").pack(side="left", padx=4)
        self.search = ctk.CTkEntry(search_row, width=300)
        self.search.pack(side="left")
        ctk.CTkButton(search_row, text="Search",
                      command=self.refresh).pack(side="left", padx=8)
        self.results = ctk.CTkScrollableFrame(self, height=140)
        self.results.pack(fill="x", padx=12, pady=4)
        self.selected_label = ctk.CTkLabel(self, text="No student selected.",
                                           font=ctk.CTkFont(weight="bold"))
        self.selected_label.pack(pady=4)
        form = ctk.CTkFrame(self)
        form.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(form, text="Amount Rs").pack(side="left", padx=4)
        self.amount_entry = ctk.CTkEntry(form, width=110)
        self.amount_entry.pack(side="left")
        ctk.CTkLabel(form, text="Method").pack(side="left", padx=4)
        self.method_var = ctk.StringVar(value="Cash")
        ctk.CTkOptionMenu(form, variable=self.method_var, values=METHODS).pack(side="left")
        ctk.CTkLabel(form, text="Date").pack(side="left", padx=4)
        self.date_entry = ctk.CTkEntry(form, width=110)
        self.date_entry.insert(0, date.today().isoformat())
        self.date_entry.pack(side="left")
        ctk.CTkLabel(form, text="Note").pack(side="left", padx=4)
        self.note_entry = ctk.CTkEntry(form, width=140)
        self.note_entry.pack(side="left")
        ctk.CTkButton(form, text="Collect & print receipt",
                      command=self.collect).pack(side="left", padx=8)
        ctk.CTkLabel(self, text="Recent payments",
                     font=ctk.CTkFont(weight="bold")).pack(pady=(8, 0))
        self.history = ctk.CTkScrollableFrame(self)
        self.history.pack(fill="both", expand=True, padx=12, pady=4)

    def select(self, student):
        self.selected_id = student["id"]
        total, paid, due = db.student_dues(self.app.conn, student["id"])
        self.selected_label.configure(
            text=f"{student['name']} — {student['class_name']}: "
                 f"total Rs {total:.2f}, paid Rs {paid:.2f}, due Rs {due:.2f}")
        self.amount_entry.delete(0, "end")
        if due > 0:
            self.amount_entry.insert(0, f"{due:.2f}")

    def refresh(self):
        clear(self.results)
        for student in db.list_students(self.app.conn, search=self.search.get().strip()):
            total, paid, due = db.student_dues(self.app.conn, student["id"])
            row_label(self.results,
                      f"{student['name']} — {student['class_name']} · Due Rs {due:.2f}",
                      "Select", lambda s=student: self.select(s))
        clear(self.history)
        for payment in db.list_payments(self.app.conn, limit=30):
            ctk.CTkLabel(self.history,
                         text=f"{payment['receipt_no']} · {payment['pay_date']} · "
                              f"{payment['student_name']} ({payment['class_name']}) · "
                              f"Rs {payment['amount']:.2f} ({payment['method']})",
                         anchor="w").pack(fill="x", padx=4, pady=2)

    def collect(self):
        if self.selected_id is None:
            messagebox.showerror("FeeTrack", "Select a student first.")
            return
        try:
            amount = float(self.amount_entry.get())
        except ValueError:
            messagebox.showerror("FeeTrack", "Amount must be a number.")
            return
        try:
            receipt_no, payment_id = db.add_payment(
                self.app.conn, self.selected_id, amount,
                self.method_var.get(), self.date_entry.get().strip(),
                self.note_entry.get())
        except ValueError as exc:
            messagebox.showerror("FeeTrack", str(exc))
            return
        # Receipt PDFs: total/paid-before are computed from the stored row
        # plus this payment, so the slip is correct even if heads changed.
        payment = db.get_payment(self.app.conn, payment_id)
        paid_after = db.student_dues(self.app.conn, self.selected_id)[1]
        payment["total"] = db.student_dues(self.app.conn, self.selected_id)[0]
        payment["paid_before"] = db.money(paid_after - payment["amount"])
        school = db.get_setting(self.app.conn, "school_name", "")
        receipts = self.app.data_dir / "receipts"
        a4 = printing.receipt_pdf_a4(payment, school, receipts / f"{receipt_no}-A4.pdf")
        thermal = printing.receipt_pdf_thermal(
            payment, school, receipts / f"{receipt_no}-thermal.pdf")
        messagebox.showinfo("FeeTrack", f"Receipt {receipt_no} saved.\n{a4}\n{thermal}")
        student = db.get_student(self.app.conn, self.selected_id)
        self.select(student)
        self.refresh()


# ---------------------------------------------------------------- defaulters

class DefaultersScreen(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        ctk.CTkLabel(self, text="Defaulters",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(pady=8)
        filter_row = ctk.CTkFrame(self)
        filter_row.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(filter_row, text="Class").pack(side="left", padx=4)
        self.filter_var = ctk.StringVar(value="All")
        self.filter_menu = ctk.CTkOptionMenu(filter_row, variable=self.filter_var,
                                             values=["All"], command=lambda _: self.refresh())
        self.filter_menu.pack(side="left")
        self.total_label = ctk.CTkLabel(self, text="", font=ctk.CTkFont(weight="bold"))
        self.total_label.pack(pady=4)
        self.list_frame = ctk.CTkScrollableFrame(self)
        self.list_frame.pack(fill="both", expand=True, padx=12, pady=4)

    def refresh(self):
        classes = ["All"] + db.distinct_classes(self.app.conn)
        self.filter_menu.configure(values=classes)
        if self.filter_var.get() not in classes:
            self.filter_var.set("All")
        chosen = "" if self.filter_var.get() == "All" else self.filter_var.get()
        clear(self.list_frame)
        defaulters = db.defaulters(self.app.conn, class_name=chosen)
        total = sum(d["due"] for d in defaulters)
        self.total_label.configure(
            text=f"{len(defaulters)} defaulter(s) · total pending Rs {total:.2f}")
        if not defaulters:
            ctk.CTkLabel(self.list_frame, text="Nobody owes anything.").pack(pady=8)
            return
        for student in defaulters:
            phone = f" · {student['guardian_phone']}" if student["guardian_phone"] else ""
            row_label(self.list_frame,
                      f"{student['name']} — {student['class_name']}{phone}: "
                      f"due Rs {student['due']:.2f} (paid Rs {student['paid']:.2f} "
                      f"of Rs {student['total']:.2f})")


# ---------------------------------------------------------------- reports

class ReportsScreen(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        ctk.CTkLabel(self, text="Reports",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(pady=8)
        ctk.CTkButton(self, text="Export class summary PDF",
                      command=self.export).pack(pady=4)
        ctk.CTkLabel(self, text="Class-wise summary",
                     font=ctk.CTkFont(weight="bold")).pack(pady=(8, 0))
        self.summary_frame = ctk.CTkScrollableFrame(self, height=200)
        self.summary_frame.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(self, text="Monthly totals",
                     font=ctk.CTkFont(weight="bold")).pack(pady=(8, 0))
        self.monthly_frame = ctk.CTkScrollableFrame(self)
        self.monthly_frame.pack(fill="both", expand=True, padx=12, pady=4)

    def refresh(self):
        clear(self.summary_frame)
        for row in db.class_summary(self.app.conn):
            ctk.CTkLabel(self.summary_frame,
                         text=f"{row['class_name']}: {row['students']} pupil(s) · "
                              f"total Rs {row['total']:.2f} · collected Rs {row['collected']:.2f} "
                              f"· pending Rs {row['pending']:.2f}",
                         anchor="w").pack(fill="x", padx=4, pady=2)
        clear(self.monthly_frame)
        for row in db.monthly_totals(self.app.conn):
            ctk.CTkLabel(self.monthly_frame,
                         text=f"{row['month']}: Rs {row['total']:.2f} "
                              f"({row['receipts']} receipt(s))",
                         anchor="w").pack(fill="x", padx=4, pady=2)

    def export(self):
        summary = db.class_summary(self.app.conn)
        school = db.get_setting(self.app.conn, "school_name", "")
        path = printing.class_summary_pdf(
            summary, school, self.app.data_dir / "reports" / "class-summary.pdf")
        messagebox.showinfo("FeeTrack", f"Class summary saved to:\n{path}")


# ---------------------------------------------------------------- settings

class SettingsScreen(ctk.CTkFrame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        ctk.CTkLabel(self, text="Settings & Backup",
                     font=ctk.CTkFont(size=20, weight="bold")).pack(pady=8)
        row = ctk.CTkFrame(self)
        row.pack(fill="x", padx=12, pady=8)
        ctk.CTkLabel(row, text="School name").pack(side="left", padx=4)
        self.school_entry = ctk.CTkEntry(row, width=300)
        self.school_entry.pack(side="left")
        ctk.CTkButton(row, text="Save", command=self.save_school).pack(side="left", padx=8)
        ctk.CTkLabel(self, text="").pack()  # spacer
        ctk.CTkButton(self, text="Backup now", command=self.backup).pack(pady=4)
        ctk.CTkButton(self, text="Restore from backup…",
                      command=self.restore).pack(pady=4)
        self.info = ctk.CTkLabel(self, text="", wraplength=700)
        self.info.pack(pady=12)

    def refresh(self):
        self.school_entry.delete(0, "end")
        self.school_entry.insert(0, db.get_setting(self.app.conn, "school_name", ""))
        self.info.configure(text=f"Data folder: {self.app.data_dir}\n"
                                 "Receipts land in receipts/, backups in backups/.")

    def save_school(self):
        db.set_setting(self.app.conn, "school_name", self.school_entry.get().strip())
        messagebox.showinfo("FeeTrack", "School name saved.")

    def backup(self):
        dest = backup_mod.backup_db(self.app.data_dir / "feetrack.db")
        messagebox.showinfo("FeeTrack", f"Backup saved to:\n{dest}")

    def restore(self):
        picked = filedialog.askopenfilename(
            title="Pick a FeeTrack backup (.db)",
            filetypes=[("SQLite database", "*.db"), ("All files", "*.*")])
        if not picked:
            return
        if messagebox.askyesno("FeeTrack", "Restore this backup? "
                               "The current database is kept as a .safety copy."):
            backup_mod.restore_db(self.app.data_dir / "feetrack.db", picked)
            self.app.reload_db()
            messagebox.showinfo("FeeTrack", "Restored. Showing the restored data now.")
            self.app.show("Dashboard")
