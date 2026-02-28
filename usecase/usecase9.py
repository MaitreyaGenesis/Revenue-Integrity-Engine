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
    "Co-Term Failure Contracts",
    "Other Contracts"
]

PIE_COLORS = ["#FF7782", '#88E788']


def run(sf, base_output_dir):

    # ------------------------------------------------------------------
    # Create Usecase Folder
    # ------------------------------------------------------------------

    output_dir = os.path.join(base_output_dir, "usecase_9")
    os.makedirs(output_dir, exist_ok=True)

    today = pd.Timestamp.today().normalize()

    # ------------------------------------------------------------------
    # Query 1: Accounts with Multiple Contracts
    # ------------------------------------------------------------------

    query = """
    SELECT AccountId accId, COUNT(Id) contractCount
    FROM Contract
    GROUP BY AccountId
    HAVING COUNT(Id) > 1
    """

    grouped_results = run_query(sf, query)

    account_ids = [
        record['accId']
        for record in grouped_results
    ]

    if not account_ids:
        print("No Accounts found with more than 1 Contract")
        df_contracts = pd.DataFrame()
        co_term_failure_contracts = pd.DataFrame()
        df_other_contracts = pd.DataFrame()

    else:

        account_ids_str = ",".join([f"'{aid}'" for aid in account_ids])

        contract_query = f"""
        SELECT Id, AccountId, StartDate, EndDate, Status
        FROM Contract
        WHERE AccountId IN ({account_ids_str})
        ORDER BY AccountId, StartDate
        """

        contracts = run_query(sf, contract_query)
        df_contracts = records_to_df(contracts)

        df_contracts['StartDate'] = pd.to_datetime(df_contracts['StartDate'])
        df_contracts['EndDate'] = pd.to_datetime(df_contracts['EndDate'])

        df_contracts.rename(columns={
            "Id": "Contract ID"
        }, inplace=True)

        co_term_failure_account_ids = set()

        for account_id in account_ids:
            df_account_contracts = (
                df_contracts[df_contracts['AccountId'] == account_id]
                .sort_values('EndDate')
            )

            first_end = df_account_contracts['EndDate'].iloc[0]
            last_end = df_account_contracts['EndDate'].iloc[-1]

            if (last_end - first_end).days <= 90:
                co_term_failure_account_ids.add(account_id)

        co_term_failure_contracts = df_contracts[
            df_contracts['AccountId'].isin(co_term_failure_account_ids)
        ]

        df_other_contracts = df_contracts[
            ~df_contracts['Contract ID'].isin(
                co_term_failure_contracts['Contract ID']
            )
        ]

    print(f"Found {len(co_term_failure_contracts)} contracts with co-term failure.")
    print(co_term_failure_contracts)

    # ------------------------------------------------------------------
    # Generate Pie Chart
    # ------------------------------------------------------------------

    chart_path = generate_pie_chart(
        labels=PIE_LABELS,
        values=[
            len(co_term_failure_contracts),
            len(df_contracts) - len(co_term_failure_contracts)
        ],
        output_path=os.path.join(output_dir, "The_Co_Term_Failure.png"),
        colors=PIE_COLORS
    )

    assert os.path.exists(chart_path), "Pie chart image was not generated"

    # ------------------------------------------------------------------
    # Save Excel Files
    # ------------------------------------------------------------------

    co_term_failure_contracts.to_excel(
        os.path.join(output_dir, "co_term_failure_contracts.xlsx"),
        index=False
    )

    df_other_contracts.to_excel(
        os.path.join(output_dir, "other_contracts.xlsx"),
        index=False
    )

    # ------------------------------------------------------------------
    # Prepare Tables
    # ------------------------------------------------------------------

    co_term_failure_contract_table = (
        [co_term_failure_contracts.columns.tolist()]
        + co_term_failure_contracts.values.tolist()
    )

    other_contracts_table = (
        [df_other_contracts.columns.tolist()]
        + df_other_contracts.values.tolist()
    )

    tables_list = [
        {
            "data": co_term_failure_contract_table,
            "title": f"Co-Term Failure Contracts ({len(co_term_failure_contracts)})",
            "background_color": PIE_COLORS[0]
        },
        {
            "data": other_contracts_table,
            "title": f"Other Contracts ({len(df_contracts) - len(co_term_failure_contracts)})",
            "background_color": PIE_COLORS[1]
        }
    ]

    # ------------------------------------------------------------------
    # AI Summary
    # ------------------------------------------------------------------

    ai_response = generate_pie_label_summary(
        labels={
            PIE_LABELS[0]: len(co_term_failure_contracts),
            PIE_LABELS[1]: len(df_contracts) - len(co_term_failure_contracts),
        },
        segment_filters={
            PIE_LABELS[0]: "Contracts with co-term failure (multiple contracts for same account with end dates within 90 days)",
            PIE_LABELS[1]: "All other contracts that do not meet co-term failure criteria"
        },
        columns=df_contracts.columns.tolist(),
    )

    # ----------------------------------------------------
    # Store reusable assets for category-level reports
    # ----------------------------------------------------

    data_chart_dir = os.path.join(base_output_dir, "Data_Chart")
    data_summary_dir = os.path.join(base_output_dir, "Data_Summary")

    os.makedirs(data_chart_dir, exist_ok=True)
    os.makedirs(data_summary_dir, exist_ok=True)

    USECASE_NAME = "The_Co_Term_Failure"

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
            PIE_LABELS[0]: co_term_failure_contracts,
            PIE_LABELS[1]: df_other_contracts,
        },
        pie_labels=PIE_LABELS,
        pie_colors=PIE_COLORS
    )

    pie_overview_intro = ""

    # ------------------------------------------------------------------
    # Build Report
    # ------------------------------------------------------------------

    build_leakage_report(
        output_pdf=os.path.join(output_dir, "The_Co_Term_Failure.pdf"),
        title="The Co-Term Failure Analysis Report",
        image_path=chart_path,
        tables_list=tables_list,
        pie_overview_intro=pie_overview_intro,
        pie_segments=pie_segments
    )

    print("\n✓ Report generated successfully")
    print(f"✓ PDF: {output_dir}/The_Co_Term_Failure.pdf")
    print(f"✓ Co-Term Failure Contracts ({len(co_term_failure_contracts)}): co_term_failure_contracts.xlsx")
    print(f"✓ Other Contracts ({len(df_other_contracts)}): other_contracts.xlsx")
    print("✓ Pie chart saved")
    print("\nAll files are ready for download.")

    return {
        "name": "The_Co_Term_Failure",
        "records_found": len(co_term_failure_contracts),
        "total_revenue": None,
        "total_loss": None
    }