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
    "Healthy Quotes",
    "Bypass Approval Quotes",
    "Incorrect Discount Quotes"
]

PIE_COLORS = ["#88E788", "#FFCC77", "#FA5053"]


def run(sf, base_output_dir):

    # ------------------------------------------------------------------
    # Create Usecase Folder
    # ------------------------------------------------------------------

    output_dir = os.path.join(base_output_dir, "usecase_4")
    os.makedirs(output_dir, exist_ok=True)

    today = pd.Timestamp.today().normalize()

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    query = """
    SELECT Id, SBQQ__AverageCustomerDiscount__c, SBQQ__Opportunity2__r.Name, 
    SBQQ__Opportunity2__r.Amount, SBQQ__TotalCustomerDiscountAmount__c 
    FROM SBQQ__Quote__c
    """

    records = run_query(sf, query)
    df = records_to_df(records)
    df = extract_nested_fields(
        df,
        {'SBQQ__Opportunity2__r': {'Name': 'Opportunity Name', 'Amount': 'Opportunity Amount'}}
    )
    df = df.drop(columns=["SBQQ__Opportunity2__r"])
    df = df.rename(columns={
        "SBQQ__AverageCustomerDiscount__c": "Average Customer Discount",
        "Id": "Quote ID",
        "SBQQ__TotalCustomerDiscountAmount__c": "Discount Amount"
    })

    # ------------------------------------------------------------------
    # Apply Threshold Hugger Filters
    # ------------------------------------------------------------------

    healthy_filters = {
        "Average Customer Discount": {">=": 0.0, "<=": 19.0},
        "Average Customer Discount": {">=": 20.0, "<=": 100.0},
    }

    bypass_approval_filters = {
        "Average Customer Discount": {">=": 19.01, "<=": 19.99},
    }

    incorrect_discount_filters = {
        "Average Customer Discount": {"<": 0.0},
    }

    healthy_df = apply_filters(filters=healthy_filters, df=df)
    bypass_approval_df = apply_filters(filters=bypass_approval_filters, df=df)
    incorrect_discount_df = apply_filters(filters=incorrect_discount_filters, df=df)

    # ------------------------------------------------------------------
    # Generate Pie Chart
    # ------------------------------------------------------------------

    chart_path = generate_pie_chart(
        labels=[
            "Healthy Quotes",
            "Bypass Approval Quotes",
            "Incorrect Discount Quotes"
        ],
        values=[
            len(healthy_df),
            len(bypass_approval_df),
            len(incorrect_discount_df)
        ],
        output_path=os.path.join(
            output_dir,
            "The_Threshold_Hugger.png"
        ),
        colors=["#88E788", '#FFCC77', "#FA5053"]
    )

    assert os.path.exists(chart_path), "Pie chart image was not generated"

    # ------------------------------------------------------------------
    # Save DataFrames
    # ------------------------------------------------------------------

    healthy_df.to_excel(
        os.path.join(output_dir, "healthy_quotes.xlsx"),
        index=False
    )

    bypass_approval_df.to_excel(
        os.path.join(output_dir, "bypass_approval_quotes.xlsx"),
        index=False
    )

    incorrect_discount_df.to_excel(
        os.path.join(output_dir, "incorrect_discount_quotes.xlsx"),
        index=False
    )

    # ------------------------------------------------------------------
    # Prepare Tables for PDF
    # ------------------------------------------------------------------

    healthy_table = (
        [healthy_df.columns.tolist()]
        + healthy_df.values.tolist()
    )

    bypass_approval_table = (
        [bypass_approval_df.columns.tolist()]
        + bypass_approval_df.values.tolist()
    )

    incorrect_discount_table = (
        [incorrect_discount_df.columns.tolist()]
        + incorrect_discount_df.values.tolist()
    )

    tables_list = [
        {
            "data": healthy_table,
            "title": f"Healthy Quotes ({len(healthy_df)})",
            "background_color": "#88E788"
        },
        {
            "data": bypass_approval_table,
            "title": f"Bypass Approval Quotes ({len(bypass_approval_df)})",
            "background_color": "#FFCC77"
        },
        {
            "data": incorrect_discount_table,
            "title": f"Incorrect Discount Quotes ({len(incorrect_discount_df)})",
            "background_color": "#FA5053"
        }
    ]

    # ------------------------------------------------------------------
    # Pie Chart Overview Content
    # ------------------------------------------------------------------

    pie_overview_intro = (
        f"This pie chart illustrates pricing behavior relative to Finance approval thresholds. "
        f"Out of {len(df)} total quotes, the distribution highlights deals priced exactly at the "
        f"100% approval trigger, a pattern commonly referred to as threshold hugging."
    )

    ai_response = generate_pie_label_summary(
        labels={
            PIE_LABELS[0]: len(healthy_df),
            PIE_LABELS[1]: len(bypass_approval_df),
            PIE_LABELS[2]: len(incorrect_discount_df)
        },
        segment_filters={
            PIE_LABELS[0]: healthy_filters,
            PIE_LABELS[1]: bypass_approval_filters,
            PIE_LABELS[2]: incorrect_discount_filters
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

    USECASE_NAME = "The_Threshold_Hugger"

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
            PIE_LABELS[0]: healthy_df,
            PIE_LABELS[1]: bypass_approval_df
        },
        pie_labels=PIE_LABELS,
        pie_colors=PIE_COLORS
    )

    # ------------------------------------------------------------------
    # Build PDF Report
    # ------------------------------------------------------------------

    build_leakage_report(
        output_pdf=os.path.join(
            output_dir,
            "The_Threshold_Hugger.pdf"
        ),
        image_path=chart_path,
        tables_list=tables_list,
        title="Threshold Hugger Pricing Analysis Report",
        intro_text=(
            f"This report identifies deals priced just below the formal approval threshold, where discounts are consistently set marginally under the trigger point for Finance review. "
            f"Such “threshold hugging” behavior may indicate deliberate structuring to bypass oversight controls. Over time, this pattern can erode margin integrity and weaken governance safeguards."
        ),
        figure_caption=(
            "Figure 1. Distribution of Threshold Hugger vs Non-Threshold Hugger Quotes "
            "based on Finance approval thresholds."
        ),
        pie_overview_intro=pie_overview_intro,
        pie_segments=pie_segments
    )

    # ------------------------------------------------------------------
    # Final Output
    # ------------------------------------------------------------------

    print("\n✓ Report generated successfully")
    print(f"✓ PDF: {output_dir}/The_Threshold_Hugger.pdf")
    print("✓ Pie chart saved")
    print("\nAll files are ready for download.")

    return {
        "name": "The_Threshold_Hugger",
        "records_found": len(bypass_approval_df),
        "total_revenue": df["Opportunity Amount"].sum() - bypass_approval_df["Opportunity Amount"].sum(),
        "total_loss": bypass_approval_df["Discount Amount"].sum()
    }