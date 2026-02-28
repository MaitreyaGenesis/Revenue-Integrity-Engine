import os
import pandas as pd
from dotenv import load_dotenv
from data_extraction.salesforce_client import get_salesforce_client, run_query
from data_extraction.loaders import records_to_df
from filters.contract_filters import apply_filters
from chart_generator.matplotlib_charts import generate_pie_chart
from report.report_generator import build_leakage_report
from ai_chart_overview_generator.groq_overview_generator import generate_pie_label_summary, build_pie_segments

# ------------------------------------------------------------------
# Constants (Allowed at module level)
# ------------------------------------------------------------------

PIE_LABELS = [
    "Renewal Without Renewal Quote",
    "Renewal With Renewal Quote",
]

PIE_COLORS = ["#FF7782", '#88E788']


def run(sf, base_output_dir):

    # ------------------------------------------------------------------
    # Create Usecase Folder
    # ------------------------------------------------------------------

    output_dir = os.path.join(base_output_dir, "usecase_10")
    os.makedirs(output_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Query 1: Renewal With Renewal Quote
    # ------------------------------------------------------------------

    query = """
    SELECT Id, Name, AccountId, StageName, CloseDate
    FROM Opportunity
    WHERE Name LIKE 'Renewal%'
    AND Id IN (
        SELECT SBQQ__Opportunity2__c
        FROM SBQQ__Quote__c
        WHERE SBQQ__Type__c = 'Renewal'
        AND SBQQ__Opportunity2__c != NULL
    )
    """

    records = run_query(sf, query)
    df = records_to_df(records)

    df = df.rename(columns={
        "Id": "Opportunity ID",
        "Name": "Opportunity Name",
        "AccountId": "Account ID",
        "StageName": "Stage Name",
        "CloseDate": "Close Date",
    })

    df['Close Date'] = pd.to_datetime(df['Close Date'])

    # ------------------------------------------------------------------
    # Query 2: Renewal Without Renewal Quote
    # ------------------------------------------------------------------

    query2 = """
    SELECT Id, Name, AccountId, StageName, CloseDate
    FROM Opportunity
    WHERE Name LIKE 'Renewal%'
    AND Id NOT IN (
        SELECT SBQQ__Opportunity2__c
        FROM SBQQ__Quote__c
        WHERE SBQQ__Type__c = 'Renewal'
        AND SBQQ__Opportunity2__c != NULL
    )
    """

    records2 = run_query(sf, query2)
    df2 = records_to_df(records2)

    df2 = df2.rename(columns={
        "Id": "Opportunity ID",
        "Name": "Opportunity Name",
        "AccountId": "Account ID",
        "StageName": "Stage Name",
        "CloseDate": "Close Date",
    })

    # ------------------------------------------------------------------
    # Generate Pie Chart
    # ------------------------------------------------------------------

    chart_path = generate_pie_chart(
        labels=PIE_LABELS,
        values=[len(df2), len(df)],
        output_path=os.path.join(output_dir, "Renewal_Without_Renewal_Quote.png"),
        colors=PIE_COLORS
    )

    # ------------------------------------------------------------------
    # Save Excel Files
    # ------------------------------------------------------------------

    df.to_excel(
        os.path.join(output_dir, "renewal_with_renewal_quote_opportunities.xlsx"),
        index=False
    )

    df2.to_excel(
        os.path.join(output_dir, "renewal_without_renewal_quote_opportunities.xlsx"),
        index=False
    )

    # ------------------------------------------------------------------
    # Prepare Tables
    # ------------------------------------------------------------------

    renewal_without_quote_table = (
        [df2.columns.to_list()] +
        df2.values.tolist()
    )

    renewal_with_quote_table = (
        [df.columns.to_list()] +
        df.values.tolist()
    )

    tables_list = [
        {
            "data": renewal_without_quote_table,
            "title": f"Renewal Without Renewal Quote ({len(df2)})",
            "background_color": PIE_COLORS[0]
        },
        {
            "data": renewal_with_quote_table,
            "title": f"Renewal With Renewal Quote ({len(df)})",
            "background_color": PIE_COLORS[1]
        }
    ]

    # ------------------------------------------------------------------
    # AI Summary
    # ------------------------------------------------------------------

    ai_response = generate_pie_label_summary(
        labels={
            PIE_LABELS[0]: len(df2),
            PIE_LABELS[1]: len(df)
        },
        segment_filters={
            PIE_LABELS[0]: query2,
            PIE_LABELS[1]: query,
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

    USECASE_NAME = "Renewal_Without_Renewal_Quote"

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
            PIE_LABELS[0]: df2,
            PIE_LABELS[1]: df,
        },
        pie_labels=PIE_LABELS,
        pie_colors=PIE_COLORS
    )

    pie_overview_intro = ""

    # ------------------------------------------------------------------
    # Build Report
    # ------------------------------------------------------------------

    build_leakage_report(
        output_pdf=os.path.join(output_dir, "Renewal_Without_Renewal_Quote.pdf"),
        image_path=chart_path,
        tables_list=tables_list,
        title="The Renewal Without Renewal Quote Analysis Report",
        intro_text=(
            f"This report identifies renewal opportunities that were created without generating an associated renewal quote, thereby bypassing the standard renewal pricing process. Such cases indicate a breakdown in pricing governance and approval controls, increasing the risk of inconsistent pricing, missed uplifts, or potential revenue leakage."
            f"These opportunities require review to ensure compliance with established renewal policies."
        ),
        figure_caption="Figure 1. Distribution of Renewal Opportunities With and Without Renewal Quotes",
        pie_overview_intro=pie_overview_intro,
        pie_segments=pie_segments,
    )

    return {
        "name": "Renewal_Without_Renewal_Quote",
        "records_found": len(df2),
        "total_revenue": None,
        "total_loss": None
    }