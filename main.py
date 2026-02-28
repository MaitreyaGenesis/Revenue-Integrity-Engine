import sys
sys.stdout.reconfigure(encoding='utf-8')

import os
import importlib
import traceback
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
import time

from data_extraction.salesforce_client import get_salesforce_client
from chart_generator.matplotlib_charts import generate_pie_chart, bar_chart_executive
from report.report_generator import build_leakage_report,build_executive_report


# ------------------------------------------------------------
# Categories of leakage with their associated use cases (for executive summary)
# ------------------------------------------------------------

CATEGORY_MAPPING = {
    "Renewal & Retention Leakage": [
        "The_Zombie_Renewal",
        "The_Co_Term_Failure",
        "The_Lost_Uplift"
    ],

    "Pricing & Discount Integrity": [
        "The_Threshold_Hugger",
        "The_Broken_Bundle"
    ],

    "Billing & Usage Leakage": [
        "The_Ghost_Order",
        "The_Eternal_Trial",
        "Expired_Subscription_Not_Renewed"
    ],

    "Master Data & Setup Gaps": [
        "The_Inactive_Sale",
        "Missing_Tax_Status",
        "Zero_Quantity_Line"
    ],

    "Process & Governance Leakage": [
        "Discount_Without_Approval",
        "Renewal_Without_Renewal_Quote",
        "Unsynced_Primary_Quote",
        "Missing_Billing_Frequency"
    ]
}



from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image,
    PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch


def build_category_from_central_assets(category_name, base_output_dir, usecase_list):

    chart_dir = os.path.join(base_output_dir, "Data_Chart")
    summary_dir = os.path.join(base_output_dir, "Data_Summary")

    category_dir = os.path.join(
        base_output_dir,
        category_name.replace(" ", "_").replace("&", "and")
    )
    os.makedirs(category_dir, exist_ok=True)

    output_pdf = os.path.join(
        category_dir,
        f"{category_name.replace(' ', '_').replace('&','and')}.pdf"
    )

    # ---------- CLEAN MARGINS ----------
    doc = SimpleDocTemplate(
        output_pdf,
        rightMargin=40,
        leftMargin=40,
        topMargin=50,
        bottomMargin=40
    )

    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    heading_style = styles["Heading2"]
    normal_style = styles["Normal"]

    normal_style.fontSize = 10
    normal_style.leading = 14

    elements = []

    # ---------- CATEGORY TITLE ----------
    elements.append(Paragraph(category_name, title_style))
    elements.append(Spacer(1, 0.4 * inch))

    first_section = True

    for usecase in usecase_list:

        chart_path = os.path.join(chart_dir, f"{usecase}.png")
        summary_path = os.path.join(summary_dir, f"{usecase}.txt")

        if not os.path.exists(chart_path):
            print(f"⚠ Chart missing for {usecase}")
            continue

        if not os.path.exists(summary_path):
            print(f"⚠ Summary missing for {usecase}")
            continue

        print(f"✓ Adding {usecase} to {category_name}")

        # Add PageBreak only AFTER first section
        if not first_section:
            elements.append(PageBreak())

        first_section = False

        # ---------- USECASE TITLE ----------
        elements.append(
            Paragraph(usecase.replace("_", " "), heading_style)
        )
        elements.append(Spacer(1, 0.3 * inch))

        # ---------- FIXED HEIGHT (500px equivalent) ----------
        FIXED_HEIGHT = 300  # ~500px in points

        img = Image(chart_path)

        # Calculate proportional width
        ratio = FIXED_HEIGHT / img.drawHeight
        img.drawHeight = FIXED_HEIGHT
        img.drawWidth = img.drawWidth * ratio

        # If width exceeds page width, scale down again
        if img.drawWidth > doc.width:
            width_ratio = doc.width / img.drawWidth
            img.drawWidth = doc.width
            img.drawHeight = img.drawHeight * width_ratio

        img.hAlign = "CENTER"

        elements.append(img)
        elements.append(Spacer(1, 0.3 * inch))

        # ---------- SUMMARY ----------
        with open(summary_path, "r", encoding="utf-8") as f:
            summary_text = f.read()

        # formatted = summary_text.replace("\n", "<br/>")
        # elements.append(Paragraph(formatted, normal_style))
        
        # ---------- SUMMARY CLEAN FORMAT ----------
        with open(summary_path, "r", encoding="utf-8") as f:
            raw_text = f.read()

        clean_lines = []

        for line in raw_text.splitlines():
            line = line.strip()

            if line.startswith("title:"):
                clean_lines.append(
                    f"<b>{line.replace('title:', '').strip()}</b>"
                )

            elif line.startswith("description:"):
                clean_lines.append(
                    line.replace("description:", "").strip()
                )

        # Join cleaned lines
        formatted = "<br/><br/>".join(clean_lines)

        elements.append(Paragraph(formatted, normal_style))

    doc.build(elements)

    print(f"✓ Category Report Built: {category_name}")

# ------------------------------------------------------------
# Risk Classification Logic
# ------------------------------------------------------------

def classify_risk(count):
    if count > 100:
        return "High"
    elif count > 25:
        return "Medium"
    else:
        return "Low"


