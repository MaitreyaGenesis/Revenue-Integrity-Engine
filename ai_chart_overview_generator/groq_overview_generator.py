import os
from dotenv import load_dotenv
from groq import Groq
import json
import re

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def generate_pie_label_summary(labels, segment_filters, columns) -> str:
    prompt = generate_prompt(labels=labels, segment_filters=segment_filters, columns=columns)
    response = client.chat.completions.create(
        model="compound-beta",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a business data analyst generating label-level summaries for a pie chart."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0.1,
        max_tokens=600
    )
    raw_output = response.choices[0].message.content or ""
    return json.loads(raw_output)

def generate_prompt(labels, segment_filters, columns):
    segments_text = "\n".join(
        [f"- {label}: {count}" for label, count in labels.items()]
    )

    filters_text = []
    for label in labels:
        filt = segment_filters.get(label)
        if filt:
            filters_text.append(f"- {label}: filters = {filt}")
        else:
            filters_text.append(
                f"- {label}: No explicit filter provided. "
                f"This segment represents all remaining records not captured by other segment filters."
            )

    filters_text = "\n".join(filters_text)
    columns_text = "\n".join([f"- {col}" for col in columns])

    prompt = f"""
For each pie chart segment, generate:

1. A heading in the format:
{{{{Segment Title}}}} ({{{{Count}}}})

2. A 2–3 sentence explanation describing:
- What the segment represents
- Why these records fall into this category (based on columns involved)
- The operational or business implication, if evident

Guidelines:
- Write a separate block for each segment
- Use clear, professional business language
- Base explanations strictly on the data and filters provided
- Do not compare segments with each other
- Do not mention chart mechanics or visualization terms
- Keep each explanation concise (40–60 words max)
- You are a function that returns ONLY valid JSON
- Do not include explanations, markdown, or text outside JSON

Input:
Segments:
{segments_text}

Filters applied per segment:
{filters_text}

If a filter is not provided for a segment, treat it as all records excluding those covered by other segment filters.

Columns involved:
{columns_text}

Output:
Return ONLY valid JSON.
Do not include markdown, explanations, or extra text.

The response MUST be a JSON array.
Each array item MUST follow this schema:
[
  {{
    "segment_no": number,
    "title": string,
    "description": string
  }}
]
""".strip()

    return prompt

def build_pie_segments(
    llm_output,
    label_to_df_map,
    pie_labels,
    pie_colors
):
    """
    llm_output: list[dict]
        [
          {
            "segment_no": 1,
            "title": "Inactive Product Sales (14)",
            "description": "..."
          }
        ]

    label_to_df_map: dict
        {
            "Inactive Product Sales": inactive_sale_df,
            "Active Product Sales": active_sale_df
        }
    """

    # Build lookup from base title -> description
    description_map = {}
    for item in llm_output:
        raw_title = item.get("title", "")
        base_title = re.sub(r"\s*\(\d+\)$", "", raw_title).strip()
        description_map[base_title] = item.get("description", "")

    pie_segments = []

    for idx, label in enumerate(pie_labels):
        df = label_to_df_map.get(label)

        if df is None:
            continue  # fail-safe: skip unknown labels

        pie_segments.append({
            "title": label,
            "count": len(df),
            "description": description_map.get(label, ""),
            "color": pie_colors[idx] if idx < len(pie_colors) else "#CCCCCC",
        })

    return pie_segments