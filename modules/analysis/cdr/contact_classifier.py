import re
import pandas as pd


_SERVICE_SENDER_PATTERN = re.compile(r"^[A-Z]{2}-[A-Z0-9][A-Z0-9\-]{2,}-[A-Z]$", re.IGNORECASE)


def normalize_contact(value) -> str:
    """Return clean contact text without changing the original source data."""
    if value is None or pd.isna(value):
        return ""

    return str(value).strip().strip("'").strip('"')


def classify_contact(value) -> str:
    """
    Classify a CDR counterparty for investigator-friendly reporting.

    Categories:
    - human_mobile: normal mobile/phone number contact
    - service_sender_id: SMS header / bank / operator / app sender ID
    - short_code: short service number such as 50000, 52263
    - unknown_contact: blank or unsupported value
    """
    contact = normalize_contact(value)

    if not contact:
        return "unknown_contact"

    compact = contact.replace(" ", "").replace("-", "")

    if _SERVICE_SENDER_PATTERN.match(contact):
        return "service_sender_id"

    if compact.isdigit():
        digit_count = len(compact)

        if digit_count <= 6:
            return "short_code"

        if 7 <= digit_count <= 15:
            return "human_mobile"

    if any(character.isalpha() for character in contact):
        return "service_sender_id"

    return "unknown_contact"


def add_contact_category(dataframe: pd.DataFrame, column: str = "b_party") -> pd.DataFrame:
    """Add contact_category column to a CDR dataframe."""
    if dataframe is None or dataframe.empty or column not in dataframe.columns:
        return pd.DataFrame() if dataframe is None else dataframe.copy()

    result = dataframe.copy()
    result["contact_category"] = result[column].map(classify_contact)
    return result


def only_human_contacts(dataframe: pd.DataFrame, column: str = "b_party") -> pd.DataFrame:
    """Return rows where the counterparty is a human/mobile number."""
    data = add_contact_category(dataframe, column)
    if data.empty or "contact_category" not in data.columns:
        return data

    return data[data["contact_category"].eq("human_mobile")].copy()


def only_service_sender_ids(dataframe: pd.DataFrame, column: str = "b_party") -> pd.DataFrame:
    """Return rows where the counterparty is a service/SMS sender ID."""
    data = add_contact_category(dataframe, column)
    if data.empty or "contact_category" not in data.columns:
        return data

    """Return rows where the counterparty is a service/SMS sender ID."""
    data = add_contact_category(dataframe, column)
    if data.empty or "contact_category" not in data.columns:
        return data

    return data[data["contact_category"].eq("service_sender_id")].copy()


def only_short_codes(dataframe: pd.DataFrame, column: str = "b_party") -> pd.DataFrame:
    """Return rows where the counterparty is a short code."""
    data = add_contact_category(dataframe, column)
    if data.empty or "contact_category" not in data.columns:
        return data

    return data[data["contact_category"].eq("short_code")].copy()
