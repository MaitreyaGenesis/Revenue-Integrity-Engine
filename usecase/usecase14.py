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
    "Unsynced Primary Quotes",
    "Healthy Quotes",
]

PIE_COLORS = ["#FF7782", '#88E788']


def run(sf, base_output_dir):

    # ------------------------------------------------------------------
    # Create Usecase Folder
    # ------------------------------------------------------------------

    output_dir = os.path.join(base_output_dir, "usecase_14")
    os.makedirs(output_dir, exist_ok=True)

    today = pd.Timestamp.today().normalize()

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    query = """
    SELECT Id, Name, SBQQ__NetAmount__c, SBQQ__Opportunity2__r.Amount
    FROM SBQQ__Quote__c
    WHERE SBQQ__Primary__c = TRUE AND SBQQ__Opportunity2__c != NULL
    """

    records = run_query(sf, query)
    df = records_to_df(records)

    df = extract_nested_fields(
        df,
        {
            "SBQQ__Opportunity2__r": {
                "Amount": "Opportunity Amount"
            }
        }
    )

    df = df.rename(columns={
        "Id": "Quote ID",
        "Name": "Quote Name",
        "SBQQ__NetAmount__c": "Net Amount",
        "SBQQ__SubscriptionType__c": "Subscription Type"
    })

    df.drop(columns=["SBQQ__Opportunity2__r"], inplace=True)

    # ------------------------------------------------------------------
    # Split Data
    # ------------------------------------------------------------------

    healthy_df = df[
        df["Net Amount"] == df["Opportunity Amount"]
    ].copy()

    unsynced_primary_quote_df = df[
        df["Net Amount"] != df["Opportunity Amount"]
    ].copy()

    # ------------------------------------------------------------------
    # Generate Pie Chart
    # ------------------------------------------------------------------

    chart_path = generate_pie_chart(
        labels=PIE_LABELS,
        values=[
            len(unsynced_primary_quote_df),
            len(healthy_df)
        ],
        output_path=os.path.join(output_dir, "Unsynced_Primary_Quote.png"),
        colors=PIE_COLORS
    )

    # ------------------------------------------------------------------
    # Save Excel Files
    # ------------------------------------------------------------------

    unsynced_primary_quote_df.to_excel(
        os.path.join(output_dir, "unsynced_primary_quotes.xlsx"),
        index=False
    )

    healthy_df.to_excel(
        os.path.join(output_dir, "healthy_quote.xlsx"),
        index=False
    )

    # ------------------------------------------------------------------
    # Prepare Tables
    # ------------------------------------------------------------------

    unsynced_primary_quote_table = (
        [unsynced_primary_quote_df.columns.tolist()] +
        unsynced_primary_quote_df.values.tolist()
    )

    healthy_table = (
        [healthy_df.columns.tolist()] +
        healthy_df.values.tolist()
    )

    tables_list = [
        {
            "data": unsynced_primary_quote_table,
            "title": f"Unsynced Primary Quotes ({len(unsynced_primary_quote_df)})",
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
            PIE_LABELS[0]: len(unsynced_primary_quote_df),
            PIE_LABELS[1]: len(healthy_df)
        },
        segment_filters={
            PIE_LABELS[0]: {"df": '''df["Net Amount"] != df["Opportunity Amount"]''', "query": query},
            PIE_LABELS[1]: {"df": '''df["Net Amount"] == df["Opportunity Amount"]''', "query": query},
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

    USECASE_NAME = "Unsynced_Primary_Quote"

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
            PIE_LABELS[0]: unsynced_primary_quote_df,
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
        output_pdf=os.path.join(output_dir, "Unsynced_Primary_Quote.pdf"),
        image_path=chart_path,
        tables_list=tables_list,
        title="Unsynced Primary Quotes Analysis Report",
        intro_text=(
            f"This report identifies opportunities where the designated Primary Quote is not synchronized with the Opportunity Amount, resulting in data inconsistencies."
            f"Such misalignment can distort pipeline visibility, revenue forecasting, and performance reporting. These cases require review to ensure accurate quote-to-opportunity synchronization and reliable financial projections."
        ),
        figure_caption="Figure 1. Distribution of Unsynced Primary Quotes",
        pie_overview_intro=pie_overview_intro,
        pie_segments=pie_segments,
    )

    return {
        "name": "Unsynced_Primary_Quote",
        "records_found": len(unsynced_primary_quote_df),
        "total_revenue":  df["Net Amount"].sum() - unsynced_primary_quote_df["Net Amount"].sum(),
        "total_loss":  unsynced_primary_quote_df["Net Amount"].sum()
    }   