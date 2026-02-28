from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Image,
    Table,
    TableStyle,
    Spacer
)
from reportlab.lib.pagesizes import LETTER, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph, Image, Spacer
from typing import Optional, List
import os
from reportlab.platypus import Paragraph, Spacer, ListFlowable, ListItem
import matplotlib.pyplot as plt
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import Paragraph, Spacer, ListFlowable, ListItem
# ============================================================

def format_inr(amount):
    """Format number into Indian numbering format."""
    amount = float(str(amount).replace(",", ""))
    s = f"{amount:.2f}"
    integer, decimal = s.split(".")

    if len(integer) > 3:
        last3 = integer[-3:]
        rest = integer[:-3]
        rest = ",".join([rest[max(i-2,0):i] for i in range(len(rest), 0, -2)][::-1])
        integer = rest + "," + last3

    return integer + "." + decimal


def create_custom_styles():
    """Create and return custom paragraph styles for the report."""
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        "Title",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=20,
        alignment=1,  # center
        textColor=colors.HexColor("#1F2937"),
        spaceAfter=20,
    )

    h2_style = ParagraphStyle(
        "Heading2",
        parent=styles["Heading2"],
        fontSize=14,
        textColor=colors.HexColor("#111827"),
        spaceBefore=20,
        spaceAfter=10,
    )

    body_style = ParagraphStyle(
        "BodyText",
        parent=styles["BodyText"],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#374151"),
        spaceAfter=10,
    )

    caption_style = ParagraphStyle(
        "Caption",
        parent=styles["Normal"],
        fontSize=8,
        alignment=1,
        textColor=colors.HexColor("#6B7280"),
        spaceAfter=20,
        spaceBefore=6,
    )
    
    return {
        "title": title_style,
        "heading2": h2_style,
        "body": body_style,
        "caption": caption_style,
    }


def add_title_section(story, title_text, styles):
    """Add title section to report."""
    story.append(Paragraph(title_text, styles["title"]))


def add_intro_section(story, intro_text, styles):
    """Add introduction paragraph to report."""
    story.append(Paragraph(intro_text, styles["body"]))


def add_chart_section(story, image_path, figure_caption, styles, max_width):
    """Add chart/image section to report (safe scaling)."""

    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Chart image not found: {image_path}")

    # Read image size
    img_reader = ImageReader(image_path)
    img_width, img_height = img_reader.getSize()

    # Constrain image
    max_height = 4 * inch
    scale = min(max_width / img_width, max_height / img_height)

    img = Image(
        image_path,
        width=img_width * scale,
        height=img_height * scale,
    )
    img.hAlign = "CENTER"

    story.append(img)
    story.append(Spacer(1, 6))
    story.append(Paragraph(figure_caption, styles["caption"]))
    story.append(Spacer(1, 6))

def create_table_style(background_color='#FA5053'):
    """Create and return the table styling with text wrapping support."""
    return TableStyle(
        [
            # Header
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(background_color)),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),

            # Body
            ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BACKGROUND", (0, 1), (-1, -1), colors.white),
            ("ALIGN", (0, 1), (-1, -1), "LEFT"),
            ("VALIGN", (0, 1), (-1, -1), "TOP"),

            # Grid
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#9CA3AF")),

            # Padding
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
    )


