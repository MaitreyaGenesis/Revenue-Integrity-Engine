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
    "Eternal Trial (Zero Price, >90 Days)",
    "Zero Price Short Term",
    "Long Term Priced Contracts",
    "Short Term Priced Contracts"
]

PIE_COLORS = ["#FF7782", '#88E788', '#7799FF', '#FFCC77']


def run(sf, base_output_dir):

    # ------------------------------------------------------------------
    # Create Usecase Folder
    # ------------------------------------------------------------------

    output_dir = os.path.join(base_output_dir, "usecase_8")
    os.makedirs(output_dir, exist_ok=True)

    today = pd.Timestamp.today().normalize()

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    query = """
    SELECT Id, Name, SBQQ__NetPrice__c, SBQQ__ListPrice__c,
           SBQQ__Product__r.Name, SBQQ__Product__r.Family,
           SBQQ__StartDate__c, SBQQ__EndDate__c,
           SBQQ__Contract__r.Id, SBQQ__Contract__r.StartDate,
           SBQQ__Contract__r.EndDate, SBQQ__Contract__r.Status
    FROM SBQQ__Subscription__c
    """

    records = run_query(sf, query)
    df = records_to_df(records)
    df = extract_nested_fields(
        df,
        {
            'SBQQ__Product__r': {'Name': 'Product Name', 'Family': 'Product Family'},
            'SBQQ__Contract__r': {'Id': 'Contract Id', 'Status': 'Contract Status'}
        }
    )

    df = df.rename(columns={
        "Id": "Subscription ID",
        "Name": "Subscription Name",
        "SBQQ__ListPrice__c": "List Price",
        "SBQQ__NetPrice__c": "Net Price",
        "SBQQ__StartDate__c": "Start Date",
        "SBQQ__EndDate__c": "End Date",
    })

    # Ensure datetime columns
    df['Start Date'] = pd.to_datetime(df['Start Date'])
    df['End Date'] = pd.to_datetime(df['End Date'])
    df['Contract Duration'] = df['End Date'] - df['Start Date']

    df = df.drop(columns=["SBQQ__Product__r", "SBQQ__Contract__r", "Contract Id", "Contract Status"])

    eternal_trial_filter = {
        "Product Family": {"!=": "Marketing"},
        "Net Price": {"=": 0},
        "Contract Duration": {">": pd.Timedelta(days=90)}
    }

    zero_price_short_term_filter = {
        "Net Price": {"=": 0},
        "Contract Duration": {"<=": pd.Timedelta(days=90)}
    }

    long_term_priced_contract_filter = {
        "Net Price": {"!=": 0},
        "Contract Duration": {">": pd.Timedelta(days=90)}
    }

    short_term_priced_contract_filter = {
        "Net Price": {"!=": 0},
        "Contract Duration": {"<=": pd.Timedelta(days=90)}
    }

    eternal_trial_df = apply_filters(filters=eternal_trial_filter, df=df)
    zero_price_short_term_df = apply_filters(filters=zero_price_short_term_filter, df=df)
    long_term_priced_contract_df = apply_filters(filters=long_term_priced_contract_filter, df=df)
    short_term_priced_contract_df = apply_filters(filters=short_term_priced_contract_filter, df=df)

    # ------------------------------------------------------------------
    # Generate Charts
    # ------------------------------------------------------------------

    chart_path = generate_pie_chart(
        labels=PIE_LABELS,
        values=[
            len(eternal_trial_df),
            len(zero_price_short_term_df),
            len(long_term_priced_contract_df),
            len(short_term_priced_contract_df)
        ],
        output_path=os.path.join(output_dir, "The_Eternal_Trial.png"),
        colors=PIE_COLORS
    )

    bar_chart_path = bar_chart(
        eternal_trial_df,
        "Product Family",
        os.path.join(output_dir, "eternal_trial_by_product_family_bar_chart.png"),
    )

    assert os.path.exists(chart_path), "Pie chart image was not generated"

    # ------------------------------------------------------------------
    # Save Excel Files
    # ------------------------------------------------------------------

    eternal_trial_df.to_excel(
        os.path.join(output_dir, "eternal_trial_line_items.xlsx"),
        index=False
    )

    zero_price_short_term_df.to_excel(
        os.path.join(output_dir, "zero_price_short_term_line_items.xlsx"),
        index=False
    )

    long_term_priced_contract_df.to_excel(
        os.path.join(output_dir, "long_term_priced_contract_line_items.xlsx"),
        index=False
    )

    short_term_priced_contract_df.to_excel(
        os.path.join(output_dir, "short_term_priced_contract_line_items.xlsx"),
        index=False
    )

    eternal_trial_df.drop(columns=["Start Date", "End Date"], inplace=True)
    zero_price_short_term_df.drop(columns=["Start Date", "End Date"], inplace=True)
    long_term_priced_contract_df.drop(columns=["Start Date", "End Date", "Contract Duration"], inplace=True)
    short_term_priced_contract_df.drop(columns=["Start Date", "End Date", "Contract Duration"], inplace=True)

    # ------------------------------------------------------------------
    # Prepare Tables
    # ------------------------------------------------------------------

    eternal_trial_table = [eternal_trial_df.columns.tolist()] + eternal_trial_df.values.tolist()
    zero_price_short_term_table = [zero_price_short_term_df.columns.tolist()] + zero_price_short_term_df.values.tolist()
    long_term_priced_contract_table = [long_term_priced_contract_df.columns.tolist()] + long_term_priced_contract_df.values.tolist()
    short_term_priced_contract_table = [short_term_priced_contract_df.columns.tolist()] + short_term_priced_contract_df.values.tolist()

    tables_list = [
        {
            "data": eternal_trial_table,
            "title": f"Eternal Trial (Zero Price, >90 Days) ({len(eternal_trial_df)})",
            "background_color": PIE_COLORS[0]
        },
        {
            "data": zero_price_short_term_table,
            "title": f"Zero Price Short Term ({len(zero_price_short_term_df)})",
            "background_color": PIE_COLORS[1]
        },
        {
            "data": long_term_priced_contract_table,
            "title": f"Long Term Priced Contracts ({len(long_term_priced_contract_df)})",
            "background_color": PIE_COLORS[2]
        },
        {
            "data": short_term_priced_contract_table,
            "title": f"Short Term Priced Contracts ({len(short_term_priced_contract_df)})",
            "background_color": PIE_COLORS[3]
        }
    ]

    # ------------------------------------------------------------------
    # AI Summary
    # ------------------------------------------------------------------

    ai_response = generate_pie_label_summary(
        labels={
            PIE_LABELS[0]: len(eternal_trial_df),
            PIE_LABELS[1]: len(zero_price_short_term_df),
            PIE_LABELS[2]: len(long_term_priced_contract_df),
            PIE_LABELS[3]: len(short_term_priced_contract_df)
        },
        segment_filters={
            PIE_LABELS[0]: eternal_trial_filter,
            PIE_LABELS[1]: zero_price_short_term_filter,
            PIE_LABELS[2]: long_term_priced_contract_filter,
            PIE_LABELS[3]: short_term_priced_contract_filter
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

    USECASE_NAME = "The_Eternal_Trial"

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
            PIE_LABELS[0]: eternal_trial_df,
            PIE_LABELS[1]: zero_price_short_term_df,
            PIE_LABELS[2]: long_term_priced_contract_df,
            PIE_LABELS[3]: short_term_priced_contract_df
        },
        pie_labels=PIE_LABELS,
        pie_colors=PIE_COLORS
    )

    pie_overview_intro = ""

    # ------------------------------------------------------------------
    # Build Report
    # ------------------------------------------------------------------

    build_leakage_report(
        output_pdf=os.path.join(output_dir, "The_Eternal_Trial.pdf"),
        image_path=chart_path,
        tables_list=tables_list,
        title="The Eternal Trial Analysis Report",
        intro_text=(
            f"This report identifies products that were initially provisioned as free trials for a limited period but continue to remain priced at $0 well beyond the intended trial duration. Such “eternal trials” indicate "
            f"potential revenue leakage, where temporary promotional pricing was never converted to a paid subscription. These cases require review to prevent ongoing loss of billable revenue."
        ),
        figure_caption="Figure 1. Distribution of Subscriptions by Pricing and Duration Categories",
        pie_overview_intro=pie_overview_intro,
        pie_segments=pie_segments,
    )

    return {
        "name": "The_Eternal_Trial",
        "records_found": len(eternal_trial_df),
        "total_revenue": df["List Price"].sum() - eternal_trial_df["List Price"].sum(),
        "total_loss": eternal_trial_df["List Price"].sum()
    }