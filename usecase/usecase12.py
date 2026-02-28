import os
import pandas as pd
from dotenv import load_dotenv
from data_extraction.salesforce_client import get_salesforce_client, run_query
from data_extraction.loaders import records_to_df, extract_nested_fields
from filters.contract_filters import apply_filters
from chart_generator.matplotlib_charts import generate_pie_chart, bar_chart
from report.report_generator import build_leakage_report
from ai_chart_overview_generator.groq_overview_generator import generate_pie_label_summary, build_pie_segments

# ------------------------------------------------------------------
# Constants (Allowed at module level)
# ------------------------------------------------------------------

PIE_LABELS = [
    "Discount Without Approval",
    "Other Quotes",
]

PIE_COLORS = ["#FF7782", '#88E788']


def run(sf, base_output_dir):

    # ------------------------------------------------------------------
    # Create Usecase Folder
    # ------------------------------------------------------------------

    output_dir = os.path.join(base_output_dir, "usecase_12")
    os.makedirs(output_dir, exist_ok=True)

    today = pd.Timestamp.today().normalize()

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    query = """
    SELECT Id,Name,SBQQ__CustomerDiscount__c,SBQQ__Status__c,SBQQ__NetAmount__c,
           SBQQ__Opportunity2__c,CreatedDate
    FROM SBQQ__Quote__c
    """

    records = run_query(sf, query)
    df = records_to_df(records)

    df = df.rename(columns={
        "Id": "Quote ID",
        "Name": "Quote Name",
        "SBQQ__CustomerDiscount__c": "Customer Discount",
        "SBQQ__Status__c": "Status",
        "SBQQ__NetAmount__c" : "Net Amount",
        "SBQQ__Opportunity2__c": "Opportunity ID",
        "CreatedDate": "Created Date"
    })

    # ------------------------------------------------------------------
    # Apply Filters
    # ------------------------------------------------------------------

    discount_without_approval_filter = {
        "Customer Discount": {">": 20},
        "Status": {"!=": "Approved"}
    }

    discount_without_approval_df = apply_filters(
        filters=discount_without_approval_filter,
        df=df
    )

    healthy_quotes_df = df[
        (
            (df["Customer Discount"] < 20) |
            (df["Customer Discount"].isna())
        )
        &
        (df["Status"] != "Approved")
    ]

    # ------------------------------------------------------------------
    # Generate Pie Chart
    # ------------------------------------------------------------------

    chart_path = generate_pie_chart(
        labels=PIE_LABELS,
        values=[
            len(discount_without_approval_df),
            len(healthy_quotes_df)
        ],
        output_path=os.path.join(output_dir, "Discount_Without_Approval.png"),
        colors=PIE_COLORS
    )

    # ------------------------------------------------------------------
    # Save Excel Files
    # ------------------------------------------------------------------

    discount_without_approval_df.to_excel(
        os.path.join(output_dir, "discount_without_approval_quotes.xlsx"),
        index=False
    )

    healthy_quotes_df.to_excel(
        os.path.join(output_dir, "healthy_quotes.xlsx"),
        index=False
    )

    # ------------------------------------------------------------------
    # Prepare Tables
    # ------------------------------------------------------------------

    discount_without_approval_table = (
        [discount_without_approval_df.columns.tolist()] +
        discount_without_approval_df.values.tolist()
    )

    healthy_quotes_table = (
        [healthy_quotes_df.columns.tolist()] +
        healthy_quotes_df.values.tolist()
    )

    tables_list = [
        {
            "data": discount_without_approval_table,
            "title": f"Discount Without Approval ({len(discount_without_approval_df)})",
            "background_color": PIE_COLORS[0]
        },
        {
            "data": healthy_quotes_table,
            "title": f"Healthy Quotes ({len(healthy_quotes_df)})",
            "background_color": PIE_COLORS[1]
        }
    ]

    # ------------------------------------------------------------------
    # AI Summary
    # ------------------------------------------------------------------

    ai_response = generate_pie_label_summary(
        labels={
            PIE_LABELS[0]: len(discount_without_approval_df),
            PIE_LABELS[1]: len(healthy_quotes_df)
        },
        segment_filters={
            PIE_LABELS[0]: discount_without_approval_filter,
            PIE_LABELS[1]: {
                "Custom Filter": "(df['Customer Discount'] < 20) |(df['Customer Discount'].isna())&df['Status'] != 'Approved'"
            }
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

    USECASE_NAME = "Discount_Without_Approval"

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
            PIE_LABELS[0]: discount_without_approval_df,
            PIE_LABELS[1]: healthy_quotes_df,
        },
        pie_labels=PIE_LABELS,
        pie_colors=PIE_COLORS
    )

    pie_overview_intro = ""

    # ------------------------------------------------------------------
    # Build Report
    # ------------------------------------------------------------------

    build_leakage_report(
        output_pdf=os.path.join(output_dir, "Discount_Without_Approval.pdf"),
        image_path=chart_path,
        tables_list=tables_list,
        title="Discount Without Approval Analysis Report",
        intro_text=(
            f"This report identifies quotes where discounts exceed the permitted threshold but lack documented approval."
            f" Such instances bypass established approval workflows and pricing governance controls, increasing the risk of margin erosion and non-compliant deal execution. These cases require review to ensure adherence to discount authorization policies."
        ),
        figure_caption="Figure 1. Distribution of Quotes with Unauthorized Discounts",
        pie_overview_intro=pie_overview_intro,
        pie_segments=pie_segments,
    )

    return {
        "name": "Discount_Without_Approval",
        "records_found": len(discount_without_approval_df),
        "total_revenue": df["Net Amount"].sum() - discount_without_approval_df["Net Amount"].sum(),
        "total_loss": discount_without_approval_df["Net Amount"].sum()
    }