# modules/reports.py

import importlib
import traceback

import pandas as pd


# ==============================================================
# SAFE IMPORT SYSTEM
# ==============================================================

FUNCTIONS = {}
IMPORT_ERRORS = {}


def safe_load(module_path, function_names):
    """
    Kisi analysis module aur uske functions ko safely import karta hai.

    Ek module fail hone par reports.py crash nahi hoga.
    Doosre analysis modules normal tarike se load hote rahenge.
    """

    try:
        module = importlib.import_module(module_path)

    except Exception as error:
        error_message = f"{type(error).__name__}: {error}"
        IMPORT_ERRORS[module_path] = error_message

        print(f"\n[-] Module Import Failed: {module_path}")
        print(f"    Error: {error_message}")

        for function_name in function_names:
            FUNCTIONS[function_name] = None

        return

    for function_name in function_names:
        try:
            function = getattr(module, function_name)

            if not callable(function):
                raise TypeError(
                    f"'{function_name}' callable function nahi hai."
                )

            FUNCTIONS[function_name] = function

        except Exception as error:
            error_key = f"{module_path}.{function_name}"
            error_message = f"{type(error).__name__}: {error}"

            IMPORT_ERRORS[error_key] = error_message
            FUNCTIONS[function_name] = None

            print(f"\n[-] Function Import Failed: {error_key}")
            print(f"    Error: {error_message}")


# ==============================================================
# LOAD ALL CDR ANALYSIS FUNCTIONS
# ==============================================================

safe_load(
    "modules.analysis.cdr.contacts",
    [
        "top_contacts",
        "contact_ranking",
        "incoming_outgoing",
        "contact_summary",
    ],
)

safe_load(
    "modules.analysis.cdr.social_network",
    [
        "social_network",
    ],
)

safe_load(
    "modules.analysis.cdr.location",
    [
        "frequent_locations",
    ],
)

safe_load(
    "modules.analysis.cdr.movement",
    [
        "tower_movement",
        "tower_transition",
        "movement_pattern",
    ],
)

safe_load(
    "modules.analysis.cdr.tower_intelligence",
    [
        "tower_intelligence",
        "home_tower",
        "work_tower",
    ],
)

safe_load(
    "modules.analysis.cdr.imei",
    [
        "imei_summary",
        "imei_intelligence",
    ],
)

safe_load(
    "modules.analysis.cdr.sim_change",
    [
        "sim_change",
    ],
)

safe_load(
    "modules.analysis.cdr.activity",
    [
        "analyze_activity",
        "hourly_activity",
        "daily_activity",
        "weekly_activity",
        "monthly_activity",
    ],
)

safe_load(
    "modules.analysis.cdr.behavioral_intelligence",
    [
        "behavioral_intelligence",
    ],
)

safe_load(
    "modules.analysis.cdr.suspicious_activity",
    [
        "suspicious_activity",
    ],
)

safe_load(
    "modules.analysis.cdr.summary",
    [
        "cdr_summary",
    ],
)


# ==============================================================
# GENERAL OUTPUT FUNCTIONS
# ==============================================================

def print_section(title):
    """Main report section heading print karta hai."""

    print("\n" + "=" * 75)
    print(title)
    print("=" * 75)


