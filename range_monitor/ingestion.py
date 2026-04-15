from pathlib import Path

import pandas as pd

# Canonical column names expected by the analysis engine
REQUIRED_COLUMNS = {
    "products": ["product_id", "product_name", "category"],
    "online_sales": ["product_id", "period", "units_sold"],
    "store_sales": ["product_id", "location_id", "period", "units_sold"],
    "calendar": ["range_tag", "season", "active_from", "active_to"],
}

OPTIONAL_COLUMNS = {
    "products": ["brand", "range_tag", "season", "price"],
    "online_sales": ["revenue"],
    "store_sales": ["stock_on_hand", "revenue"],
    "calendar": [],
}


def load_file(path: str | Path) -> pd.DataFrame:
    """Load a CSV or Excel file into a DataFrame."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {path}")
    if path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    return pd.read_csv(path)


def apply_schema_mapping(df: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    """Rename customer column names to canonical names using a mapping dict.

    Args:
        df: Raw DataFrame from customer file.
        mapping: Dict of {customer_column: canonical_column}.
    """
    return df.rename(columns=mapping)


def validate_required_columns(df: pd.DataFrame, entity: str) -> None:
    """Raise a clear error if any required canonical columns are missing."""
    required = REQUIRED_COLUMNS.get(entity, [])
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(
            f"[{entity}] Missing required columns: {missing}. "
            f"Found columns: {list(df.columns)}. "
            f"Use a schema mapping file to map your column names to the canonical names."
        )


def parse_dates(df: pd.DataFrame, date_cols: list[str]) -> pd.DataFrame:
    """Parse date columns, coercing errors to NaT with a warning."""
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
            nulls = df[col].isna().sum()
            if nulls > 0:
                print(f"  Warning: {nulls} unparseable date(s) in column '{col}' set to NaT.")
    return df


def load_products(path: str | Path, mapping: dict | None = None) -> pd.DataFrame:
    df = load_file(path)
    if mapping:
        df = apply_schema_mapping(df, mapping)
    validate_required_columns(df, "products")
    df["product_id"] = df["product_id"].astype(str)
    # Ensure optional columns exist with sensible defaults
    for col in ["brand", "range_tag", "season", "price"]:
        if col not in df.columns:
            df[col] = None
    return df


def load_online_sales(path: str | Path, mapping: dict | None = None) -> pd.DataFrame:
    df = load_file(path)
    if mapping:
        df = apply_schema_mapping(df, mapping)
    validate_required_columns(df, "online_sales")
    df = parse_dates(df, ["period"])
    df["product_id"] = df["product_id"].astype(str)
    df["units_sold"] = pd.to_numeric(df["units_sold"], errors="coerce").fillna(0).astype(int)
    if "revenue" not in df.columns:
        df["revenue"] = None
    return df


def load_store_sales(path: str | Path, mapping: dict | None = None) -> pd.DataFrame:
    df = load_file(path)
    if mapping:
        df = apply_schema_mapping(df, mapping)
    validate_required_columns(df, "store_sales")
    df = parse_dates(df, ["period"])
    df["product_id"] = df["product_id"].astype(str)
    df["location_id"] = df["location_id"].astype(str)
    df["units_sold"] = pd.to_numeric(df["units_sold"], errors="coerce").fillna(0).astype(int)
    if "stock_on_hand" not in df.columns:
        df["stock_on_hand"] = None
    if "revenue" not in df.columns:
        df["revenue"] = None
    return df


def load_calendar(path: str | Path, mapping: dict | None = None) -> pd.DataFrame:
    df = load_file(path)
    if mapping:
        df = apply_schema_mapping(df, mapping)
    validate_required_columns(df, "calendar")
    # active_from/active_to may be empty for continuity products
    for col in ["active_from", "active_to"]:
        df[col] = df[col].replace("", None)
        df[col] = pd.to_datetime(df[col], errors="coerce")
    return df
