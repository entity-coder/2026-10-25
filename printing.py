"""Printable documents for FeeTrack — fee receipts and the class summary.

Both receipt sizes are generated from the same data:
  * A4 — a full receipt for the school file, built with Platypus.
  * 80mm thermal — a narrow receipt for a small printer, drawn with a
    canvas. The page height grows with the content, so a receipt is
    never cut off mid-line.

A receipt always shows the fee total, what was paid before this
receipt, this payment, and the due that remains — so the slip alone
is enough to answer "how much is left?".
"""

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

THERMAL_WIDTH = 80 * mm


def _receipt_lines(payment, school_name):
    """Shared receipt content, as (label, value) rows."""
    total = payment["total"]
    paid_before = payment["paid_before"]
    due_after = max(0.0, round(total - paid_before - payment["amount"], 2))
    return [
        ("School", school_name or "FeeTrack School"),
        ("Receipt", payment["receipt_no"]),
        ("Date", payment["pay_date"]),
        ("Student", payment["student_name"]),
        ("Class", f"{payment['class_name']}"
         + (f" - {payment['section']}" if payment.get("section") else "")
         + (f" (Roll {payment['roll_no']})" if payment.get("roll_no") else "")),
        ("Total fee", f"Rs {total:.2f}"),
        ("Paid before", f"Rs {paid_before:.2f}"),
        ("This payment", f"Rs {payment['amount']:.2f} ({payment['method']})"),
        ("Due after", f"Rs {due_after:.2f}"),
    ] + ([("Note", payment["note"])] if payment.get("note") else [])


def receipt_pdf_a4(payment, school_name, path):
    """Full A4 fee receipt."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    story = [
        Paragraph(school_name or "FeeTrack School", styles["Title"]),
        Paragraph("Fee Receipt", styles["Heading2"]),
        Spacer(1, 6),
    ]
    rows = [[label, value] for label, value in _receipt_lines(payment, school_name)]
    table = Table(rows, colWidths=[130, 340])
    table.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 11),
        ("FONT", (0, 0), (0, -1), "Helvetica-Bold", 11),
        ("LINEBELOW", (0, 0), (-1, -2), 0.5, colors.lightgrey),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story += [table, Spacer(1, 18),
              Paragraph("Thank you for the payment.", styles["Normal"])]
    SimpleDocTemplate(str(path), pagesize=A4,
                      title=f"Receipt {payment['receipt_no']}").build(story)
    return path


def receipt_pdf_thermal(payment, school_name, path):
    """80mm thermal receipt; height grows with the number of lines."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = _receipt_lines(payment, school_name)
    line_height = 12
    height = 30 + line_height * (len(lines) + 3)
    c = canvas.Canvas(str(path), pagesize=(THERMAL_WIDTH, height))
    y = height - 18
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(THERMAL_WIDTH / 2, y, school_name or "FeeTrack School")
    y -= 16
    c.drawCentredString(THERMAL_WIDTH / 2, y, "FEE RECEIPT")
    y -= 16
    c.setFont("Helvetica", 9)
    for label, value in lines:
        # Long values wrap onto a second line instead of running off the paper.
        text = f"{label}: {value}"
        while len(text) > 38:
            c.drawString(6, y, text[:38])
            text = text[38:]
            y -= line_height
        c.drawString(6, y, text)
        y -= line_height
    y -= 4
    c.drawCentredString(THERMAL_WIDTH / 2, y, "Thank you!")
    c.showPage()
    c.save()
    return path


def class_summary_pdf(summary, school_name, path):
    """A4 class-wise collection summary (from Reports > Export PDF)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    story = [
        Paragraph(school_name or "FeeTrack School", styles["Title"]),
        Paragraph("Class-wise Collection Summary", styles["Heading2"]),
        Spacer(1, 6),
    ]
    rows = [["Class", "Pupils", "Total fees", "Collected", "Pending"]]
    for row in summary:
        rows.append([row["class_name"], str(row["students"]),
                     f"Rs {row['total']:.2f}", f"Rs {row['collected']:.2f}",
                     f"Rs {row['pending']:.2f}"])
    rows.append(["TOTAL", str(sum(r["students"] for r in summary)),
                 f"Rs {sum(r['total'] for r in summary):.2f}",
                 f"Rs {sum(r['collected'] for r in summary):.2f}",
                 f"Rs {sum(r['pending'] for r in summary):.2f}"])
    table = Table(rows, colWidths=[90, 60, 105, 105, 105])
    table.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, -1), "Helvetica", 11),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 11),
        ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 11),
        ("LINEBELOW", (0, 0), (-1, -2), 0.5, colors.lightgrey),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(table)
    SimpleDocTemplate(str(path), pagesize=A4, title="Class Summary").build(story)
    return path