def print_output(title, output, max_rows=None):
    """
    DataFrame, Series, dictionary, list ya normal value ko safely print karta hai.
    """

    print(f"\n===== {title} =====")

    if output is None:
        print("No records found.")
        return

    # ----------------------------------------------------------
    # DataFrame
    # ----------------------------------------------------------

    if isinstance(output, pd.DataFrame):
        if output.empty:
            print("No records found.")
            return

        display_data = output

        if (
            max_rows is not None
            and max_rows > 0
            and len(output) > max_rows
        ):
            display_data = output.head(max_rows)

        try:
            print(display_data.to_string(index=False))
        except Exception:
            print(display_data)

        if (
            max_rows is not None
            and max_rows > 0
            and len(output) > max_rows
        ):
            print(
                f"\n[+] Showing first {max_rows} "
                f"of {len(output)} records."
            )

        return

    # ----------------------------------------------------------
    # Series
    # ----------------------------------------------------------

    if isinstance(output, pd.Series):
        if output.empty:
            print("No records found.")
            return

        display_data = output

        if (
            max_rows is not None
            and max_rows > 0
            and len(output) > max_rows
        ):
            display_data = output.head(max_rows)

        print(display_data.to_string())

        if (
            max_rows is not None
            and max_rows > 0
            and len(output) > max_rows
        ):
            print(
                f"\n[+] Showing first {max_rows} "
                f"of {len(output)} records."
            )

        return

    # ----------------------------------------------------------
    # Dictionary
    # ----------------------------------------------------------

    if isinstance(output, dict):
        if not output:
            print("No records found.")
            return

        for key, value in output.items():
            print(f"{str(key):<40}: {value}")

        return

    # ----------------------------------------------------------
    # List, Tuple or Set
    # ----------------------------------------------------------

    if isinstance(output, (list, tuple, set)):
        if not output:
            print("No records found.")
            return

        for item in output:
            print(item)

        return

    # ----------------------------------------------------------
    # Normal value
    # ----------------------------------------------------------

    print(str(output))


# ==============================================================
# SAFE ANALYSIS EXECUTOR
# ==============================================================

def safe_run(
    title,
    function_name,
    *args,
    display_rows=None,
    **kwargs,
):
    """
    Analysis function ko safely execute karta hai.

    Error aane par:
    - function name batata hai;
    - error type batata hai;
    - error message batata hai;
    - traceback location dikhata hai;
    - baaki report continue rakhta hai.
    """

    function = FUNCTIONS.get(function_name)

    if not callable(function):
        print(f"\n===== {title} =====")
        print(f"[-] Analysis function unavailable: {function_name}")
        print(
            "    Module import fail hua hai ya function module mein nahi mila."
        )
        return None

    try:
        result = function(*args, **kwargs)

        print_output(
            title,
            result,
            max_rows=display_rows,
        )

        return result

    except Exception as error:
        print(f"\n===== {title} =====")
        print(f"[-] Analysis Failed: {function_name}")
        print(f"    Error Type : {type(error).__name__}")
        print(f"    Message    : {error}")
        print("    Error Trace:")

        error_trace = traceback.format_exc(limit=3)
        print(error_trace.rstrip())

        return None


# ==============================================================
# TOP CONTACT DETAILED PROFILE
# ==============================================================

def print_top_contact_details(df):
    """
    Top interacted contact ka detailed intelligence profile generate karta hai.
    """

    print("\n===== TOP CONTACT DETAILED INTELLIGENCE =====")

    top_contacts_function = FUNCTIONS.get("top_contacts")
    contact_summary_function = FUNCTIONS.get("contact_summary")

    if not callable(top_contacts_function):
        print("[-] top_contacts function available nahi hai.")
        return None

    if not callable(contact_summary_function):
        print("[-] contact_summary function available nahi hai.")
        return None

    try:
        contacts = top_contacts_function(df, limit=1)

        if contacts is None:
            print("No contact information returned.")
            return None

        if not isinstance(contacts, pd.DataFrame):
            print(
                "[-] top_contacts ne DataFrame return nahi kiya."
            )
            return None

        if contacts.empty:
            print("No contact interactions found.")
            return None

        # Current top_contacts() output mein column "Contact" hota hai.
        # Fallback columns bhi safety ke liye check kiye gaye hain.
        possible_columns = [
            "Contact",
            "contact",
            "b_party",
            "opposite_party",
            "called_number",
        ]

        contact_column = None

        for column in possible_columns:
            if column in contacts.columns:
                contact_column = column
                break

        if contact_column is None:
            print("[-] Contact number column nahi mila.")
            print(
                f"    Available columns: {contacts.columns.tolist()}"
            )
            return None

        top_number = contacts.iloc[0][contact_column]

        if pd.isna(top_number):
            print("[-] Top contact number blank hai.")
            return None

        top_number = str(top_number).strip()

        if not top_number:
            print("[-] Top contact number invalid hai.")
            return None

        print(
            f"[+] Reviewing highest-frequency contact: {top_number}"
        )

        result = contact_summary_function(
            df,
            top_number,
        )

        print_output(
            f"INTELLIGENCE SUMMARY FOR {top_number}",
            result,
        )

        return result

    except Exception as error:
        print("[-] Top Contact Detailed Analysis Failed")
        print(f"    Error Type : {type(error).__name__}")
        print(f"    Message    : {error}")
        print("    Error Trace:")

        print(traceback.format_exc(limit=3).rstrip())

        return None