def main():

    # ------------------------------------------------------------
    # 1. Load environment variables
    # ------------------------------------------------------------
    load_dotenv()

    # ------------------------------------------------------------
    # 2. Create Salesforce client once
    # ------------------------------------------------------------
    print("Connecting to Salesforce...")
    sf = get_salesforce_client(
        os.getenv("SF_USERNAME"),
        os.getenv("SF_PASSWORD"),
        os.getenv("SF_TOKEN")
    )
    print("Salesforce connection established.\n")

    # ------------------------------------------------------------
    # 3. Create base output directory (timestamped)
    # ------------------------------------------------------------
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_output_dir = os.path.join("output", timestamp)
    os.makedirs(base_output_dir, exist_ok=True)
    print(f"Base output directory: {base_output_dir}\n")

    # ------------------------------------------------------------
    # 4. Auto-discover usecase modules
    # ------------------------------------------------------------
    usecase_dir = os.path.join(os.path.dirname(__file__), "usecase")

    usecase_modules = sorted([
        f[:-3] for f in os.listdir(usecase_dir)
        if f.startswith("usecase") and f.endswith(".py") and f != "__init__.py"
    ])

    print(f"Discovered {len(usecase_modules)} use case(s):")
    print(", ".join(usecase_modules))
    print("=" * 60)

    # ------------------------------------------------------------
    # 5. Execute each usecase
    # ------------------------------------------------------------
    results = []

    for module_name in usecase_modules:
        print("Timeout: Waiting for 60 seconds...")
        time.sleep(60)
        print(f"\n▶ Running: {module_name}")
        print("-" * 60)

        try:
            module = importlib.import_module(f"usecase.{module_name}")

            if not hasattr(module, "run"):
                raise AttributeError(f"{module_name} has no run() function")

            result = module.run(sf, base_output_dir)

            results.append({
                "module": module_name,
                "name": result.get("name", module_name),
                "records_found": result.get("records_found", 0),
                "loss": result.get("total_loss", 0),
                "revenue": result.get("total_revenue", 0),
                "status": "success"
            })

            print(f"✓ Completed | Records found: {result.get('records_found', 0)}")

        except Exception as e:
            results.append({
                "module": module_name,
                "name": module_name,
                "records_found": 0,
                "loss": 0,
                "revenue": 0,
                "status": "failed",
                "error": str(e)
            })
            print(f"✗ Failed: {e}")
            traceback.print_exc()

    # ------------------------------------------------------------
    # 6. Execution Summary
    # ------------------------------------------------------------
    successful = [r for r in results if r["status"] == "success"]
    failed = [r for r in results if r["status"] == "failed"]

    print("\n" + "=" * 60)
    print("EXECUTION SUMMARY")
    print("=" * 60)
    print(f"Total run:   {len(results)}")
    print(f"Successful:  {len(successful)}")
    print(f"Failed:      {len(failed)}")

    # ------------------------------------------------------------
    # 7. Build Revenue Loss Report
    # ------------------------------------------------------------

    if successful:

        summary_df = pd.DataFrame(successful)

        # Ensure numeric
        summary_df["loss"] = pd.to_numeric(summary_df["loss"], errors="coerce").fillna(0)
        summary_df["revenue"] = pd.to_numeric(summary_df["revenue"], errors="coerce").fillna(0)

        # Sort by highest loss
        summary_df = summary_df.sort_values(by="loss", ascending=False).reset_index(drop=True)

        # Serial number
        summary_df["S.NO."] = summary_df.index + 1

        # Risk classification logic
        def classify_loss_risk(loss):
            if loss > 100000:
                return "High"
            elif loss > 50000:
                return "Medium"
            else:
                return "Low"

        summary_df["Risk Category"] = summary_df["loss"].apply(classify_loss_risk)

        # KPI calculations
        total_loss = summary_df["loss"].sum()
        total_revenue = summary_df["revenue"].sum()
        loss_percentage = (total_loss / total_revenue * 100) if total_revenue else 0

        kpis = [
            total_loss,
            loss_percentage,
        ]

        # Prepare bar chart data
        usecase_names = summary_df["name"].tolist()
        losses = summary_df["loss"].tolist()
        risk = summary_df["Risk Category"].tolist()

        bar_chart_path = os.path.join(base_output_dir, "loss_bar_chart.png")

        bar_chart_path = bar_chart_executive(
            usecase_names=summary_df["name"].tolist(),
            losses=summary_df["loss"].tolist(),
            output_path=bar_chart_path
        )

        # Prepare table data
        table_data = [
            ["S.NO.", "Dimension", "Total Loss (INR)", "Risk Category"]
        ]

        for _, row in summary_df.iterrows():
            table_data.append([
                row["S.NO."],
                row["name"],
                f"{row['loss']:,.2f}",
                row["Risk Category"]
            ])

        # Generate Revenue Loss Report
        build_executive_report(
            output_pdf=os.path.join(base_output_dir, "Executive_Revenue_Loss_Report.pdf"),
            usecase_names=usecase_names,
            losses=losses,
            kpi_values=kpis,
            table_data=table_data,
            chart_path=bar_chart_path
        )


        print("\n✓ Revenue Loss Report generated successfully.")

    # ------------------------------------------------------------
    # 8. Category Reports (Optional)
    # ------------------------------------------------------------

    if successful:
        for category_name, usecase_list in CATEGORY_MAPPING.items():
            build_category_from_central_assets(
                category_name,
                base_output_dir,
                usecase_list
            )

    print("\n" + "=" * 60)
    print(f"All output saved under: {base_output_dir}")
    print("=" * 60)

# =============================================================
if __name__ == "__main__":
    main()