def add_table_section(story, table_data, table_title, background_color, styles, page_width=None):
    """Add table section to report with custom title and background color.
    
    Args:
        story: ReportLab story list
        table_data: Table data (list of lists)
        table_title: Title for the table
        background_color: Hex color for header
        styles: Styles dict
        page_width: Available page width for table
    """
    story.append(Spacer(1, 12))
    story.append(Paragraph(table_title, styles["heading2"]))
    story.append(Spacer(1, 8))
    
    # Create body cell style for text wrapping
    body_cell_style = ParagraphStyle(
        "BodyCell",
        parent=styles["body"],
        fontSize=8,
        leading=10,
    )
    
    # Convert table data to use Paragraphs for text wrapping
    converted_data = []
    for row_idx, row in enumerate(table_data):
        converted_row = []
        for cell_data in row:
            if row_idx == 0:  # Header row
                converted_row.append(str(cell_data))
            else:
                # Convert to Paragraph for text wrapping
                converted_row.append(Paragraph(str(cell_data), body_cell_style))
        converted_data.append(converted_row)
    
    # Calculate column widths to fit page
    if page_width and len(converted_data) > 0:
        num_cols = len(converted_data[0])
        col_width = page_width / num_cols
        col_widths = [col_width] * num_cols
    else:
        col_widths = None
    
    table = Table(converted_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(create_table_style(background_color))
    
    story.append(table)
    story.append(Spacer(1, 8))


def add_multiple_table_sections(story, tables_list, styles, page_width=None):
    """Add multiple table sections to report.
    
    Args:
        story: ReportLab story list
        tables_list: List of dicts with keys: 'data', 'title', 'background_color'
        styles: Styles dict
        page_width: Available page width for tables
    """
    for table_info in tables_list:
        add_table_section(
            story,
            table_info['data'],
            table_info['title'],
            table_info['background_color'],
            styles,
            page_width
        )


def add_footer_section(story, csv_download_link, styles):
    """Add footer section with download link to report."""
    footer_html = f'''
    The full zombie contract dataset is available as a CSV file:
    <br/>
    <a href="{csv_download_link}" color="blue">
        Download zombie_contract_info.csv
    </a>
    '''
    story.append(Paragraph(footer_html, styles["body"]))

def get_segment_title_style(base_style, color_hex):
    return ParagraphStyle(
        name=f"SegmentTitle_{color_hex}",
        parent=base_style,
        fontName="Helvetica-Bold",
        fontSize=10,
        textColor=colors.black,
        spaceAfter=4,
        borderWidth=2,
        borderColor=colors.HexColor(color_hex),
        borderPadding=2.0, 
    )


def add_pie_chart_overview_section(
    story,
    styles,
    overview_intro: str,
    pie_segments: list[dict]
):
    # Section spacing + title
    story.append(Spacer(1, 12))
    story.append(Paragraph("Pie Chart Label Overview", styles["heading2"]))
    story.append(Spacer(1, 6))

    # Intro text
    if overview_intro:
        story.append(Paragraph(overview_intro, styles["body"]))
        story.append(Spacer(1, 10))

    # Build bullet list safely
    bullet_items = []

    for segment in pie_segments:
        title = segment["title"]
        count = segment["count"]
        description = segment["description"]
        color = segment.get("color", "#000000")

        bullet_text = (
            f'<b><font color="{color}">{title} ({count})</font></b><br/>'
            f'{description}'
        )

        bullet_items.append(
            ListItem(
                Paragraph(bullet_text, styles["body"]),
                leftIndent=20
            )
        )

    if bullet_items:
        story.append(
            ListFlowable(
                bullet_items,
                bulletType="bullet",
                start="circle",
                leftIndent=30
            )
        )


def build_leakage_report(
    output_pdf: str,
    image_path: str,
    table_data: Optional[list[list[str]]] = None,
    tables_list: Optional[list[dict]] = None,
    pie_overview_intro: Optional[str] = None,
    pie_segments: Optional[list[dict]] = None,
    title: str = "Leakage Zombies Analysis Report",
    intro_text: str = "...",
    figure_caption: str = "...",
    csv_download_link: str = "...",
    bar_chart_path: Optional[str] = None,
    bar_chart_caption: Optional[str] = None

):
    """Build and generate the leakage report PDF.
    
    Args:
        output_pdf: Output PDF file path
        image_path: Path to the chart image
        table_data: (Deprecated) Single table data. Use tables_list instead.
        tables_list: List of dicts with 'data', 'title', and 'background_color' keys
        title: Report title
        intro_text: Introduction text
        figure_caption: Chart caption
        csv_download_link: Download link for CSV
    """
    doc = SimpleDocTemplate(
        output_pdf,
        pagesize=A4,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    styles = create_custom_styles()
    story = []

    # Build report sections
    add_title_section(story, title, styles)
    add_intro_section(story, intro_text, styles)
    add_chart_section(story, image_path, figure_caption, styles, doc.width)
    if bar_chart_path:
        add_chart_section(story, bar_chart_path, bar_chart_caption or "Bar Chart Overview", styles, doc.width)

    if pie_segments:
       add_pie_chart_overview_section(
        story,
        styles,
        pie_overview_intro or "",
        pie_segments
    )

    
    # Add tables with proper width
    if tables_list:
        add_multiple_table_sections(story, tables_list, styles, doc.width)
    elif table_data:
        add_table_section(story, table_data, "Zombie Contract Details", "#FA5053", styles, doc.width)
    
    # add_footer_section(story, csv_download_link, styles)

    # Build PDF
    doc.build(story)
    print(f"Report generated: {output_pdf}")




def format_inr(amount):
    """Format number into Indian numbering format."""
    amount = float(str(amount).replace(",", ""))
    s = f"{amount:.2f}"
    integer, decimal = s.split(".")

    if len(integer) > 3:
        last3 = integer[-3:]
        rest = integer[:-3]
        rest = ",".join([rest[max(i-2,0):i] for i in range(len(rest), 0, -2)][::-1])
        integer = rest + "," + last3

    return integer + "." + decimal

def build_executive_report(
    output_pdf: str,
    usecase_names,
    losses,
    kpi_values,
    table_data=None,
    chart_path=None,
):
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
        Image,
    )
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    import matplotlib.pyplot as plt
    import os

    doc = SimpleDocTemplate(
        output_pdf,
        pagesize=A4,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    width = doc.width
    story = []

    # ================= TITLE =================
    title_style = ParagraphStyle(
        "title",
        fontName="Helvetica-Bold",
        fontSize=20,
        alignment=1,
        textColor=colors.HexColor("#111827"),
        spaceAfter=20,
    )

    story.append(Paragraph("Executive Revenue Leakage Report", title_style))
    story.append(Spacer(1, 20))

    # ================= KPI SECTION =================
    total_loss, loss_percentage = kpi_values
    card_width = (width - 40) / 2

    label_style = ParagraphStyle(
        "label",
        fontName="Helvetica",
        fontSize=12,
        alignment=1,
        textColor=colors.HexColor("#6B7280"),
    )

    value_style = ParagraphStyle(
        "value",
        fontName="Helvetica-Bold",
        fontSize=18,
        alignment=1,
        textColor=colors.HexColor("#111827"),
        spaceBefore=3,
    )

    cards = []

    for label, value in [
        ("Total Revenue Loss", f"INR {format_inr(total_loss)}"),
        ("Revenue Loss %", f"{loss_percentage:.2f}%"),
    ]:
        card = Table(
            [
                [Paragraph(label, label_style)],
                [Paragraph(value, value_style)],
            ],
            colWidths=[card_width],
        )

        card.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F3F6FB")),
                    ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#E5E7EB")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 20),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 20),
                    ("TOPPADDING", (0, 0), (-1, -1), 15),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 15),
                ]
            )
        )

        cards.append(card)

    kpi_row = Table(
        [[cards[0], "", cards[1]]],
        colWidths=[card_width, 40, card_width],
    )

    story.append(kpi_row)
    story.append(Spacer(1, 30))

    # ================= BAR CHART =================
    if chart_path and os.path.exists(chart_path):
        story.append(Image(chart_path, width=width, height=4 * inch))
    else:
        # fallback: generate chart internally
        plt.figure(figsize=(8, 5))
        plt.barh(usecase_names, losses)
        plt.tight_layout()
        temp_chart = "temp_bar_chart.png"
        plt.savefig(temp_chart, bbox_inches="tight")
        plt.close()
        story.append(Image(temp_chart, width=width, height=4 * inch))

    story.append(Spacer(1, 30))

    # ================= SIMPLE RAG MATRIX TABLE =================

    if table_data:

        header_style = ParagraphStyle(
            "header",
            fontName="Helvetica-Bold",
            fontSize=10,
            textColor=colors.white,
            alignment=1,
        )

        cell_style = ParagraphStyle(
            "cell",
            fontName="Helvetica",
            fontSize=9,
            textColor=colors.HexColor("#111827"),
        )

        tick_style = ParagraphStyle(
            "tick",
            fontName="Helvetica-Bold",
            fontSize=12,
            alignment=1,
            textColor=colors.black,
        )

        formatted_table = []

        # ---- HEADER ----
        formatted_table.append([
            Paragraph("Sr. No.", header_style),
            Paragraph("Diagnostic Name", header_style),
            Paragraph("Total Loss (INR)", header_style),
            Paragraph("R", header_style),
            Paragraph("A", header_style),
            Paragraph("G", header_style),
        ])

        # ---- DATA ----
        for row in table_data[1:]:

            sr = row[0]
            name = row[1]
            loss = row[2]
            risk = row[3].lower()

            r_tick = "✓" if risk == "high" else ""
            a_tick = "✓" if risk == "medium" else ""
            g_tick = "✓" if risk == "low" else ""

            formatted_table.append([
                Paragraph(str(sr), cell_style),
                Paragraph(str(name), cell_style),
                # Paragraph(f"INR {loss}", cell_style),
                Paragraph(f"INR {format_inr(loss)}", cell_style),
                Paragraph(r_tick, tick_style),
                Paragraph(a_tick, tick_style),
                Paragraph(g_tick, tick_style),
            ])

        col_widths = [
            width * 0.07,
            width * 0.38,
            width * 0.20,
            width * 0.11,
            width * 0.11,
            width * 0.13,
        ]

        table = Table(formatted_table, colWidths=col_widths, repeatRows=1)

        style_commands = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A5F")),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CBD5E1")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (3, 1), (-1, -1), "CENTER"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]

        # Color entire R, A, G columns
        style_commands += [
            ("BACKGROUND", (3, 1), (3, -1), colors.HexColor("#FECACA")),  # Red
            ("BACKGROUND", (4, 1), (4, -1), colors.HexColor("#FEF3C7")),  # Amber
            ("BACKGROUND", (5, 1), (5, -1), colors.HexColor("#D1FAE5")),  # Green
        ]

        table.setStyle(TableStyle(style_commands))

        story.append(table)

        doc.build(story)
    print(f"Executive Report generated: {output_pdf}")