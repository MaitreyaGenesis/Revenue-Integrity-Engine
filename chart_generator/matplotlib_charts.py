import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
from matplotlib.patches import ConnectionPatch
from matplotlib.ticker import FuncFormatter
from typing import List
import os


def bar_chart(df, column, output_path):
    counts = df[column].value_counts()

    plt.figure()
    counts.plot(kind="bar")
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()

    return output_path

def bar_chart_executive(usecase_names, losses, output_path):

    import matplotlib.pyplot as plt
    import numpy as np

    if not usecase_names or not losses:
        raise ValueError("usecase_names and losses cannot be empty")

    if len(usecase_names) != len(losses):
        raise ValueError("usecase_names and losses must be same length")

    plt.figure(figsize=(10, 6))

    # 🔵 Different shades of blue
    colors = plt.cm.get_cmap('Blues')(np.linspace(0.4, 0.9, len(usecase_names)))

    bars = plt.barh(usecase_names, losses, color=colors)

    plt.xlabel("Revenue Loss ($)", fontsize=10)
    plt.ylabel("Use Cases", fontsize=10)

    plt.gca().tick_params(axis='y', labelsize=8)
    plt.gca().tick_params(axis='x', labelsize=8)

    plt.gca().xaxis.set_major_formatter(
        FuncFormatter(lambda x, p: format(int(x), ","))
    )

    plt.gca().invert_yaxis()  # Highest at top

    plt.grid(axis='x', linestyle='--', alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_path, bbox_inches="tight", dpi=300)
    plt.show()
    plt.close()

    return output_path

def zombie_analysis_chart(
    df_all_contracts,
    df_zombie_contracts,
    df_expiring_soon=None,
    output_path="leakage_chart.png"
):
    """
    Create a dual-panel chart with:
    - Left: Pie chart showing overall contract status distribution
    - Right: Stacked bar chart showing zombie contracts by age
    - Connection lines linking the two panels
    
    Parameters:
    -----------
    df_all_contracts : DataFrame
        Complete dataframe of all contracts
    df_zombie_contracts : DataFrame
        Dataframe of zombie (leakage) contracts
    df_expiring_soon : DataFrame, optional
        Dataframe of contracts expiring soon (Warning category)
    output_path : str
        Path to save the output image
    
    Returns:
    --------
    str : Path to the saved image
    """
    
    # Convert StartDate to datetime
    df_zombie_contracts_copy = df_zombie_contracts.copy()
    df_zombie_contracts_copy['StartDate'] = pd.to_datetime(
        df_zombie_contracts_copy['StartDate'],
        errors='coerce'
    )
    
    # Calculate zombie age buckets
    today = pd.Timestamp.today()
    zombie_buckets = pd.cut(
        df_zombie_contracts_copy['StartDate'],
        bins=[
            pd.Timestamp.min,
            today - pd.DateOffset(years=2),
            today - pd.DateOffset(years=1),
            today
        ],
        labels=[
            'Older than 2 Years',
            '1–2 Years Old',
            'Less than 1 Year'
        ]
    )
    
    zombie_counts = zombie_buckets.value_counts().sort_index()
    
    # Calculate overall contract counts
    healthy_count = len(df_all_contracts) - len(df_zombie_contracts) - (len(df_expiring_soon) if df_expiring_soon is not None else 0)
    warning_count = len(df_expiring_soon) if df_expiring_soon is not None else 0
    zombie_count = len(df_zombie_contracts)
    
    
    
    labels = ['Healthy Contracts', 'Warning Contracts', 'Zombie Contracts']
    sizes = [
        healthy_count,
        warning_count,
        zombie_count
    ]
    
    colors = ['#88E788', '#FFEE8C', '#FA5053']
    explode = [0, 0, 0.1]
    
    overall_ratios = np.array(sizes) / sum(sizes)
    
    zombie_idx = 2
    startangle = (
        360 * overall_ratios[:zombie_idx].sum()
        + 180 * overall_ratios[zombie_idx]
    )
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 5))
    fig.subplots_adjust(wspace=0)
    
    wedges, *_ = ax1.pie(
        overall_ratios,
        labels=labels,
        autopct='%1.1f%%',
        colors=colors,
        explode=explode,
        startangle=-startangle
    )
    
    ax1.set_title('Black Box Analysis')
    #ax1.legend(loc="lower center",bbox_to_anchor=(0.52, -0.15),ncol=len(labels),frameon=False)
    ax1.axis('equal')
    
    values = zombie_counts.to_numpy(dtype=float)

    age_ratios = values / values.sum()
    age_labels = zombie_counts.index.astype(str).tolist()

    bottom = 1
    width = 0.25
    
    for j, (height, label) in enumerate(reversed(list(zip(age_ratios, age_labels)))):
        bottom -= height
        bc = ax2.bar(
            0,
            height,
            width,
            bottom=bottom,
            label=label,
            color='#FA5053',
            alpha=0.3 + 0.2 * j
        )
        ax2.bar_label(bc, labels=[f"{height:.0%}"], label_type='center')
    
    ax2.set_title('Zombie Contracts by Age')
    ax2.legend(loc='best')
    ax2.axis('off')
    ax2.set_xlim(-2.5 * width, 2.5 * width)
    
    zombie_wedge = wedges[zombie_idx]
    theta1, theta2 = zombie_wedge.theta1, zombie_wedge.theta2
    center, r = zombie_wedge.center, zombie_wedge.r
    bar_height = sum(age_ratios)
    
    x = r * np.cos(np.pi / 180 * theta2) + center[0]
    y = r * np.sin(np.pi / 180 * theta2) + center[1]
    con = ConnectionPatch(
        xyA=(-width / 2, bar_height),
        coordsA=ax2.transData,
        xyB=(x, y),
        coordsB=ax1.transData,
        linewidth=2,
        color='#333333'
    )
    ax2.add_artist(con)
    
    # Bottom connector
    x = r * np.cos(np.pi / 180 * theta1) + center[0]
    y = r * np.sin(np.pi / 180 * theta1) + center[1]
    con = ConnectionPatch(
        xyA=(-width / 2, 0),
        coordsA=ax2.transData,
        xyB=(x, y),
        coordsB=ax1.transData,
        linewidth=2,
        color='#333333'
    )
    ax2.add_artist(con)
    
    fig.show()
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    
    plt.close()
    
    return output_path


from typing import List
import matplotlib.pyplot as plt
import os

def generate_pie_chart(
    labels: List[str],
    values: List[int],
    output_path: str,
    colors: List[str] | None = None,
):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    plt.rcParams.update({'font.size': 22})

    fig, ax = plt.subplots(figsize=(12, 14))  # ⬅️ taller for bottom legend

    pie_result = plt.pie(
    values,
    labels=None,
    autopct="%1.1f%%",
    startangle=100,
    colors=colors,
    textprops={'fontsize': 30} 
    )
    wedges, autotexts = pie_result[:2]


    # Make percentage text readable
    for autotext in autotexts:
        autotext.set_color("black")
    
    

    # Bottom legend
    ax.legend(
        wedges,
        labels,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.08),   
        ncol=3,                        
        frameon=False,
        fontsize=30,
    )
    ax.axis("equal")

    plt.subplots_adjust(bottom=0.18)

    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()

    return output_path