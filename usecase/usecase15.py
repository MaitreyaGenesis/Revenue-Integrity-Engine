import os
import pandas as pd
from dotenv import load_dotenv
from data_extraction.salesforce_client import get_salesforce_client, run_query
from data_extraction.loaders import records_to_df, extract_nested_fields, extract_nested_fields_n_level
from filters.contract_filters import apply_filters
from chart_generator.matplotlib_charts import generate_pie_chart, bar_chart
from report.report_generator import build_leakage_report
from ai_chart_overview_generator.groq_overview_generator import generate_pie_label_summary, build_pie_segments

# ------------------------------------------------------------------
# Constants (Allowed at module level)
# ------------------------------------------------------------------

PIE_LABELS = [
    "Expired Subscription Not Renewed ",
    "Other Subscriptions",
]

PIE_COLORS = ["#FF7782", '#88E788']


def run(sf, base_output_dir):

    # ------------------------------------------------------------------
    # Create Usecase Folder
    # ------------------------------------------------------------------

    output_dir = os.path.join(base_output_dir, "usecase_15")
    os.makedirs(output_dir, exist_ok=True)

    today = pd.Timestamp.today().normalize()

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    query = """
    SELECT id, Name, SBQQ__SubscriptionEndDate__c, SBQQ__NetPrice__c,
           SBQQ__Contract__r.SBQQ__Opportunity__r.Name,
           SBQQ__Contract__r.SBQQ__Quote__r.SBQQ__Type__c
    FROM SBQQ__Subscription__c
    """

    records = run_query(sf, query)
    df = records_to_df(records)

    nested_mapping = {
        "SBQQ__Contract__r": {
            "SBQQ__Opportunity__r": {
                "Name": "Opportunity Name"
            },
            "SBQQ__Quote__r": {
                "SBQQ__Type__c": "Quote Type"
            }
        }
    }

    df = df.rename(columns={
        "id": "Subscription ID",
        "SBQQ__SubscriptionEndDate__c": "Subscription End Date",
        "Name": "Subscription Name",
        "SBQQ__NetPrice__c" : "Net Price"
    })

    df["Subscription End Date"] = pd.to_datetime(
        df["Subscription End Date"],
        errors="coerce"
    )

    df = extract_nested_fields_n_level(df, nested_mapping)

    df.drop(columns=["SBQQ__Contract__r"], inplace=True)

    df = df[df["Subscription End Date"].notna()]

    # ------------------------------------------------------------------
    # Filters
    # ------------------------------------------------------------------

    unhealthy_filter = {
        "Subscription End Date": {"<": today},
        "Quote Type": {"=": "Renewal"}
    }

    healthy_filter = {
        "Subscription End Date": {"<": today},
        "Quote Type": {"!=": "Renewal"}
    }

    unhealthy_df = apply_filters(filters=unhealthy_filter, df=df)
    healthy_df = apply_filters(df=df, filters=healthy_filter)

    # ------------------------------------------------------------------
    # Generate Pie Chart
    # ------------------------------------------------------------------

    chart_path = generate_pie_chart(
        labels=PIE_LABELS,
        values=[len(unhealthy_df), len(healthy_df)],
        output_path=os.path.join(output_dir, "Expired_Subscription_Not_Renewed.png"),
        colors=PIE_COLORS
    )

    # ------------------------------------------------------------------
    # Save Excel Files
    # ------------------------------------------------------------------

    unhealthy_df.to_excel(
        os.path.join(output_dir, "expired_subscription_not_renewed_subscriptions.xlsx"),
        index=False
    )

    healthy_df.to_excel(
        os.path.join(output_dir, "healthy_subscriptions.xlsx"),
        index=False
    )

    # ------------------------------------------------------------------
    # Prepare Tables
    # ------------------------------------------------------------------

    unhealthy_table = (
        [unhealthy_df.columns.tolist()] +
        unhealthy_df.values.tolist()
    )

    healthy_table = (
        [healthy_df.columns.tolist()] +
        healthy_df.values.tolist()
    )

    tables_list = [
        {
            "data": unhealthy_table,
            "title": f"Expired Subscription Not Renewed ({len(unhealthy_df)})",
            "background_color": PIE_COLORS[0]
        },
        {
            "data": healthy_table,
            "title": f"Healthy Subscriptions ({len(healthy_df)})",
            "background_color": PIE_COLORS[1]
        }
    ]

    # ------------------------------------------------------------------
    # AI Summary
    # ------------------------------------------------------------------

    ai_response = generate_pie_label_summary(
        labels={
            PIE_LABELS[0]: len(unhealthy_df),
            PIE_LABELS[1]: len(healthy_df)
        },
        segment_filters={
            PIE_LABELS[0]: unhealthy_filter,
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

    USECASE_NAME = "Expired_Subscription_Not_Renewed"

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
            PIE_LABELS[0]: unhealthy_df,
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
        output_pdf=os.path.join(output_dir, "Expired_Subscription_Not_Renewed.pdf"),
        image_path=chart_path,
        tables_list=tables_list,
        title="Expired Subscription Not Renewed Analysis Report",
        intro_text=(
            f"This report identifies subscriptions where the End Date has passed but no corresponding Renewal Quote was generated. Such cases indicate potential lapses in renewal management and revenue continuity, increasing the risk of churn and missed recurring revenue."
            f"These instances require timely review to ensure proactive renewal action and protection of subscription revenue streams."
        ),
        figure_caption="Figure 1. Distribution of Expired Subscriptions Not Renewed",
        pie_overview_intro=pie_overview_intro,
        pie_segments=pie_segments,
    )

    return {
        "name": "Expired_Subscription_Not_Renewed",
        "records_found": len(unhealthy_df),
        "total_revenue": df["Net Price"].sum() - unhealthy_df["Net Price"].sum(),
        "total_loss": unhealthy_df["Net Price"].sum()
    }