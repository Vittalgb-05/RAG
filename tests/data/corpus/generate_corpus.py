# ------------------------------------------------------------------
# Test Corpus Generator
# Generates 6 representative synthetic PDFs for testing and benchmarking
# ------------------------------------------------------------------

import os
from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors


def get_corpus_dir() -> Path:
    corpus_dir = Path(__file__).resolve().parent
    corpus_dir.mkdir(parents=True, exist_ok=True)
    return corpus_dir


def generate_clean_digital_pdf(output_path: Path, pages: int = 20) -> None:
    """Generates a 20-page digital PDF with clear headings and paragraphs."""
    doc = SimpleDocTemplate(str(output_path), pagesize=letter)
    styles = getSampleStyleSheet()
    h1 = styles["Heading1"]
    h2 = styles["Heading2"]
    normal = styles["Normal"]

    story = []
    for p in range(1, pages + 1):
        story.append(Paragraph(f"Section {p}: Fundamentals of Intelligence Systems", h1))
        story.append(Spacer(1, 12))
        story.append(Paragraph(f"Subsection {p}.1: Core Operational Architecture", h2))
        story.append(Spacer(1, 8))
        story.append(
            Paragraph(
                f"This is page {p} of the representative digital document. "
                "Document processing requires deterministic extraction of layout, "
                "semantic section hierarchy, and clean token representation. "
                f"Unique verifiable claim for page {p}: System latency metric is target-{p}0 milliseconds.",
                normal,
            )
        )
        story.append(Spacer(1, 10))
        story.append(
            Paragraph(
                "When analyzing long-context documents on consumer hardware with 4 GB GPU VRAM, "
                "resource allocation must be strictly disciplined. Preprocessing pipelines must isolate "
                "page extraction failures without aborting remaining document pages.",
                normal,
            )
        )
        story.append(Spacer(1, 14))
        if p < pages:
            story.append(PageBreak())

    doc.build(story)


def generate_multi_column_pdf(output_path: Path) -> None:
    """Generates a multi-column styled PDF across 2 pages."""
    c = canvas.Canvas(str(output_path), pagesize=letter)
    width, height = letter

    for page_num in [1, 2]:
        c.setFont("Helvetica-Bold", 16)
        c.drawString(54, height - 54, f"Multi-Column Document - Page {page_num}")

        # Column 1
        c.setFont("Helvetica", 10)
        col1_x = 54
        col1_y = height - 90
        c.drawString(col1_x, col1_y, "Column 1: Executive Overview")
        c.drawString(col1_x, col1_y - 20, "Left column discussion of system boundaries.")
        c.drawString(col1_x, col1_y - 35, "Information retrieval combines dense vectors")
        c.drawString(col1_x, col1_y - 50, "with keyword full-text search indexes.")

        # Column 2
        col2_x = width / 2 + 20
        col2_y = height - 90
        c.drawString(col2_x, col2_y, "Column 2: Technical Breakdown")
        c.drawString(col2_x, col2_y - 20, "Right column details hardware profiles.")
        c.drawString(col2_x, col2_y - 35, "GPU memory constraints mandate single VLM")
        c.drawString(col2_x, col2_y - 50, "instantiation in VRAM at any given time.")

        c.showPage()
    c.save()


def generate_dense_table_pdf(output_path: Path) -> None:
    """Generates a table-heavy PDF with structured financial/operational data."""
    doc = SimpleDocTemplate(str(output_path), pagesize=letter)
    styles = getSampleStyleSheet()
    story = [Paragraph("Quarterly Financial & Operational Metrics", styles["Heading1"]), Spacer(1, 14)]

    data = [
        ["Quarter", "Revenue ($M)", "Gross Margin", "Compute Cost ($k)", "Net Latency (ms)"],
        ["Q1 2025", "124.5", "68.2%", "45.0", "320"],
        ["Q2 2025", "142.1", "70.1%", "48.5", "295"],
        ["Q3 2025", "168.9", "71.4%", "52.3", "270"],
        ["Q4 2025", "195.4", "73.0%", "58.0", "240"],
        ["FY Total", "630.9", "70.7%", "203.8", "281"],
    ]

    t = Table(data, colWidths=[90, 95, 95, 105, 105])
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f3f4f6")),
                ("GRID", (0, 0), (-1, -1), 1, colors.HexColor("#9ca3af")),
            ]
        )
    )
    story.append(t)
    doc.build(story)


def generate_scanned_sample_pdf(output_path: Path) -> None:
    """Generates a scanned-like PDF page containing raster drawing with zero extractable text."""
    c = canvas.Canvas(str(output_path), pagesize=letter)
    width, height = letter

    # Draw shapes representing scanned text lines and stamps (no c.drawString calls)
    c.setFillColor(colors.HexColor("#2d3748"))
    for i in range(15):
        y = height - 100 - (i * 35)
        c.rect(72, y, width - 144, 12, fill=1, stroke=0)

    # Simulated red stamp
    c.setStrokeColor(colors.red)
    c.setLineWidth(3)
    c.circle(width / 2, height / 2, 60, fill=0, stroke=1)

    c.showPage()
    c.save()


def generate_chart_diagram_pdf(output_path: Path) -> None:
    """Generates a page with an architecture flowchart / diagram."""
    c = canvas.Canvas(str(output_path), pagesize=letter)
    width, height = letter

    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, height - 72, "System Workflow Diagram")

    # Box 1: Ingestion
    c.rect(72, height - 200, 120, 60, fill=0, stroke=1)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(85, height - 170, "1. Ingestion")

    # Arrow
    c.line(192, height - 170, 242, height - 170)

    # Box 2: Retrieval
    c.rect(242, height - 200, 120, 60, fill=0, stroke=1)
    c.drawString(255, height - 170, "2. Hybrid Search")

    # Arrow
    c.line(362, height - 170, 412, height - 170)

    # Box 3: Generation
    c.rect(412, height - 200, 120, 60, fill=0, stroke=1)
    c.drawString(425, height - 170, "3. Local VLM")

    c.showPage()
    c.save()


def generate_corrupt_invalid_pdf(output_path: Path) -> None:
    """Generates a non-PDF file with invalid magic bytes."""
    with open(output_path, "wb") as f:
        f.write(b"NOT_A_VALID_PDF_HEADER\x00\x01\x02\x03RandomBinaryBytesDataPayload1234567890")


def generate_all_corpus_files() -> dict[str, Path]:
    """Generates all 6 corpus test files and returns a map of file names to paths."""
    corpus_dir = get_corpus_dir()

    files = {
        "clean_digital": corpus_dir / "clean_digital.pdf",
        "multi_column": corpus_dir / "multi_column.pdf",
        "dense_table": corpus_dir / "dense_table.pdf",
        "scanned_sample": corpus_dir / "scanned_sample.pdf",
        "chart_diagram": corpus_dir / "chart_diagram.pdf",
        "corrupt_invalid": corpus_dir / "corrupt_invalid.pdf",
    }

    generate_clean_digital_pdf(files["clean_digital"], pages=20)
    generate_multi_column_pdf(files["multi_column"])
    generate_dense_table_pdf(files["dense_table"])
    generate_scanned_sample_pdf(files["scanned_sample"])
    generate_chart_diagram_pdf(files["chart_diagram"])
    generate_corrupt_invalid_pdf(files["corrupt_invalid"])

    return files


if __name__ == "__main__":
    generated = generate_all_corpus_files()
    print("Corpus generation complete:")
    for name, path in generated.items():
        print(f"  - {name}: {path} ({path.stat().st_size} bytes)")