# ==============================================================
# CHRONOLOGICAL TIMELINE
# ==============================================================

def print_timeline(df, max_rows=500):
    """
    CDR records ko proper chronological order mein print karta hai.

    Original DataFrame ko modify nahi karta.
    """

    print_section("CHRONOLOGICAL TIMELINE")

    if df is None:
        print("No DataFrame received.")
        return

    if not isinstance(df, pd.DataFrame):
        print(
            "[-] Invalid timeline input. "
            f"Received: {type(df).__name__}"
        )
        return

    if df.empty:
        print("No records available for timeline.")
        return

    try:
        timeline_df = df.copy()

        # b_party missing hone par opposite_party use karein.
        if (
            "b_party" not in timeline_df.columns
            and "opposite_party" in timeline_df.columns
        ):
            timeline_df["b_party"] = (
                timeline_df["opposite_party"]
            )

        # Missing columns ke safe default values.
        default_columns = {
            "call_date": "N/A",
            "call_time": "N/A",
            "call_type": "N/A",
            "call_direction": "",
            "b_party": "N/A",
            "call_duration": 0,
        }

        for column, default_value in default_columns.items():
            if column not in timeline_df.columns:
                timeline_df[column] = default_value

        # Existing datetime column ko use karein.
        if "datetime" in timeline_df.columns:
            timeline_df["_report_datetime"] = pd.to_datetime(
                timeline_df["datetime"],
                errors="coerce",
            )

        else:
            timeline_df["_report_datetime"] = pd.NaT

        # Jahan existing datetime parse nahi hua, wahan date + time use karein.
        missing_datetime = timeline_df[
            "_report_datetime"
        ].isna()

        if missing_datetime.any():
            combined_datetime = (
                timeline_df.loc[
                    missing_datetime,
                    "call_date",
                ]
                .astype("string")
                .fillna("")
                .str.strip()
                + " "
                + timeline_df.loc[
                    missing_datetime,
                    "call_time",
                ]
                .astype("string")
                .fillna("")
                .str.strip()
            )

            parsed_datetime = pd.to_datetime(
                combined_datetime,
                errors="coerce",
                dayfirst=True,
            )

            timeline_df.loc[
                missing_datetime,
                "_report_datetime",
            ] = parsed_datetime

        timeline_df = timeline_df.sort_values(
            "_report_datetime",
            na_position="last",
            kind="stable",
        )

        total_rows = len(timeline_df)

        if (
            max_rows is not None
            and max_rows > 0
        ):
            timeline_df = timeline_df.head(max_rows)

        current_date = None

        for _, row in timeline_df.iterrows():
            parsed_datetime = row["_report_datetime"]

            if pd.notna(parsed_datetime):
                display_date = parsed_datetime.strftime(
                    "%d-%m-%Y"
                )
                display_time = parsed_datetime.strftime(
                    "%H:%M:%S"
                )
            else:
                display_date = str(
                    row.get("call_date", "N/A")
                )
                display_time = str(
                    row.get("call_time", "N/A")
                )

            if display_date != current_date:
                current_date = display_date
                print(f"\n--- Date: {display_date} ---")

            call_type = str(
                row.get("call_type", "N/A")
            )

            call_direction = row.get(
                "call_direction",
                "",
            )

            if pd.isna(call_direction):
                call_direction = ""

            call_direction = str(
                call_direction
            ).strip()

            if call_direction:
                event_type = (
                    f"{call_direction}/{call_type}"
                )
            else:
                event_type = call_type

            opponent = row.get("b_party", "N/A")

            if pd.isna(opponent):
                opponent = "N/A"

            opponent = str(opponent)

            raw_duration = row.get(
                "call_duration",
                0,
            )

            try:
                if pd.isna(raw_duration):
                    duration = 0
                else:
                    duration = int(
                        float(raw_duration)
                    )

            except (TypeError, ValueError):
                duration = 0

            print(
                f"{display_time:<10} | "
                f"Type: {event_type:<24} | "
                f"Opponent: {opponent:<15} | "
                f"Duration: {duration:>6} sec"
            )

        if (
            max_rows is not None
            and max_rows > 0
            and total_rows > max_rows
        ):
            print(
                f"\n[+] Timeline showing first "
                f"{max_rows} of {total_rows} records."
            )

    except Exception as error:
        print("[-] Timeline Generation Failed")
        print(f"    Error Type : {type(error).__name__}")
        print(f"    Message    : {error}")
        print("    Error Trace:")

        print(traceback.format_exc(limit=3).rstrip())


