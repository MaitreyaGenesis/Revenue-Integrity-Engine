import pandas as pd
from typing import Dict, List, Optional,Mapping, Union, Any,TypeAlias
from typing import Mapping, Union, Any, TypeAlias
from typing import TypeGuard
import pandas as pd

NestedMapping = Dict[str, Any]

def records_to_df(records):
    """Convert Salesforce query records to DataFrame."""
    df = pd.DataFrame(records)
    if "attributes" in df.columns:
        df = df.drop(columns=["attributes"])
    return df


def extract_nested_fields(df: pd.DataFrame, nested_mapping: Dict[str, Dict[str, str]]) -> pd.DataFrame:
    """
    Extract nested object fields from DataFrame and create new columns.
    
    Args:
        df: DataFrame with nested objects (from SOQL relationship queries)
        nested_mapping: Dict mapping nested column names to their field extractions.
                       Format: {'nested_column': {'field_name': 'new_column_name', ...}, ...}
                       Example: {'Account': {'Name': 'Account Name'}, 
                                'SBQQ__Opportunity__r': {'Name': 'Opportunity Name', 'Amount': 'Opportunity Amount'}}
    
    Returns:
        DataFrame with extracted fields as new columns
    """
    df = df.copy()
    
    for nested_col, field_mapping in nested_mapping.items():
        if nested_col in df.columns:
            for field_name, new_col_name in field_mapping.items():
                df[new_col_name] = df[nested_col].apply(
                    lambda x: x.get(field_name) if isinstance(x, dict) else None
                )
    
    return df


def is_nested_mapping(value: object) -> TypeGuard[NestedMapping]:
    return isinstance(value, Mapping)


def extract_from_dict(
    data: Any,
    mapping: NestedMapping
) -> dict[str, Any]:

    result: dict[str, Any] = {}

    if not isinstance(data, dict):
        return result

    for key, value in mapping.items():

        # Leaf node
        if isinstance(value, str):
            result[value] = data.get(key)

        # Nested node
        elif is_nested_mapping(value):
            nested_data = data.get(key)
            if isinstance(nested_data, dict):
                nested_result = extract_from_dict(nested_data, value)
                result.update(nested_result)

    return result


def extract_nested_fields_n_level(
    df: pd.DataFrame,
    nested_mapping: NestedMapping
) -> pd.DataFrame:

    df = df.copy()

    for top_column, mapping in nested_mapping.items():

        if top_column not in df.columns:
            continue

        extracted_series = df[top_column].apply(
            lambda x: extract_from_dict(x, mapping)
        )

        # Convert Series → list[dict] (Pylance-safe)
        extracted_df = pd.json_normalize(extracted_series.tolist())

        df = pd.concat([df, extracted_df], axis=1)

    return df

def clean_soql_dataframe(df: pd.DataFrame, 
                        columns_to_drop: Optional[List[str]] = None,
                        rename_columns: Optional[Dict[str, str]] = None) -> pd.DataFrame:
    """
    Clean DataFrame by dropping unwanted columns and renaming others.
    
    Args:
        df: Input DataFrame
        columns_to_drop: List of columns to remove. Default: ['attributes']
        rename_columns: Dict mapping old column names to new names
    
    Returns:
        Cleaned DataFrame
    """
    df = df.copy()
    
    if columns_to_drop is None:
        columns_to_drop = ['attributes']
    
    existing_cols_to_drop = [col for col in columns_to_drop if col in df.columns]
    if existing_cols_to_drop:
        df = df.drop(columns=existing_cols_to_drop)
    
    if rename_columns:
        df.rename(columns=rename_columns, inplace=True)
    
    return df
