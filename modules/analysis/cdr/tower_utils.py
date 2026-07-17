import re
import pandas as pd


_INVALID_TOWER_VALUES = {
    "",
    "-",
    "--",
    "---",
    "nan",
    "none",
    "null",
    "na",
    "n/a",
}


def normalize_cell_id(value) -> str:
    """Return a clean string version of a Cell ID without changing source data."""
    if value is None or pd.isna(value):
        return ""

    text = str(value).strip().strip("'").strip('"')
    return text


def is_valid_cell_id(value) -> bool:
    """
    Decide whether a Cell ID is useful for tower/location analysis.

    Raw invalid values are preserved in source data, but excluded from derived
    tower intelligence such as Home Tower, Work Tower and movement routes.
    """
    cell_id = normalize_cell_id(value)
    lowered = cell_id.lower()

    if lowered in _INVALID_TOWER_VALUES:
        return False

    # Broken CGI pattern seen in Airtel CDR: 405-51--
    if "--" in cell_id:
        return False

    # Reject values ending with separator, for example 405-51-
    if cell_id.endswith("-"):
        return False

    # Must contain at least 6 digits overall to be useful as a tower/cell ID.
    digit_count = sum(character.isdigit() for character in cell_id)
    if digit_count < 6:
        return False

    # Allow common formats:
    # 405-51-834-15492631
    # 4058560CCE04012
    # 405700400223721
    return bool(re.search(r"\d", cell_id))


def valid_cell_mask(series: pd.Series) -> pd.Series:
    """Return True for rows where the Cell ID should be used in tower analysis."""
    return series.map(is_valid_cell_id).fillna(False)


def filter_valid_first_cell_rows(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Filter rows to valid first_cell_id values for derived tower analysis."""
    if dataframe is None or dataframe.empty or "first_cell_id" not in dataframe.columns:
        return pd.DataFrame()

    mask = valid_cell_mask(dataframe["first_cell_id"])
    return dataframe.loc[mask].copy()