# ==============================================================
# IMPORT ERROR SUMMARY
# ==============================================================

def print_import_error_summary():
    """
    Report ke end mein failed modules/functions ki summary print karta hai.
    """

    if not IMPORT_ERRORS:
        return

    print_section("MODULE IMPORT ERROR SUMMARY")

    for module_name, error_message in IMPORT_ERRORS.items():
        print(f"[-] {module_name}")
        print(f"    {error_message}")


# ==============================================================
# COMPLETE CDR FORENSIC REPORT
# ==============================================================

def extract_report(df, target, timeline_limit=500):
    """
    Complete CDR forensic report generate karta hai.

    Kisi ek module ya analysis function mein error hone par:
    - error display hoga;
    - baaki analysis continue rahega;
    - poora program crash nahi hoga.

    Returns:
        Har analysis ka result dictionary mein return hota hai.
    """

    print("\n" + "=" * 75)
    print(
        f"🛡️  FORENSIC RECONNAISSANCE REPORT "
        f"FOR TARGET: {target}"
    )
    print("=" * 75)

    if df is None:
        print(
            "[-] DataFrame None hai. "
            "Report generation aborted."
        )
        return {}

    if not isinstance(df, pd.DataFrame):
        print(
            "[-] Invalid report input. "
            f"Expected DataFrame, received {type(df).__name__}."
        )
        return {}

    if df.empty:
        print(
            "[-] DataFrame empty hai. "
            "Report generation aborted."
        )
        return {}

    report_df = df.copy()
    results = {}

    # ==========================================================
    # PART 0: MASTER SUMMARY
    # ==========================================================

    print_section("[PART 0] MASTER CDR OVERVIEW")

    results["cdr_summary"] = safe_run(
        "MASTER CDR SUMMARY",
        "cdr_summary",
        report_df,
    )

    # ==========================================================
    # PART 1: CONTACT AND LINK INTELLIGENCE
    # ==========================================================

    print_section(
        "[PART 1] CONTACT & LINK INTELLIGENCE"
    )

    results["top_contacts"] = safe_run(
        "TOP INTERACTED CONTACTS",
        "top_contacts",
        report_df,
        limit=20,
        display_rows=20,
    )

    results["contact_ranking"] = safe_run(
        "CONTACT RANKING MATRIX",
        "contact_ranking",
        report_df,
        display_rows=50,
    )

    results["incoming_outgoing"] = safe_run(
        "INCOMING VS OUTGOING TRAFFIC",
        "incoming_outgoing",
        report_df,
    )

    results["social_network"] = safe_run(
        "SOCIAL NETWORK LINK ANALYSIS",
        "social_network",
        report_df,
        display_rows=50,
    )

    results["top_contact_details"] = (
        print_top_contact_details(report_df)
    )

    # ==========================================================
    # PART 2: LOCATION AND TOWER INTELLIGENCE
    # ==========================================================

    print_section(
        "[PART 2] LOCATION, TOWER & MOVEMENT INTELLIGENCE"
    )

    results["frequent_locations"] = safe_run(
        "FREQUENT OPERATIONAL LOCATIONS",
        "frequent_locations",
        report_df,
        top_n=20,
        display_rows=20,
    )

    results["home_tower"] = safe_run(
        "PROBABLE HOME TOWER",
        "home_tower",
        report_df,
        display_rows=20,
    )

    results["work_tower"] = safe_run(
        "PROBABLE WORK TOWER",
        "work_tower",
        report_df,
        display_rows=20,
    )

    results["tower_movement"] = safe_run(
        "TOWER MOVEMENT SEQUENCE",
        "tower_movement",
        report_df,
        display_rows=50,
    )

    results["tower_transition"] = safe_run(
        "TOWER TRANSITION / ROUTE ANALYSIS",
        "tower_transition",
        report_df,
        display_rows=50,
    )

    results["tower_intelligence"] = safe_run(
        "TOWER INTELLIGENCE SUMMARY",
        "tower_intelligence",
        report_df,
        display_rows=50,
    )

    results["movement_pattern"] = safe_run(
        "REPEATED MOVEMENT PATTERNS",
        "movement_pattern",
        report_df,
        display_rows=50,
    )

    # ==========================================================
    # PART 3: IMEI, DEVICE AND SIM INTELLIGENCE
    # ==========================================================

    print_section(
        "[PART 3] IMEI, DEVICE & SIM INTELLIGENCE"
    )

    results["imei_summary"] = safe_run(
        "IMEI SUMMARY",
        "imei_summary",
        report_df,
        display_rows=50,
    )

    results["imei_intelligence"] = safe_run(
        "IMEI INTELLIGENCE",
        "imei_intelligence",
        report_df,
        display_rows=50,
    )

    results["sim_change"] = safe_run(
        "HANDSET / IMEI CHANGE EVENTS",
        "sim_change",
        report_df,
        display_rows=100,
    )

    # ==========================================================
    # PART 4: ACTIVITY AND TEMPORAL INTELLIGENCE
    # ==========================================================

    print_section(
        "[PART 4] ACTIVITY & TEMPORAL INTELLIGENCE"
    )

    results["activity_summary"] = safe_run(
        "OVERALL ACTIVITY SUMMARY",
        "analyze_activity",
        report_df,
    )

    results["hourly_activity"] = safe_run(
        "HOURLY ACTIVITY",
        "hourly_activity",
        report_df,
        display_rows=24,
    )

    results["daily_activity"] = safe_run(
        "DAILY ACTIVITY",
        "daily_activity",
        report_df,
        display_rows=50,
    )

    results["weekly_activity"] = safe_run(
        "WEEKLY ACTIVITY",
        "weekly_activity",
        report_df,
        display_rows=53,
    )

    results["monthly_activity"] = safe_run(
        "MONTHLY ACTIVITY",
        "monthly_activity",
        report_df,
        display_rows=12,
    )

    # ==========================================================
    # PART 5: BEHAVIORAL OBSERVATIONS AND REVIEW INDICATORS
    # ==========================================================

    print_section(
        "[PART 5] BEHAVIORAL OBSERVATIONS & REVIEW INDICATORS"
    )

    results["behavioral_intelligence"] = safe_run(
        "BEHAVIORAL OBSERVATIONS",
        "behavioral_intelligence",
        report_df,
    )

    results["suspicious_activity"] = safe_run(
        "REVIEW INDICATORS",
        "suspicious_activity",
        report_df,
    )

    # ==========================================================
    # PART 6: CHRONOLOGICAL TIMELINE
    # ==========================================================

    print_timeline(
        report_df,
        max_rows=timeline_limit,
    )

    # Failed imports ki summary.
    print_import_error_summary()

    print("\n" + "=" * 75)
    print(
        "[+] Full forensic report generation completed."
    )
    print("=" * 75)

    return results