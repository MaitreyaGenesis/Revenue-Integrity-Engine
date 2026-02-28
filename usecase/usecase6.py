import os
import pandas as pd
from dotenv import load_dotenv
from data_extraction.salesforce_client import get_salesforce_client, run_query
from data_extraction.loaders import records_to_df, extract_nested_fields
from filters.contract_filters import apply_filters
from chart_generator.matplotlib_charts import generate_pie_chart
from report.report_generator import build_leakage_report
from ai_chart_overview_generator.groq_overview_generator import generate_pie_label_summary, build_pie_segments

# ------------------------------------------------------------------
# Constants (Allowed at module level)
# ------------------------------------------------------------------

PIE_LABELS = [
    "Null Tax Exempt Status",
    "Pending Tax Exempt Status",
    "Non-Exempt Tax Status",
    "Exempt Tax Status",
    "Not Applicable Tax Status"
]

PIE_COLORS = ["#FF7782", '#88E788', '#FFC067', '#FFEE8C', '#69aafa']


def run(sf, base_output_dir):

    # ------------------------------------------------------------------
    # Create Usecase Folder
    # ------------------------------------------------------------------

    output_dir = os.path.join(base_output_dir, "usecase_6")
    os.makedirs(output_dir, exist_ok=True)

    today = pd.Timestamp.today().normalize()

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    query = """
    SELECT Id, Name, OrderNumber, TotalAmount, Tax_Exempt_Status__c, Status FROM Order
    """

    records = run_query(sf, query)
    df = records_to_df(records)
    df = df.rename(columns={
        "Tax_Exempt_Status__c": "Tax Exempt Status",
    })

    null_status_filter = {
        "Tax Exempt Status": {"isna": True},
        "TotalAmount": {">": 0},
    }
    pending_status_filter = {
        "Tax Exempt Status": {"=": "Pending"},
        "TotalAmount": {">": 0},
    }
    non_exempt_status_filter = {
        "Tax Exempt Status": {"=": "Non-Exempt"},
        "TotalAmount": {">": 0},
    }
    exempt_status_filter = {
        "Tax Exempt Status": {"=": "Exempt"},
        "TotalAmount": {">": 0},
    }
    not_applicable_status_filter = {
        "Tax Exempt Status": {"=": "Not Applicable"},
        "TotalAmount": {">": 0},
    }

    null_status_df = apply_filters(filters=null_status_filter, df=df)
    pending_status_df = apply_filters(filters=pending_status_filter, df=df)
    non_exempt_status_df = apply_filters(filters=non_exempt_status_filter, df=df)
    exempt_status_df = apply_filters(filters=exempt_status_filter, df=df)
    not_applicable_status_df = apply_filters(filters=not_applicable_status_filter, df=df)

    # ------------------------------------------------------------------
    # Generate Pie Chart
    # ------------------------------------------------------------------

    chart_path = generate_pie_chart(
        labels=PIE_LABELS,
        values=[
            len(null_status_df),
            len(pending_status_df),
            len(non_exempt_status_df),
            len(exempt_status_df),
            len(not_applicable_status_df)
        ],
        output_path=os.path.join(output_dir, "Missing_Tax_Status.png"),
        colors=PIE_COLORS
    )

    assert os.path.exists(chart_path), "Pie chart image was not generated"

    # ------------------------------------------------------------------
    # Save DataFrames
    # ------------------------------------------------------------------

    null_status_df.to_excel(
        os.path.join(output_dir, "null_tax_exempt_status.xlsx"),
        index=False
    )

    pending_status_df.to_excel(
        os.path.join(output_dir, "pending_tax_exempt_status.xlsx"),
        index=False
    )

    non_exempt_status_df.to_excel(
        os.path.join(output_dir, "non_exempt_tax_exempt_status.xlsx"),
        index=False
    )

    exempt_status_df.to_excel(
        os.path.join(output_dir, "exempt_tax_exempt_status.xlsx"),
        index=False
    )

    not_applicable_status_df.to_excel(
        os.path.join(output_dir, "not_applicable_tax_exempt_status.xlsx"),
        index=False
    )

    # ------------------------------------------------------------------
    # Prepare Tables for PDF
    # ------------------------------------------------------------------

    null_status_table = [null_status_df.columns.tolist()] + null_status_df.values.tolist()
    pending_status_table = [pending_status_df.columns.tolist()] + pending_status_df.values.tolist()
    non_exempt_status_table = [non_exempt_status_df.columns.tolist()] + non_exempt_status_df.values.tolist()
    exempt_status_table = [exempt_status_df.columns.tolist()] + exempt_status_df.values.tolist()
    not_applicable_status_table = [not_applicable_status_df.columns.tolist()] + not_applicable_status_df.values.tolist()

    tables_list = [
        {
            "data": null_status_table,
            "title": f"Null Tax Exempt Status ({len(null_status_df)})",
            "background_color": PIE_COLORS[0]
        },
        {
            "data": pending_status_table,
            "title": f"Pending Tax Exempt Status ({len(pending_status_df)})",
            "background_color": PIE_COLORS[1]
        },
        {
            "data": non_exempt_status_table,
            "title": f"Non-Exempt Tax Status ({len(non_exempt_status_df)})",
            "background_color": PIE_COLORS[2]
        },
        {
            "data": exempt_status_table,
            "title": f"Exempt Tax Status ({len(exempt_status_df)})",
            "background_color": PIE_COLORS[3]
        },
        {
            "data": not_applicable_status_table,
            "title": f"Not Applicable Tax Status ({len(not_applicable_status_df)})",
            "background_color": PIE_COLORS[4]
        }
    ]

    # ------------------------------------------------------------------
    # Pie Chart Overview Content
    # ------------------------------------------------------------------

    ai_response = generate_pie_label_summary(
        labels={
            PIE_LABELS[0]: len(null_status_df),
            PIE_LABELS[1]: len(pending_status_df),
            PIE_LABELS[2]: len(non_exempt_status_df),
            PIE_LABELS[3]: len(exempt_status_df),
            PIE_LABELS[4]: len(not_applicable_status_df)
        },
        segment_filters={
            PIE_LABELS[0]: null_status_filter,
            PIE_LABELS[1]: pending_status_filter,
            PIE_LABELS[2]: non_exempt_status_filter,
            PIE_LABELS[3]: exempt_status_filter,
            PIE_LABELS[4]: not_applicable_status_filter
        },
        columns=df.columns.tolist()
    )

        # ----------------------------------------------------
    # Store reusable assets for category-level reports
    # ----------------------------------------------------

    data_chart_dir = os.path.join(base_output_dir, "Data_Chart")
    data_summary_dir = os.path.join(base_output_dir, "Data_Summary")

    os.makedirs(data_chart_dir, exist_ok=True)
    os.makedirs(data_summary_dir, exist_ok=True)

    USECASE_NAME = "Missing_Tax_Status"

    import shutil
    shutil.copy(chart_path, os.path.join(data_chart_dir, f"{USECASE_NAME}.png"))

    # -------- SAFELY FORMAT AI RESPONSE --------

    if isinstance(ai_response, list):

        formatted_lines = []

        for item in ai_response:
            if isinstance(item, dict):
                # If dictionary → format nicely
                for key, value in item.items():
                    formatted_lines.append(f"{key}: {value}")
            else:
                formatted_lines.append(str(item))

        summary_text = "\n\n".join(formatted_lines)

    elif isinstance(ai_response, dict):
        summary_text = "\n\n".join(
            f"{k}: {v}" for k, v in ai_response.items()
        )

    else:
        summary_text = str(ai_response)

    # -------- WRITE SUMMARY FILE --------

    with open(
        os.path.join(data_summary_dir, f"{USECASE_NAME}.txt"),
        "w",
        encoding="utf-8"
    ) as f:
        f.write(summary_text)

    print("\nAI-Generated Pie Chart Label Summary:\n")

    pie_segments = build_pie_segments(
        ai_response,
        label_to_df_map={
            PIE_LABELS[0]: null_status_df,
            PIE_LABELS[1]: pending_status_df,
            PIE_LABELS[2]: non_exempt_status_df,
            PIE_LABELS[3]: exempt_status_df,
            PIE_LABELS[4]: not_applicable_status_df
        },
        pie_labels=PIE_LABELS,
        pie_colors=PIE_COLORS
    )

    pie_overview_intro = ""

    # ------------------------------------------------------------------
    # Build PDF Report
    # ------------------------------------------------------------------

    build_leakage_report(
        output_pdf=os.path.join(output_dir, "Missing_Tax_Status.pdf"),
        image_path=chart_path,
        tables_list=tables_list,
        title="Missing Tax Status Analysis Report",
        intro_text=(
            f"This report identifies {len(null_status_df)} orders where the Tax_Exempt_Status "
            f"is missing (NULL) despite a positive order amount. Such orders represent a critical financial and compliance risk, as the ERP system rejects transactions without a defined tax status, directly delaying invoice creation and revenue recognition."
        ),
        figure_caption=(
            "Figure 1. Distribution of Orders by Tax Exempt Status, highlighting the critical issue of missing tax status for orders with positive amounts."
        ),
        pie_overview_intro=pie_overview_intro,
        pie_segments=pie_segments
    )

    # ------------------------------------------------------------------
    # Final Output
    # ------------------------------------------------------------------

    print("\n✓ Report generated successfully")
    print(f"✓ PDF: {output_dir}/Missing_Tax_Status.pdf")
    print("✓ Pie chart saved")
    print("\nAll files are ready for download.")

    return {
        "name": "Missing_Tax_Status",
        "records_found": len(null_status_df),
        "total_revenue": df["TotalAmount"].sum() - null_status_df["TotalAmount"].sum(),
        "total_loss": null_status_df["TotalAmount"].sum() * 0.46
    }