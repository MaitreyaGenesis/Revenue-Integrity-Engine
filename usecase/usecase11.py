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
    "The Broken Bundle",
    "Other Quote Lines",
]

PIE_COLORS = ["#FF7782", '#88E788']


def run(sf, base_output_dir):

    # ------------------------------------------------------------------
    # Create Usecase Folder
    # ------------------------------------------------------------------

    output_dir = os.path.join(base_output_dir, "usecase_11")
    os.makedirs(output_dir, exist_ok=True)

    today = pd.Timestamp.today().normalize()

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    query = """
    SELECT Id,
           SBQQ__Product__r.Name,
           SBQQ__Product__r.SBQQ__Component__c,
           SBQQ__RequiredBy__r.SBQQ__ProductName__c,
           SBQQ__NetPrice__c
    FROM SBQQ__QuoteLine__c
    """

    records = run_query(sf, query)
    df = records_to_df(records)

    df = extract_nested_fields(
        df,
        {
            'SBQQ__Product__r': {
                'Name': 'Product Name',
                'SBQQ__Component__c': 'Product Component'
            },
            'SBQQ__RequiredBy__r': {
                'SBQQ__ProductName__c': 'Required By Product Name'
            }
        }
    )

    df = df.rename(columns={
        "Id": "Quote Line ID",
        "SBQQ__NetPrice__c": "Net Price",
    })

    df = df.drop(columns=["SBQQ__Product__r", "SBQQ__RequiredBy__r"])

    # ------------------------------------------------------------------
    # Apply Filters
    # ------------------------------------------------------------------

    overall_filter = {
        "Product Component": {"=": True},
    }

    filtered_df = apply_filters(filters=overall_filter, df=df)

    required_by_product_filter = {
        "Required By Product Name": {"isna": True}
    }

    required_by_product_present_filter = {
        "Required By Product Name": {"notna": True}
    }

    required_by_product_not_present_df = apply_filters(
        filters=required_by_product_filter,
        df=filtered_df
    )

    required_by_product_present_df = apply_filters(
        filters=required_by_product_present_filter,
        df=filtered_df
    )

    # ------------------------------------------------------------------
    # Generate Pie Chart
    # ------------------------------------------------------------------

    chart_path = generate_pie_chart(
        labels=PIE_LABELS,
        values=[
            len(required_by_product_not_present_df),
            len(required_by_product_present_df)
        ],
        output_path=os.path.join(output_dir, "The_Broken_Bundle.png"),
        colors=PIE_COLORS
    )

    assert os.path.exists(chart_path), "Pie chart image was not generated"

    # ------------------------------------------------------------------
    # Save Excel Files
    # ------------------------------------------------------------------

    required_by_product_not_present_df.to_excel(
        os.path.join(output_dir, "broken_bundle_line_items.xlsx"),
        index=False
    )

    required_by_product_present_df.to_excel(
        os.path.join(output_dir, "other_quote_lines.xlsx"),
        index=False
    )

    # ------------------------------------------------------------------
    # Prepare Tables
    # ------------------------------------------------------------------

    broken_bundle_table = (
        [required_by_product_not_present_df.columns.tolist()] +
        required_by_product_not_present_df.values.tolist()
    )

    others_table = (
        [required_by_product_present_df.columns.tolist()] +
        required_by_product_present_df.values.tolist()
    )

    tables_list = [
        {
            "data": broken_bundle_table,
            "title": f"The Broken Bundle ({len(required_by_product_not_present_df)})",
            "background_color": PIE_COLORS[0]
        },
        {
            "data": others_table,
            "title": f"Other Quote Lines ({len(required_by_product_present_df)})",
            "background_color": PIE_COLORS[1]
        },
    ]

    # ------------------------------------------------------------------
    # AI Summary
    # ------------------------------------------------------------------

    ai_response = generate_pie_label_summary(
        labels={
            PIE_LABELS[0]: len(required_by_product_not_present_df),
            PIE_LABELS[1]: len(required_by_product_present_df),
        },
        segment_filters={
            PIE_LABELS[0]: required_by_product_filter,
            PIE_LABELS[1]: required_by_product_present_filter
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

    USECASE_NAME = "The_Broken_Bundle"

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
            PIE_LABELS[0]: required_by_product_not_present_df,
            PIE_LABELS[1]: required_by_product_present_df,
        },
        pie_labels=PIE_LABELS,
        pie_colors=PIE_COLORS
    )

    pie_overview_intro = ""

    # ------------------------------------------------------------------
    # Build Report
    # ------------------------------------------------------------------

    build_leakage_report(
        output_pdf=os.path.join(output_dir, "The_Broken_Bundle.pdf"),
        image_path=chart_path,
        tables_list=tables_list,
        title="The Broken Bundle Analysis Report",
        intro_text=(
            f"This report identifies cases where a bundle component (e.g., Support) was sold independently at a price lower than the approved standalone or bundled rate."
            f" Such “broken bundles” violate predefined bundle pricing logic and discount guardrails, potentially leading to margin erosion and revenue leakage. These instances require review to ensure adherence to pricing governance and bundling policies."
        ),
        figure_caption="Figure 1. Distribution of Subscriptions by Pricing and Duration Categories",
        pie_overview_intro=pie_overview_intro,
        pie_segments=pie_segments,
    )

    return {
        "name": "The_Broken_Bundle",
        "records_found": len(required_by_product_not_present_df),
        "total_revenue": df["Net Price"].sum() - required_by_product_not_present_df["Net Price"].sum(),
        "total_loss": required_by_product_not_present_df["Net Price"].sum()
    }