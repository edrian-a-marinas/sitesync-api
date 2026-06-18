import io
from datetime import date

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def build_report_pdf(
    project_name: str,
    week_start: date,
    week_end: date,
    total_hours: float,
    total_material_cost: float,
    log_count: int,
    incident_count: int,
    open_incident_count: int,
) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(50, 800, "SITESYNC WEEKLY REPORT")

    pdf.setFont("Helvetica", 12)
    pdf.drawString(50, 770, f"Project: {project_name}")
    pdf.drawString(50, 750, f"Period: {week_start} to {week_end}")
    pdf.drawString(50, 720, f"Total Logs Submitted: {log_count}")
    pdf.drawString(50, 700, f"Total Hours Worked: {total_hours}")
    pdf.drawString(50, 680, f"Total Material Cost: {total_material_cost}")
    pdf.drawString(50, 660, f"Total Incidents: {incident_count}")
    pdf.drawString(50, 640, f"Open Incidents: {open_incident_count}")

    pdf.save()
    return buffer.getvalue()
