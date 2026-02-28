import pandas as pd
from pandas.tseries.offsets import Day

today = pd.Timestamp.today().normalize()

def normalize_dates(df, columns):
    for col in columns:
        df[col] = (
            pd.to_datetime(df[col], errors="coerce", utc=True)
              .dt.tz_convert(None)   
              .dt.normalize()
        )
    return df

def leakage_zombies(df, today=None):
    if today is None:
        today = pd.Timestamp.today().normalize()

    return df.loc[
        (df["EndDate"] <= today - pd.Timedelta(days=30)) &
        (df["Status"] == "Activated") &
        (df["SBQQ__RenewalOpportunity__c"].isna())
    ].copy()

def expiring_soon_contracts(df):
    return df.loc[
       (df['EndDate'] >= (today - pd.Timedelta(days=30))) &
       (df['Status'] == 'Activated') &
       (df['SBQQ__RenewalOpportunity__c'].isna())
    ].copy()

def apply_filters(df, filters: dict):
    """
    Apply arbitrary filters to a dataframe.

    Supported filter formats:
    - value equality
    - list membership
    - date ranges
    - null / not-null
    - comparison operators

    Example:
    filters = {
        "Status": "Activated",
        "SBQQ__RenewalOpportunity__c": {"isna": True},
        "EndDate": {"lte": today - pd.Timedelta(days=30)}
    }
    """

    mask = pd.Series(True, index=df.index)

    for column, condition in filters.items():
        if isinstance(condition, dict):
            for op, value in condition.items():

                if op == "isna":
                    mask &= df[column].isna()

                elif op == "notna":
                    mask &= df[column].notna()

                elif op == "=":
                    mask &= df[column] == value

                elif op == "!=":
                    mask &= df[column] != value

                elif op == "in":
                    mask &= df[column].isin(value)

                elif op == ">=":
                    mask &= df[column] >= value

                elif op == "<=":
                    mask &= df[column] <= value

                elif op == ">":
                    mask &= df[column] > value

                elif op == "<":
                    mask &= df[column] < value

                else:
                    raise ValueError(f"Unsupported operator: {op}")

        else:
            # simple equality
            mask &= df[column] == condition

    return df.loc[mask].copy()
