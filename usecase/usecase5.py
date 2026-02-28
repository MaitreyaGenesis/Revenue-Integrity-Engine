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
    "Inactive Product Sales",
    "Active Product Sales"
]

PIE_COLORS = ["#FA5053", "#88E788"]


def run(sf, base_output_dir):

    # ------------------------------------------------------------------
    # Create Usecase Folder
    # ------------------------------------------------------------------

    output_dir = os.path.join(base_output_dir, "usecase_5")
    os.makedirs(output_dir, exist_ok=True)

    today = pd.Timestamp.today().normalize()

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    query = """
    SELECT Id, SBQQ__Product__r.Name, SBQQ__Product__r.IsActive, SBQQ__Quote__r.Name 
    FROM SBQQ__QuoteLine__c
    """

    records = run_query(sf, query)
    df = records_to_df(records)
    df = extract_nested_fields(
        df,
        {
            'SBQQ__Quote__r': {'Name': 'Quote Name'},
            'SBQQ__Product__r': {'Name': 'Product Name', 'IsActive': 'Product IsActive'}
        }
    )
    df = df.drop(columns=["SBQQ__Product__r", "SBQQ__Quote__r"])
    df = df.rename(columns={
        "Id": "Quote ID",
    })

    # ------------------------------------------------------------------
    # Apply Filters
    # ------------------------------------------------------------------

    filters = {
        "Product IsActive": {"=": False}
    }

    inactive_sale_df = apply_filters(filters=filters, df=df)

    active_sale_df = df.loc[
        ~df.index.isin(inactive_sale_df.index)
    ].copy()

    # ------------------------------------------------------------------
    # Generate Pie Chart
    # ------------------------------------------------------------------

    chart_path = generate_pie_chart(
        labels=PIE_LABELS,
        values=[len(inactive_sale_df), len(active_sale_df)],
        output_path=os.path.join(output_dir, "The_Inactive_Sale.png"),
        colors=PIE_COLORS
    )

    assert os.path.exists(chart_path), "Pie chart image was not generated"

    # ------------------------------------------------------------------
    # Save DataFrames
    # ------------------------------------------------------------------

    inactive_sale_df.to_excel(
        os.path.join(output_dir, "inactive_product_sales.xlsx"),
        index=False
    )

    active_sale_df.to_excel(
        os.path.join(output_dir, "active_product_sales.xlsx"),
        index=False
    )

    # ------------------------------------------------------------------
    # Prepare Tables for PDF
    # ------------------------------------------------------------------

    inactive_sale_table = (
        [inactive_sale_df.columns.tolist()]
        + inactive_sale_df.values.tolist()
    )

    active_sale_table = (
        [active_sale_df.columns.tolist()]
        + active_sale_df.values.tolist()
    )

    tables_list = [
        {
            "data": inactive_sale_table,
            "title": f"Inactive Product Sales ({len(inactive_sale_df)})",
            "background_color": PIE_COLORS[0]
        },
        {
            "data": active_sale_table,
            "title": f"Active Product Sales ({len(active_sale_df)})",
            "background_color": PIE_COLORS[1]
        }
    ]

    # ------------------------------------------------------------------
    # Pie Chart Overview Content
    # ------------------------------------------------------------------

    ai_response = generate_pie_label_summary(
        labels={
            PIE_LABELS[0]: len(inactive_sale_df),
            PIE_LABELS[1]: len(active_sale_df)
        },
        segment_filters={
            PIE_LABELS[0]: filters,
            PIE_LABELS[1]: None
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

    USECASE_NAME = "The_Inactive_Sale"

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
            PIE_LABELS[0]: inactive_sale_df,
            PIE_LABELS[1]: active_sale_df
        },
        pie_labels=PIE_LABELS,
        pie_colors=PIE_COLORS
    )

    pie_overview_intro = (
        f"This pie chart highlights quotes that reference inactive products at the quote line level. "
        f"Out of {len(df)} total quotes, the distribution distinguishes between quotes containing "
        f"inactive products and those with only active products. Quotes with inactive products "
        f"pose a high risk of fulfillment failure and downstream operational issues."
    )

    # ------------------------------------------------------------------
    # Build PDF Report
    # ------------------------------------------------------------------

    build_leakage_report(
        output_pdf=os.path.join(
            output_dir,
            "The_Inactive_Sale.pdf"
        ),
        image_path=chart_path,
        tables_list=tables_list,
        title="Inactive Product Sales Analysis Report",
        intro_text=(
            f"This report identifies {len(inactive_sale_df)} quotes that reference inactive products "
            "at the quote line level (QuoteLine_Product_Active_Flag = False). "
            "Such quotes represent a critical operational risk, as fulfillment will fail for products "
            "that are no longer active in the Product Master. This issue highlights breakdowns in "
            "product lifecycle governance, catalog hygiene, and sales system controls."
        ),
        figure_caption=(
            "Figure 1. Distribution of Quotes with Inactive vs Active Products "
            "based on Product Master IsActive status."
        ),
        pie_overview_intro=pie_overview_intro,
        pie_segments=pie_segments
    )

    # ------------------------------------------------------------------
    # Final Output
    # ------------------------------------------------------------------

    print("\n✓ Report generated successfully")
    print(f"✓ PDF: {output_dir}/The_Inactive_Sale.pdf")
    print(
        f"✓ Inactive Product Sales ({len(inactive_sale_df)}): "
        "inactive_product_sales.xlsx"
    )
    print(
        f"✓ Active Product Sales ({len(active_sale_df)}): "
        "active_product_sales.xlsx"
    )
    print("✓ Pie chart saved")
    print("\nAll files are ready for download.")

    return {
        "name": "The_Inactive_Sale",
        "records_found": len(inactive_sale_df),
        "total_revenue": None,
        "total_loss": None
    }