import sys
sys.stdout.reconfigure(encoding='utf-8')

import os
import pandas as pd

from data_extraction.salesforce_client import run_query
from data_extraction.loaders import records_to_df
from filters.contract_filters import normalize_dates, apply_filters
from chart_generator.matplotlib_charts import generate_pie_chart
from report.report_generator import build_leakage_report
from ai_chart_overview_generator.groq_overview_generator import generate_pie_label_summary, build_pie_segments

# ------------------------------------------------------------------
# Pie chart globals (module-level constants, these never change)
# ------------------------------------------------------------------
PIE_LABELS = [
    "Non-Ghost Orders",
    "Ghost Orders"
]
PIE_COLORS = ["#88E788", "#FA5053"]


def run(sf, base_output_dir):
    # ----------------------------------------------------------------
    # 1. Create this usecase's own subfolder inside base_output_dir
    # ----------------------------------------------------------------
    output_dir = os.path.join(base_output_dir, "usecase_3")
    os.makedirs(output_dir, exist_ok=True)

    today = pd.Timestamp.today().normalize()

    # ----------------------------------------------------------------
    # 2. Fetch orders from Salesforce
    # ----------------------------------------------------------------
    query = """
        SELECT Id, OrderNumber, OrderReferenceNumber, Status, ActivatedDate, TotalAmount
        FROM Order
    """
    records = run_query(sf, query)
    df = records_to_df(records)

    # Normalize dates (force tz-naive)
    df = normalize_dates(df, ["ActivatedDate"])
    df["ActivatedDate"] = df["ActivatedDate"].dt.tz_localize(None)

    # ----------------------------------------------------------------
    # 3. Apply filters to detect ghost orders
    # ----------------------------------------------------------------
    filters = {
        "ActivatedDate": {"<=": today - pd.Timedelta(days=7)},
        "Status": "Activated",
        "OrderReferenceNumber": {"isna": True},
    }

    ghost_orders_df     = apply_filters(filters=filters, df=df)
    non_ghost_orders_df = df.loc[~df.index.isin(ghost_orders_df.index)].copy()

    # ----------------------------------------------------------------
    # 4. Generate pie chart
    # ----------------------------------------------------------------
    chart_path = generate_pie_chart(
        labels=PIE_LABELS,
        values=[len(non_ghost_orders_df), len(ghost_orders_df)],
        output_path=os.path.join(output_dir, "The_Ghost_Order.png"),
        colors=PIE_COLORS
    )

    assert os.path.exists(chart_path), "Pie chart image was not generated"

    # ----------------------------------------------------------------
    # 5. Save Excel files
    # ----------------------------------------------------------------
    ghost_orders_df.to_excel(
        os.path.join(output_dir, "ghost_orders.xlsx"), index=False
    )
    non_ghost_orders_df.to_excel(
        os.path.join(output_dir, "non_ghost_orders.xlsx"), index=False
    )

    # ----------------------------------------------------------------
    # 6. Build table data for PDF
    # ----------------------------------------------------------------
    ghost_order_table     = [ghost_orders_df.columns.tolist()]     + ghost_orders_df.values.tolist()
    non_ghost_order_table = [non_ghost_orders_df.columns.tolist()] + non_ghost_orders_df.values.tolist()

    tables_list = [
        {
            "data":             ghost_order_table,
            "title":            f"Ghost Orders ({len(ghost_orders_df)})",
            "background_color": "#FA5053"
        },
        {
            "data":             non_ghost_order_table,
            "title":            f"Non-Ghost Orders ({len(non_ghost_orders_df)})",
            "background_color": "#88E788"
        }
    ]

    # ----------------------------------------------------------------
    # 7. AI pie overview
    # ----------------------------------------------------------------
    pie_overview_intro = (
        f"This pie chart summarizes order classification across the dataset. "
        f"Out of {len(df)} total orders, the distribution highlights operational "
        f"gaps caused by missing ERP invoice references."
    )

    ai_response = generate_pie_label_summary(
        labels={
            PIE_LABELS[0]: len(non_ghost_orders_df),
            PIE_LABELS[1]: len(ghost_orders_df),
        },
        segment_filters={
            PIE_LABELS[0]: None,
            PIE_LABELS[1]: filters,
        },
        columns=df.columns.tolist()
    )
    print("\nAI-Generated Pie Chart Label Summary:\n")
    print(ai_response)

    # ----------------------------------------------------
    # Store reusable assets for category-level reports
    # ----------------------------------------------------

    data_chart_dir = os.path.join(base_output_dir, "Data_Chart")
    data_summary_dir = os.path.join(base_output_dir, "Data_Summary")

    os.makedirs(data_chart_dir, exist_ok=True)
    os.makedirs(data_summary_dir, exist_ok=True)

    USECASE_NAME = "The_Ghost_Order"

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

    pie_segments = build_pie_segments(
        ai_response,
        label_to_df_map={
            PIE_LABELS[0]: non_ghost_orders_df,
            PIE_LABELS[1]: ghost_orders_df,
        },
        pie_labels=PIE_LABELS,
        pie_colors=PIE_COLORS,
    )

    # ----------------------------------------------------------------
    # 8. Build PDF report
    # ----------------------------------------------------------------
    build_leakage_report(
        output_pdf=os.path.join(output_dir, "The_Ghost_Order.pdf"),
        image_path=chart_path,
        tables_list=tables_list,
        title="The 'Ghost' Orders Report",
        intro_text=(
            f"This report highlights {len(ghost_orders_df)} ghost orders that were activated "
            "in Salesforce but are not associated with any ERP invoice reference, representing "
            "potential revenue, fulfillment, and compliance risk."
        ),
        figure_caption="Figure 1. Distribution of Ghost vs Non-Ghost Orders.",
        pie_overview_intro=pie_overview_intro,
        pie_segments=pie_segments,
    )

    # ----------------------------------------------------------------
    # 9. Print file summary
    # ----------------------------------------------------------------
    print("\n✓ Report generated successfully")
    print(f"✓ PDF:                            {os.path.join(output_dir, 'The_Ghost_Order.pdf')}")
    print(f"✓ Ghost Orders ({len(ghost_orders_df)}):          ghost_orders.xlsx")
    print(f"✓ Non-Ghost Orders ({len(non_ghost_orders_df)}):      non_ghost_orders.xlsx")
    print("✓ Pie chart saved")
    print("\nAll files are ready for download.")

    # ----------------------------------------------------------------
    # 10. Return summary for main.py
    # ----------------------------------------------------------------
    return {
        "name": "The_Ghost_Order",
        "records_found": len(ghost_orders_df),
        "total_revenue": df["TotalAmount"].sum() - ghost_orders_df["TotalAmount"].sum(),
        "total_loss": ghost_orders_df["TotalAmount"].sum()
    }