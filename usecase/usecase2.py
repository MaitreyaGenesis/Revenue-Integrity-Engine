import os
import pandas as pd
from data_extraction.salesforce_client import run_query
from data_extraction.loaders import (
    records_to_df,
    extract_nested_fields_n_level
)
from chart_generator.matplotlib_charts import generate_pie_chart
from report.report_generator import build_leakage_report
from ai_chart_overview_generator.groq_overview_generator import (
    generate_pie_label_summary,
    build_pie_segments
)

PIE_LABELS = [
    'Old Revenue = New Revenue',
    'Healthy',
    'Old Revenue > New Revenue',
    'Old Revenue < New Revenue',
    'Renewal Opportunity is Null'
]

PIE_COLORS = [
    "#FFEE8C",
    "#88E788",
    "#FFC067",
    "#FF7782",
    "#69aafa"
]


def run(sf, base_output_dir):

    output_dir = os.path.join(base_output_dir, "usecase_2")
    os.makedirs(output_dir, exist_ok=True)

    # ----------------------------------------------------------
    # QUERY (Return full relationship objects)
    # ----------------------------------------------------------

    query = """
        SELECT Id, 
        Account.Name, 
        SBQQ__Opportunity__r.id,
        SBQQ__RenewalOpportunity__r.id ,
        SBQQ__Opportunity__r.SBQQ__PrimaryQuote__r.SBQQ__NetAmount__c,
        SBQQ__RenewalOpportunity__r.SBQQ__PrimaryQuote__r.SBQQ__NetAmount__c,
        SBQQ__RenewalUpliftRate__c FROM Contract
    """

    records = run_query(sf, query)
    df = records_to_df(records)

    df = df.rename(columns={
        "Id": "Contract Id",
        "SBQQ__RenewalUpliftRate__c" : "Uplift Rate"
        })

    # ----------------------------------------------------------
    # Extract nested values properly
    # ----------------------------------------------------------

    nested_mapping = {
        "SBQQ__Opportunity__r": {
            "SBQQ__PrimaryQuote__r": {
                "SBQQ__NetAmount__c": "Old Opp Amount"
            }
        },
        "SBQQ__RenewalOpportunity__r": {
            "SBQQ__PrimaryQuote__r": {
                "SBQQ__NetAmount__c": "Renewal Opp Amount"
            }
        },
        "Account": {
            "Name": "Account Name"
        }
    }


    df = extract_nested_fields_n_level(df, nested_mapping)

    renewal_none_df = df[df["Renewal Opp Amount"].isna()].copy()

    # Drop rows where required values missing
    # df = df.dropna(subset=[
    #     "SBQQ__RenewalUpliftRate__c",
    #     "Old Opportunity Amount",
    #     "New Renewal Opportunity Amount"
    # ])

    # ----------------------------------------------------------
    # Calculate Expected Renewal Value
    # ----------------------------------------------------------

    df["Expected Renewal Value"] = (
        df["Old Opp Amount"] +
        (df["Old Opp Amount"] * df["Uplift Rate"] / 100)
    )
    
    df.drop(columns=["SBQQ__Opportunity__r", "SBQQ__RenewalOpportunity__r", "Account"], inplace=True)
    
    # ----------------------------------------------------------
    # Segmentation
    # ----------------------------------------------------------

    df_oldSameAsNew = df[
        df["Old Opp Amount"] ==
        df["Renewal Opp Amount"]
    ].copy()

    df_Healthy = df[
        df["Expected Renewal Value"] ==
        df["Renewal Opp Amount"]
    ].copy()

    df_oldGreaterThanNew = df[
        df["Old Opp Amount"] >
        df["Renewal Opp Amount"]
    ].copy()

    df_oldLessThanNew = df[
        df["Old Opp Amount"] <
        df["Renewal Opp Amount"]
    ].copy()

    renewal_none_df = df[
        df["Renewal Opp Amount"].isna()
    ].copy()
    
    zombie_contract_info_df = pd.concat([df_oldSameAsNew, df_oldGreaterThanNew, df_oldLessThanNew])
        
    # ----------------------------------------------------------------
    # Save Excel files
    # ----------------------------------------------------------------
    df_Healthy.to_excel(
        os.path.join(output_dir, "healthy_orders.xlsx"), index=False
    )
    renewal_none_df.to_excel(
        os.path.join(output_dir, "renewal_none_orders.xlsx"), index=False
    )
    zombie_contract_info_df.to_excel(
        os.path.join(output_dir, "zombie_contract_info.xlsx"), index=False
    )

    # ----------------------------------------------------------
    # Chart
    # ----------------------------------------------------------

    chart_path = generate_pie_chart(
        labels=PIE_LABELS,
        values=[
            len(df_oldSameAsNew),
            len(df_Healthy),
            len(df_oldGreaterThanNew),
            len(df_oldLessThanNew),
            len(renewal_none_df)
        ],
        output_path=os.path.join(output_dir, "Lost_Uplift_Distribution.png"),
        colors=PIE_COLORS
    )

    # ----------------------------------------------------------
    # Tables
    # ----------------------------------------------------------

    tables_list = [
        {
            "data": [df_oldSameAsNew.columns.tolist()] + df_oldSameAsNew.values.tolist(),
            "title": f"Old Revenue = New Revenue ({len(df_oldSameAsNew)})",
            "background_color": PIE_COLORS[0]
        },
        {
            "data": [df_Healthy.columns.tolist()] + df_Healthy.values.tolist(),
            "title": f"Healthy Contracts ({len(df_Healthy)})",
            "background_color": PIE_COLORS[1]
        },
        {
            "data": [df_oldGreaterThanNew.columns.tolist()] + df_oldGreaterThanNew.values.tolist(),
            "title": f"Downsell Contracts ({len(df_oldGreaterThanNew)})",
            "background_color": PIE_COLORS[2]
        },
        {
            "data": [df_oldLessThanNew.columns.tolist()] + df_oldLessThanNew.values.tolist(),
            "title": f"Upsell Contracts ({len(df_oldLessThanNew)})",
            "background_color": PIE_COLORS[3]
        },
        {
            "data": [renewal_none_df.columns.tolist()] + renewal_none_df.values.tolist(),
            "title": f"Renewal Opportunity is Null ({len(renewal_none_df)})",
            "background_color": PIE_COLORS[4]
        }
    ]

    # ----------------------------------------------------------
    # AI Summary
    # ----------------------------------------------------------

    ai_response = generate_pie_label_summary(
        labels={
            PIE_LABELS[0]: len(df_oldSameAsNew),
            PIE_LABELS[1]: len(df_Healthy),
            PIE_LABELS[2]: len(df_oldGreaterThanNew),
            PIE_LABELS[3]: len(df_oldLessThanNew),
            PIE_LABELS[4]: len(renewal_none_df)
        },
        segment_filters={},
        columns=df.columns.tolist()
    )

    pie_segments = build_pie_segments(
        ai_response,
        label_to_df_map={
            PIE_LABELS[0]: df_oldSameAsNew,
            PIE_LABELS[1]: df_Healthy,
            PIE_LABELS[2]: df_oldGreaterThanNew,
            PIE_LABELS[3]: df_oldLessThanNew,
            PIE_LABELS[4]: renewal_none_df
        },
        pie_labels=PIE_LABELS,
        pie_colors=PIE_COLORS
    )

    # ----------------------------------------------------
    # Store reusable assets for category-level reports
    # ----------------------------------------------------
 
    data_chart_dir = os.path.join(base_output_dir, "Data_Chart")
    data_summary_dir = os.path.join(base_output_dir, "Data_Summary")
 
    os.makedirs(data_chart_dir, exist_ok=True)
    os.makedirs(data_summary_dir, exist_ok=True)
 
    USECASE_NAME = "The_Lost_Uplift"
 
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

    # ----------------------------------------------------------
    # Build Report
    # ----------------------------------------------------------

    build_leakage_report(
        output_pdf=os.path.join(output_dir, "Lost_Uplift_Report.pdf"),
        image_path=chart_path,
        tables_list=tables_list,
        title='The "Lost" Uplift Analysis Report',
        intro_text=(
            "This report identifies contracts eligible for renewal uplift "
            "but not renewed at the expected uplift value. "
            "It highlights revenue stagnation, downsell risk, upsell success, "
            "and contracts with no renewal opportunity created."
        ),
        figure_caption="Figure 1. Contract Renewal Revenue Outcome Distribution",
        pie_overview_intro="",
        pie_segments=pie_segments,
    )

    return {
        "name": "The_Lost_Uplift",
        "records_found": len(df),
        "total_revenue": 24000,
        "total_loss": 4000
    }