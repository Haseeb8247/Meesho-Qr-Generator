import re
from pathlib import Path

import fitz  # PyMuPDF
import pandas as pd
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


# Optional filenames used only when running this module directly.
# The Flask app passes uploaded file paths to the functions below.
PDF_FILE = "shipping_labels.pdf"
CSV_FILE = "orders.csv"
OUTPUT_PDF = "meesho_awb_packet_qr_printable.pdf"
OUTPUT_REPORT = "meesho_awb_packet_qr_match_report.xlsx"


def extract_sub_order_id(text):
    """Extract a Meesho sub-order ID, such as 340188156317054912_1."""
    matches = re.findall(r"\b\d{15,22}_\d+\b", text)
    return matches[0] if matches else ""


def extract_awb(text):
    """Extract common AWB formats from shipping-label text."""
    patterns = [
        r"\bVL\d{10,}\b",          # Valmo
        r"\bSF[A-Za-z0-9]+FPL\b",  # Shadowfax
        r"\b\d{15,16}\b",          # Numeric AWBs
    ]

    for pattern in patterns:
        matches = re.findall(pattern, text, flags=re.IGNORECASE)
        if matches:
            return matches[0]
    return ""


def read_csv_safely(csv_path):
    """Read CSV values as strings so IDs are not converted to numbers."""
    try:
        df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    except UnicodeDecodeError:
        df = pd.read_csv(
            csv_path,
            dtype=str,
            keep_default_na=False,
            encoding="latin1",
        )

    df.columns = df.columns.astype(str).str.strip()
    return df


def draw_qr(pdf_canvas, value, x, y, size):
    """Draw a QR code containing the exact supplied value."""
    value = str(value).strip() if value is not None else ""

    if not value:
        pdf_canvas.setFont("Helvetica-Bold", 12)
        pdf_canvas.drawCentredString(
            x + size / 2, y + size / 2, "VALUE MISSING"
        )
        return

    widget = qr.QrCodeWidget(value)
    x0, y0, x1, y1 = widget.getBounds()
    width = x1 - x0
    height = y1 - y0

    drawing = Drawing(
        size,
        size,
        transform=[
            size / width, 0,
            0, size / height,
            0, 0,
        ],
    )
    drawing.add(widget)
    renderPDF.draw(drawing, pdf_canvas, x, y)


def extract_pdf_orders(pdf_path):
    """Extract one record per page from the uploaded shipping-label PDF."""
    records = []

    with fitz.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf, start=1):
            text = page.get_text("text")
            records.append({
                "PDF Page": page_number,
                "Sub Order No": extract_sub_order_id(text),
                "AWB": extract_awb(text),
            })

    return records


def match_with_csv(pdf_records, csv_path):
    """Match extracted sub-order IDs to Packet Id values in the orders CSV."""
    df = read_csv_safely(csv_path)

    required_columns = ["Sub Order No", "Packet Id"]
    missing = [column for column in required_columns if column not in df.columns]

    if missing:
        raise ValueError(
            "CSV is missing required column(s): "
            + ", ".join(missing)
            + "\nAvailable columns: "
            + ", ".join(df.columns)
        )

    df["Sub Order No"] = df["Sub Order No"].astype(str).str.strip()
    df["Packet Id"] = df["Packet Id"].astype(str).str.strip()

    status_column = "Reason for Credit Entry"
    if status_column in df.columns:
        df[status_column] = (
            df[status_column].astype(str).str.strip().str.upper()
        )
    else:
        df[status_column] = ""

    grouped = {
        key: group
        for key, group in df.groupby("Sub Order No", sort=False)
        if key
    }

    results = []

    for record in pdf_records:
        sub_order_id = str(record.get("Sub Order No", "")).strip()
        matches = grouped.get(sub_order_id)

        packet_id = ""
        status = ""
        match_result = "SUB-ORDER NOT FOUND IN CSV"

        if matches is not None and not matches.empty:
            packet_ids = [
                value.strip()
                for value in matches["Packet Id"].tolist()
                if value.strip()
            ]
            packet_id = packet_ids[0] if packet_ids else ""

            status_values = [
                value.strip()
                for value in matches[status_column].tolist()
                if value.strip()
            ]
            status = status_values[0] if status_values else ""

            if len(matches) > 1:
                match_result = f"DUPLICATE CSV MATCHES ({len(matches)})"
            else:
                match_result = "MATCHED"

            if not packet_id:
                match_result += " - PACKET ID MISSING"

        results.append({
            **record,
            "Packet Id": packet_id,
            "CSV Status": status,
            "Match Result": match_result,
        })

    return pd.DataFrame(results)


