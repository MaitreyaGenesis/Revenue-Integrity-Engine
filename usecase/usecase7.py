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
    "Zero Quantity Line Items",
    "Other Line Items"
]

PIE_COLORS = ["#FF7782", '#88E788']


def run(sf, base_output_dir):

    # ------------------------------------------------------------------
    # Create Usecase Folder
    # ------------------------------------------------------------------

    output_dir = os.path.join(base_output_dir, "usecase_7")
    os.makedirs(output_dir, exist_ok=True)

    today = pd.Timestamp.today().normalize()

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    query = """
    SELECT Id, SBQQ__Product__c, SBQQ__Quantity__c, SBQQ__Contract__c, 
           SBQQ__StartDate__c, SBQQ__EndDate__c, SBQQ__NetPrice__c, 
           SBQQ__RenewalPrice__c, SBQQ__TerminatedDate__c 
    FROM SBQQ__Subscription__c
    """

    records = run_query(sf, query)
    df = records_to_df(records)
    df = df.rename(columns={
        "Id": "Subscription ID",
        "SBQQ__Product__c": "Product ID",
        "SBQQ__Quantity__c": "Quantity",
        "SBQQ__Contract__c": "Contract ID",
        "SBQQ__StartDate__c": "Start Date",
        "SBQQ__EndDate__c": "End Date",
        "SBQQ__NetPrice__c": "Net Price",
        "SBQQ__RenewalPrice__c": "Renewal Price",
        "SBQQ__TerminatedDate__c": "Terminated Date"
    })

    zero_quantity_filter = {
        "Quantity": {"=": 0.0},
        "Terminated Date": {"isna": True}
    }

    zero_quantity_df = apply_filters(filters=zero_quantity_filter, df=df)
    other_line_items_df = df[
        ~df["Subscription ID"].isin(zero_quantity_df["Subscription ID"])
    ]

    # ------------------------------------------------------------------
    # Generate Pie Chart
    # ------------------------------------------------------------------

    chart_path = generate_pie_chart(
        labels=PIE_LABELS,
        values=[len(zero_quantity_df), len(df) - len(zero_quantity_df)],
        output_path=os.path.join(output_dir, "Zero_Quantity_Line.png"),
        colors=PIE_COLORS
    )

    assert os.path.exists(chart_path), "Pie chart image was not generated"

    # ------------------------------------------------------------------
    # Save DataFrames
    # ------------------------------------------------------------------

    zero_quantity_df.to_excel(
        os.path.join(output_dir, "zero_quantity_line_items.xlsx"),
        index=False
    )

    other_line_items_df.to_excel(
        os.path.join(output_dir, "other_line_items.xlsx"),
        index=False
    )

    # ------------------------------------------------------------------
    # Prepare Tables for PDF
    # ------------------------------------------------------------------

    zero_quantity_table = (
        [zero_quantity_df.columns.tolist()]
        + zero_quantity_df.values.tolist()
    )

    other_line_items_table = (
        [other_line_items_df.columns.tolist()]
        + other_line_items_df.values.tolist()
    )

    tables_list = [
        {
            "data": zero_quantity_table,
            "title": f"Zero Quantity Line Items ({len(zero_quantity_df)})",
            "background_color": PIE_COLORS[0]
        },
        {
            "data": other_line_items_table,
            "title": f"Other Line Items ({len(other_line_items_df)})",
            "background_color": PIE_COLORS[1]
        }
    ]

    # ------------------------------------------------------------------
    # AI Overview
    # ------------------------------------------------------------------

    ai_response = generate_pie_label_summary(
        labels={
            PIE_LABELS[0]: len(zero_quantity_df),
            PIE_LABELS[1]: len(other_line_items_df)
        },
        segment_filters={
            PIE_LABELS[0]: zero_quantity_filter,
            PIE_LABELS[1]: ""
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

    USECASE_NAME = "Zero_Quantity_Line"

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
            PIE_LABELS[0]: zero_quantity_df,
            PIE_LABELS[1]: other_line_items_df
        },
        pie_labels=PIE_LABELS,
        pie_colors=PIE_COLORS
    )

    pie_overview_intro = ""

    # ------------------------------------------------------------------
    # Build PDF Report
    # ------------------------------------------------------------------

    build_leakage_report(
        output_pdf=os.path.join(
            output_dir,
            "Zero_Quantity_Line.pdf"
        ),
        image_path=chart_path,
        tables_list=tables_list,
        title="Zero Quantity Line Analysis Report",
        intro_text=(
            f"This report highlights contract line items where the quantity is recorded as zero, often as a result of cancelled or adjusted amendments. Although these lines are no longer commercially relevant, they remain on the contract and continue to clutter"
            f"the renewal structure. Their presence can complicate renewal calculations, reduce clarity in reporting, and increase the risk of processing inaccuracies during automated renewals."
        ),
        figure_caption=(
            "Figure 1. Distribution of Zero Quantity Line Items vs. Other Line Items"
        ),
        pie_overview_intro=pie_overview_intro,
        pie_segments=pie_segments
    )

    # ------------------------------------------------------------------
    # Final Output
    # ------------------------------------------------------------------

    print("\n✓ Report generated successfully")
    print(f"✓ PDF: {output_dir}/Zero_Quantity_Line.pdf")
    print(f"✓ Zero Quantity Line Items ({len(zero_quantity_df)}): zero_quantity_line_items.xlsx")
    print(f"✓ Other Line Items ({len(other_line_items_df)}): other_line_items.xlsx")
    print("✓ Pie chart saved")
    print("\nAll files are ready for download.")

    return {
        "name": "Zero_Quantity_Line",
        "records_found": len(zero_quantity_df),
        "total_revenue": df["Net Price"].sum() - zero_quantity_df["Net Price"].sum(),
        "total_loss": zero_quantity_df["Net Price"].sum()
    }