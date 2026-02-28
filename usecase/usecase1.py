import sys
sys.stdout.reconfigure(encoding='utf-8')
 
import os
import pandas as pd
from data_extraction.salesforce_client import run_query
from data_extraction.loaders import records_to_df, extract_nested_fields, clean_soql_dataframe
from filters.contract_filters import normalize_dates, leakage_zombies, expiring_soon_contracts
from chart_generator.matplotlib_charts import zombie_analysis_chart
from report.report_generator import build_leakage_report
from ai_chart_overview_generator.groq_overview_generator import generate_pie_label_summary, build_pie_segments
 
 
# ------------------------------------------------------------------
# Pie chart globals (module-level constants, these never change)
# ------------------------------------------------------------------
 
PIE_LABELS = [
    "Active Contracts",
    "Leakage Zombies",
    "Expiring Soon"
]
PIE_COLORS = ["#88E788", "#FA5053", "#FFEE8C"]
 
 
def run(sf, base_output_dir):
    # ----------------------------------------------------------------
    # 1. Create this usecase's own subfolder inside base_output_dir
    # ----------------------------------------------------------------
    output_dir = os.path.join(base_output_dir, "usecase_1")
    os.makedirs(output_dir, exist_ok=True)
 
    today = pd.Timestamp.today().normalize()
 
    # ----------------------------------------------------------------
    # 2. Fetch contracts and apply filters
    # ----------------------------------------------------------------
    query = """
        SELECT Id, StartDate, EndDate, Status,
               SBQQ__RenewalOpportunity__c, SBQQ__Opportunity__r.Amount
        FROM Contract
    """
    records = run_query(sf, query)
    df = records_to_df(records)
    df = normalize_dates(df, ["EndDate"])
 
    leakage_df = leakage_zombies(df)
    expiring_soon_contracts_df = expiring_soon_contracts(df)
 
    # ----------------------------------------------------------------
    # 3. Generate chart
    # ----------------------------------------------------------------
    chart_path = zombie_analysis_chart(
        df_all_contracts=df,
        df_zombie_contracts=leakage_df,
        df_expiring_soon=expiring_soon_contracts_df,
        output_path=os.path.join(output_dir, "The_Zombie_Renewal.png")
    )
 
    # ----------------------------------------------------------------
    # 4. Fetch detailed contract data for tables
    # ----------------------------------------------------------------
    detail_query = """      
        SELECT Id, Account.Name, SBQQ__Opportunity__r.Name,SBQQ__Opportunity__r.Amount, Status
        FROM Contract
    """
    records = run_query(sf, detail_query)
    df = records_to_df(records)
 
    # Extract nested relationship fields
    nested_mapping = {
        'Account': {'Name': 'Account Name'},
        'SBQQ__Opportunity__r': {
            'Name': 'Opportunity Name',
            'Amount': 'Opportunity Amount'
        }
    }
    df = extract_nested_fields(df, nested_mapping)
 
    # Clean and rename columns
    df = clean_soql_dataframe(
        df,
        columns_to_drop=['attributes', 'Account', 'SBQQ__Opportunity__r'],
        rename_columns={'Id': 'Contract Id'}
    )
 
    # ----------------------------------------------------------------
    # 5. Split into categories
    # ----------------------------------------------------------------
    leakage_df_details = df[df.index.isin(leakage_df.index)].copy()
    expiring_soon_df_details = df[df.index.isin(expiring_soon_contracts_df.index)].copy()
    healthy_df = df[
        ~df.index.isin(leakage_df.index) &
        ~df.index.isin(expiring_soon_contracts_df.index)
    ].copy()
 
    # ----------------------------------------------------------------
    # 6. Save Excel files
    # ----------------------------------------------------------------
    leakage_df_details.to_excel(
        os.path.join(output_dir, "zombie_leakage_contracts.xlsx"), index=False
    )
    expiring_soon_df_details.to_excel(
        os.path.join(output_dir, "warning_subscriptions.xlsx"), index=False
    )
    healthy_df.to_excel(
        os.path.join(output_dir, "healthy_subscriptions.xlsx"), index=False
    )
 
    # ----------------------------------------------------------------
    # 7. Build table data for PDF
    # ----------------------------------------------------------------
    zombie_table_data  = [leakage_df_details.columns.tolist()]       + leakage_df_details.values.tolist()
    warning_table_data = [expiring_soon_df_details.columns.tolist()] + expiring_soon_df_details.values.tolist()
    healthy_table_data = [healthy_df.columns.tolist()]               + healthy_df.values.tolist()
 
    tables_list = [
        {
            'data':             zombie_table_data,
            'title':            f'Zombie Leakage Contracts ({len(leakage_df_details)})',
            'background_color': PIE_COLORS[1]
        },
        {
            'data':             warning_table_data,
            'title':            f'Warning Subscriptions - Expiring Soon ({len(expiring_soon_df_details)})',
            'background_color': PIE_COLORS[2]
        },
        {
            'data':             healthy_table_data,
            'title':            f'Healthy Subscriptions ({len(healthy_df)})',
            'background_color': PIE_COLORS[0]
        }
    ]
 
    # ----------------------------------------------------------------
    # 8. AI pie overview
    # ----------------------------------------------------------------
    ai_response = generate_pie_label_summary(
        labels={
            PIE_LABELS[0]: len(healthy_df),
            PIE_LABELS[1]: len(leakage_df_details),
            PIE_LABELS[2]: len(expiring_soon_df_details),
        },
        segment_filters={
            PIE_LABELS[0]: None,
            PIE_LABELS[1]: None,
            PIE_LABELS[2]: None,
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
 
    USECASE_NAME = "The_Zombie_Renewal"
 
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
    print(ai_response)
 
    pie_segments = build_pie_segments(
        ai_response,
        label_to_df_map={
            PIE_LABELS[0]: healthy_df,
            PIE_LABELS[1]: leakage_df_details,
            PIE_LABELS[2]: expiring_soon_df_details,
        },
        pie_labels=PIE_LABELS,
        pie_colors=PIE_COLORS,
    )
 
    # ----------------------------------------------------------------
    # 9. Build PDF report
    # ----------------------------------------------------------------
    build_leakage_report(
        output_pdf=os.path.join(output_dir, "The_Zombie_Renewal.pdf"),
        image_path=chart_path,
        tables_list=tables_list,
        title="The Zombie Renewal",
        intro_text=(
            f"This report highlights {len(leakage_df)} activated contracts that have "
            f"passed their end date without renewal activity or termination, "
            f"representing potential revenue leakage."
        ),
        figure_caption="Figure 1. Zombie Contracts Analysis by Age Distribution.",
        pie_segments=pie_segments
    )
 
    # ----------------------------------------------------------------
    # 10. Print file summary
    # ----------------------------------------------------------------
    print(f"\n✓ Report generated:              {os.path.join(output_dir, 'The_Zombie_Renewal.pdf')}")
    print(f"✓ Zombie Leakage Contracts ({len(leakage_df_details)}):  zombie_leakage_contracts.xlsx")
    print(f"✓ Warning Subscriptions ({len(expiring_soon_df_details)}):       warning_subscriptions.xlsx")
    print(f"✓ Healthy Subscriptions ({len(healthy_df)}):         healthy_subscriptions.xlsx")
    print("\nAll files are ready for download.")
 
    # ----------------------------------------------------------------
    # 11. Return summary for main.py
    # ----------------------------------------------------------------
    return {
        "name": "The_Zombie_Renewal",
        "records_found": len(leakage_df),
        "total_revenue": df["Opportunity Amount"].sum() - leakage_df_details["Opportunity Amount"].sum(),
        "total_loss": leakage_df_details["Opportunity Amount"].sum()
    }