def create_printable_pdf(results_df, output_path):
    """
    Create two pages per order:
    Page 1: AWB QR + AWB number + sub-order ID as text.
    Page 2: Packet ID QR + Packet ID text.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    page_width, page_height = A4
    pdf = canvas.Canvas(str(output_path), pagesize=A4)
    total = len(results_df)

    for order_index, (_, row) in enumerate(results_df.iterrows(), start=1):
        awb = str(row.get("AWB", "")).strip()
        sub_order_id = str(row.get("Sub Order No", "")).strip()
        packet_id = str(row.get("Packet Id", "")).strip()
        status = str(row.get("CSV Status", "")).strip() or "UNKNOWN"
        match_result = str(row.get("Match Result", "")).strip()

        # PAGE 1: AWB QR, AWB number and sub-order ID as text only.
        pdf.setFont("Helvetica-Bold", 20)
        pdf.drawString(40, page_height - 48, f"ORDER {order_index} OF {total}")

        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(40, page_height - 82, "AWB NUMBER")

        pdf.setFont("Helvetica-Bold", 19)
        pdf.drawString(40, page_height - 110, awb or "AWB NOT EXTRACTED")

        draw_qr(pdf, awb, 55, page_height - 330, 170)

        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawCentredString(140, page_height - 350, "AWB QR CODE")

        pdf.setFont("Helvetica-Bold", 13)
        pdf.drawString(285, page_height - 145, "SUB ORDER ID")

        pdf.setFont("Helvetica", 10)
        pdf.drawString(
            285, page_height - 165, sub_order_id or "NOT EXTRACTED"
        )

        pdf.setFont("Helvetica", 10)
        pdf.drawString(40, 75, f"CSV status: {status}")
        pdf.drawString(40, 58, f"Source PDF page: {row.get('PDF Page', '')}")
        pdf.showPage()

        # PAGE 2: Packet ID QR and Packet ID as text.
        pdf.setFont("Helvetica-Bold", 20)
        pdf.drawString(40, page_height - 48, f"ORDER {order_index} OF {total}")

        pdf.setFont("Helvetica-Bold", 14)
        pdf.drawString(40, page_height - 95, "PACKET ID")

        pdf.setFont("Helvetica-Bold", 19)
        pdf.drawString(
            40, page_height - 128, packet_id or "PACKET ID MISSING"
        )

        draw_qr(pdf, packet_id, 170, page_height - 430, 250)

        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawCentredString(295, page_height - 452, "PACKET ID QR CODE")

        pdf.setFont("Helvetica", 10)
        pdf.drawString(
            40, 75, f"Sub Order ID: {sub_order_id or 'NOT EXTRACTED'}"
        )
        pdf.drawString(40, 58, f"Match result: {match_result}")
        pdf.showPage()

    pdf.save()


def main():
    """Optional command-line mode; the Flask app does not call this function."""
    pdf_path = Path(PDF_FILE)
    csv_path = Path(CSV_FILE)

    if not pdf_path.is_file():
        raise FileNotFoundError(
            f"PDF not found: {pdf_path.resolve()}. "
            "Update PDF_FILE or upload the PDF through the Flask app."
        )

    if not csv_path.is_file():
        raise FileNotFoundError(
            f"CSV not found: {csv_path.resolve()}. "
            "Update CSV_FILE or upload the CSV through the Flask app."
        )

    print("Reading shipping-label PDF...")
    pdf_records = extract_pdf_orders(pdf_path)

    print("Matching sub-order IDs with the CSV...")
    results_df = match_with_csv(pdf_records, csv_path)

    print("Generating printable PDF...")
    create_printable_pdf(results_df, OUTPUT_PDF)

    print("Saving Excel matching report...")
    results_df.to_excel(OUTPUT_REPORT, index=False, engine="openpyxl")

    total = len(results_df)
    awb_count = results_df["AWB"].astype(str).str.strip().ne("").sum()
    sub_order_count = (
        results_df["Sub Order No"].astype(str).str.strip().ne("").sum()
    )
    packet_count = results_df["Packet Id"].astype(str).str.strip().ne("").sum()
    matched_count = (
        results_df["Match Result"].astype(str).str.startswith("MATCHED").sum()
    )

    print("\n========== COMPLETE ==========")
    print(f"PDF label pages processed: {total}")
    print(f"AWB numbers extracted: {awb_count}/{total}")
    print(f"Sub-order IDs extracted: {sub_order_count}/{total}")
    print(f"Packet IDs found: {packet_count}/{total}")
    print(f"Matched orders: {matched_count}/{total}")
    print(f"Printable PDF: {Path(OUTPUT_PDF).resolve()}")
    print(f"Excel report: {Path(OUTPUT_REPORT).resolve()}")
    print("Each order uses two consecutive pages in the printable PDF.")


if __name__ == "__main__":
    main()
