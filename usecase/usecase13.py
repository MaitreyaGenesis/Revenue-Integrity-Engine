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
    "Missing Billing Frequency Quote Lines",
    "Ohter Quote Lines",
]

PIE_COLORS = ["#FF7782", '#88E788']


def run(sf, base_output_dir):

    # ------------------------------------------------------------------
    # Create Usecase Folder
    # ------------------------------------------------------------------

    output_dir = os.path.join(base_output_dir, "usecase_13")
    os.makedirs(output_dir, exist_ok=True)

    today = pd.Timestamp.today().normalize()

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    query = """
    SELECT Id, Name, SBQQ__Quote__c, SBQQ__NetTotal__c,
           SBQQ__ProductName__c, SBQQ__BillingFrequency__c,
           SBQQ__SubscriptionType__c
    FROM SBQQ__QuoteLine__c
    """

    records = run_query(sf, query)
    df = records_to_df(records)

    df = df.rename(columns={
        "Id": "Quote Line Item ID",
        "Name": "Quote Line Item Name",
        "SBQQ__Quote__c": "Quote ID",
        "SBQQ__NetTotal__c": "Net Total",
        "SBQQ__ProductName__c": "Product Name",
        "SBQQ__BillingFrequency__c": "Billing Frequency",
        "SBQQ__SubscriptionType__c": "Subscription Type"
    })

    df.drop("Quote ID", axis=1, inplace=True)

    # ------------------------------------------------------------------
    # Filters
    # ------------------------------------------------------------------

    missing_billing_frequency_filter = {
        "Subscription Type": {"=": "Renewable"},
        "Billing Frequency": {"isna": True}
    }

    healthy_filter = {
        "Subscription Type": {"=": "Renewable"},
        "Billing Frequency": {"notna": True}
    }

    missing_billing_frequency_df = apply_filters(
        filters=missing_billing_frequency_filter,
        df=df
    )

    healthy_df = apply_filters(
        df=df,
        filters=healthy_filter
    )

    # ------------------------------------------------------------------
    # Generate Pie Chart
    # ------------------------------------------------------------------

    chart_path = generate_pie_chart(
        labels=PIE_LABELS,
        values=[
            len(missing_billing_frequency_df),
            len(healthy_df)
        ],
        output_path=os.path.join(output_dir, "Missing_Billing_Frequency.png"),
        colors=PIE_COLORS
    )

    # ------------------------------------------------------------------
    # Save Excel Files
    # ------------------------------------------------------------------

    missing_billing_frequency_df.to_excel(
        os.path.join(output_dir, "missing_billing_frequency_quote_lines.xlsx"),
        index=False
    )

    healthy_df.to_excel(
        os.path.join(output_dir, "healthy_quote_lines.xlsx"),
        index=False
    )

    # ------------------------------------------------------------------
    # Prepare Tables
    # ------------------------------------------------------------------

    missing_billing_frequency_table = (
        [missing_billing_frequency_df.columns.tolist()] +
        missing_billing_frequency_df.values.tolist()
    )

    healthy_table = (
        [healthy_df.columns.tolist()] +
        healthy_df.values.tolist()
    )

    tables_list = [
        {
            "data": missing_billing_frequency_table,
            "title": f"Discount Without Approval ({len(missing_billing_frequency_df)})",
            "background_color": PIE_COLORS[0]
        },
        {
            "data": healthy_table,
            "title": f"Healthy Quotes ({len(healthy_df)})",
            "background_color": PIE_COLORS[1]
        }
    ]

    # ------------------------------------------------------------------
    # AI Summary
    # ------------------------------------------------------------------

    ai_response = generate_pie_label_summary(
        labels={
            PIE_LABELS[0]: len(missing_billing_frequency_df),
            PIE_LABELS[1]: len(healthy_df)
        },
        segment_filters={
            PIE_LABELS[0]: missing_billing_frequency_filter,
            PIE_LABELS[1]: healthy_filter,
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

    USECASE_NAME = "Missing_Billing_Frequency"

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

    print(ai_response)
    print("\nAI-Generated Pie Chart Label Summary:\n")

    pie_segments = build_pie_segments(
        ai_response,
        label_to_df_map={
            PIE_LABELS[0]: missing_billing_frequency_df,
            PIE_LABELS[1]: healthy_df,
        },
        pie_labels=PIE_LABELS,
        pie_colors=PIE_COLORS
    )

    pie_overview_intro = ""

    # ------------------------------------------------------------------
    # Build Report
    # ------------------------------------------------------------------

    build_leakage_report(
        output_pdf=os.path.join(output_dir, "Missing_Billing_Frequency.pdf"),
        image_path=chart_path,
        tables_list=tables_list,
        title="Missing Billing Frequency Analysis Report",
        intro_text=(
            f"This report identifies subscription products that were added without a defined Billing Frequency, creating gaps in required billing configuration."
            f"Such omissions can lead to downstream invoicing errors, revenue recognition issues, and operational delays. These cases require review to ensure accurate billing setup and compliance with subscription governance standards."
        ),
        figure_caption="Figure 1. Distribution of Quote Line Items with Missing Billing Frequency",
        pie_overview_intro=pie_overview_intro,
        pie_segments=pie_segments,
    )

    return {
        "name": "Missing_Billing_Frequency",
        "records_found": len(missing_billing_frequency_df),
        "total_revenue": df["Net Total"].sum() - missing_billing_frequency_df["Net Total"].sum(),
        "total_loss": missing_billing_frequency_df["Net Total"].sum()
    }