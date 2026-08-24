"""Central single-CDR analysis pipeline.

Every registered analysis function is executed at most once.  The returned
bundle is reused by the console renderer and Excel report generator.
"""

from __future__ import annotations

import importlib
import time
import traceback
from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd

from modules.enrichment.telecom_master_enrichment import (
    CDR_TABLE_SPECS,
    build_missing_cgi_summary_from_bundle,
    enrich_analysis_bundle,
)
from modules.enrichment.cgi_address_enrichment import enrich_dataframe_with_cgi_address, build_missing_cgi_lookup_summary


@dataclass(frozen=True)
class AnalysisSpec:
    group: str
    result_key: str
    module_path: str
    function_name: str


ANALYSIS_REGISTRY: tuple[AnalysisSpec, ...] = (
    AnalysisSpec("Summary", "cdr_summary", "modules.analysis.cdr.summary", "cdr_summary"),
    AnalysisSpec("Contacts", "top_contacts", "modules.analysis.cdr.contacts", "top_contacts"),
    AnalysisSpec("Contacts", "bottom_contacts", "modules.analysis.cdr.contacts", "bottom_contacts"),
    AnalysisSpec("Contacts", "contact_category_summary", "modules.analysis.cdr.contacts", "contact_category_summary"),
    AnalysisSpec("Contacts", "top_service_sender_ids", "modules.analysis.cdr.contacts", "top_service_sender_ids"),
    AnalysisSpec("Contacts", "top_short_codes", "modules.analysis.cdr.contacts", "top_short_codes"),
    AnalysisSpec("Contacts", "contact_ranking", "modules.analysis.cdr.contacts", "contact_ranking"),
    AnalysisSpec("Contacts", "incoming_outgoing", "modules.analysis.cdr.contacts", "incoming_outgoing"),
    AnalysisSpec("Contacts", "other_call_type_summary", "modules.analysis.cdr.contacts", "other_call_type_summary"),
    AnalysisSpec("Network", "social_network", "modules.analysis.cdr.social_network", "social_network"),
    AnalysisSpec("Location", "analyze_location", "modules.analysis.cdr.location", "analyze_location"),
    AnalysisSpec("Location", "frequent_locations", "modules.analysis.cdr.location", "frequent_locations"),
    AnalysisSpec("Location", "bottom_cgi", "modules.analysis.cdr.location", "bottom_cgi"),
    AnalysisSpec("Movement", "tower_movement", "modules.analysis.cdr.movement", "tower_movement"),
    AnalysisSpec("Movement", "tower_transition", "modules.analysis.cdr.movement", "tower_transition"),
    AnalysisSpec("Movement", "movement_pattern", "modules.analysis.cdr.movement", "movement_pattern"),
    AnalysisSpec("Tower", "tower_intelligence", "modules.analysis.cdr.tower_intelligence", "tower_intelligence"),
    AnalysisSpec("Tower", "home_tower", "modules.analysis.cdr.tower_intelligence", "home_tower"),
    AnalysisSpec("Tower", "work_tower", "modules.analysis.cdr.tower_intelligence", "work_tower"),
    AnalysisSpec("IMEI", "imei_summary", "modules.analysis.cdr.imei", "imei_summary"),
    AnalysisSpec("IMEI", "imei_intelligence", "modules.analysis.cdr.imei", "imei_intelligence"),
    AnalysisSpec("SIM", "sim_change", "modules.analysis.cdr.sim_change", "sim_change"),
    AnalysisSpec("Activity", "activity_summary", "modules.analysis.cdr.activity", "analyze_activity"),
    AnalysisSpec("Activity", "hourly_activity", "modules.analysis.cdr.activity", "hourly_activity"),
    AnalysisSpec("Activity", "daily_activity", "modules.analysis.cdr.activity", "daily_activity"),
    AnalysisSpec("Activity", "weekly_activity", "modules.analysis.cdr.activity", "weekly_activity"),
    AnalysisSpec("Activity", "monthly_activity", "modules.analysis.cdr.activity", "monthly_activity"),
    AnalysisSpec(
        "Behavior",
        "behavioral_intelligence",
        "modules.analysis.cdr.behavioral_intelligence",
        "behavioral_intelligence",
    ),
    AnalysisSpec(
        "Alerts",
        "suspicious_activity",
        "modules.analysis.cdr.suspicious_activity",
        "suspicious_activity",
    ),
)



CGI_ENRICHMENT_RESULT_KEYS = {
    "bottom_cgi",
    "tower_movement",
    "tower_transition",
    "tower_intelligence",
    "home_tower",
    "work_tower",
}


def _apply_cgi_address_enrichment_to_results(results):
    """
    Add tower address details to selected CDR tower analysis results.

    User-facing output stays simple:
    - tower_address_found
    - tower_operator
    - tower_circle
    - tower_town
    - tower_site_name
    - tower_address
    - tower_latitude
    - tower_longitude

    If enrichment fails for any reason, original result is preserved.
    """
    if not isinstance(results, dict):
        return results

    for key in CGI_ENRICHMENT_RESULT_KEYS:
        value = results.get(key)

        try:
            results[key] = enrich_dataframe_with_cgi_address(value)
        except Exception:
            results[key] = value

    try:
        tower_movement = results.get("tower_movement")
        if tower_movement is not None:
            results["missing_cgi_lookup"] = build_missing_cgi_lookup_summary(tower_movement)
    except Exception:
        pass

    return results

def _load_function(spec: AnalysisSpec) -> Callable[[pd.DataFrame], Any]:
    module = importlib.import_module(spec.module_path)
    function = getattr(module, spec.function_name, None)
    if not callable(function):
        raise AttributeError(
            f"Function '{spec.function_name}' not found in '{spec.module_path}'"
        )
    return function


def _find_top_contact(value: Any) -> str | None:
    if not isinstance(value, pd.DataFrame) or value.empty:
        return None

    for column in ("Contact", "contact", "b_party", "Other Party", "other_party"):
        if column in value.columns:
            candidate = str(value.iloc[0][column]).strip()
            return candidate or None
    return None


def _run_top_contact_details(
    df: pd.DataFrame,
    top_contacts_result: Any,
    results: dict[str, Any],
    errors: dict[str, str],
    status_rows: list[dict[str, Any]],
) -> None:
    """Run contact_summary once for the highest-ranked contact, when available."""
    started = time.perf_counter()
    contact = _find_top_contact(top_contacts_result)

    if not contact:
        status_rows.append(
            {
                "Group": "Contacts",
                "Result Key": "top_contact_details",
                "Module": "modules.analysis.cdr.contacts",
                "Function": "contact_summary",
                "Status": "SKIPPED",
                "Duration (sec)": 0.0,
                "Error": "Top contact unavailable",
            }
        )
        return

    try:
        module = importlib.import_module("modules.analysis.cdr.contacts")
        function = getattr(module, "contact_summary", None)
        if not callable(function):
            raise AttributeError("Function 'contact_summary' not found")
        results["top_contact_details"] = function(df, contact)
        status = "COMPLETED"
        error_text = ""
    except Exception as error:
        status = "FAILED"
        error_text = f"{type(error).__name__}: {error}"
        errors["top_contact_details"] = error_text

    status_rows.append(
        {
            "Group": "Contacts",
            "Result Key": "top_contact_details",
            "Module": "modules.analysis.cdr.contacts",
            "Function": "contact_summary",
            "Status": status,
            "Duration (sec)": round(time.perf_counter() - started, 4),
            "Error": error_text,
        }
    )



CGI_ENRICHMENT_RESULT_KEYS = {
    "bottom_cgi",
    "tower_movement",
    "tower_transition",
    "tower_intelligence",
    "home_tower",
    "work_tower",
}


def _looks_like_analysis_result_container(value):
    if not isinstance(value, dict):
        return False

    return any(key in value for key in CGI_ENRICHMENT_RESULT_KEYS)


def _find_analysis_result_container(bundle):
    """
    Find where analysis result dataframes are stored.

    Some report bundles keep results directly:
        bundle["tower_movement"]

    Some keep results nested:
        bundle["results"]["tower_movement"]
        bundle["analysis"]["tower_movement"]
        bundle["analysis_results"]["tower_movement"]

    This helper supports both.
    """
    if not isinstance(bundle, dict):
        return None

    if _looks_like_analysis_result_container(bundle):
        return bundle

    preferred_keys = [
        "results",
        "analysis",
        "analysis_results",
        "analysis_bundle",
        "sheets",
        "data",
    ]

    for key in preferred_keys:
        child = bundle.get(key)
        if _looks_like_analysis_result_container(child):
            return child

    for child in bundle.values():
        if _looks_like_analysis_result_container(child):
            return child

    return None


def _apply_cgi_address_enrichment(
    bundle,
):
    """
    Apply one common batch SDR/CGI lookup to CDR summaries.

    Raw CDR records are not copied or enriched here.
    Lookup failures preserve all original analysis results.
    """

    if not isinstance(
        bundle,
        dict,
    ):
        return bundle

    results = _find_analysis_result_container(
        bundle
    )

    if results is None:
        return bundle

    enrichment = enrich_analysis_bundle(
        results,
        table_specs=CDR_TABLE_SPECS,
    )

    enriched_results = enrichment[
        "bundle"
    ]

    enriched_results[
        "master_enrichment_summary"
    ] = enrichment[
        "summary"
    ]

    enriched_results[
        "master_enrichment_warnings"
    ] = enrichment[
        "warnings"
    ]

    enriched_results[
        "missing_cgi_lookup"
    ] = build_missing_cgi_summary_from_bundle(
        enriched_results,
        table_specs=CDR_TABLE_SPECS,
    )

    results.clear()
    results.update(
        enriched_results
    )

    mirror_keys = {
        *CDR_TABLE_SPECS.keys(),
        "master_enrichment_summary",
        "master_enrichment_warnings",
        "missing_cgi_lookup",
    }

    for key in mirror_keys:
        if key in results:
            bundle[
                key
            ] = results[
                key
            ]

    return bundle


def build_single_analysis_bundle(
    df: pd.DataFrame,
    target: str | None = None,
) -> dict[str, Any]:
    """Execute every registered single-CDR analysis independently and once."""
    results: dict[str, Any] = {}
    errors: dict[str, str] = {}
    status_rows: list[dict[str, Any]] = []

    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        message = "DataFrame is empty or invalid"
        return {
            "target": str(target or ""),
            "results": results,
            "errors": {"input": message},
            "status": pd.DataFrame(
                [{
                    "Group": "Input",
                    "Result Key": "input",
                    "Module": "",
                    "Function": "",
                    "Status": "FAILED",
                    "Duration (sec)": 0.0,
                    "Error": message,
                }]
            ),
        }

    for spec in ANALYSIS_REGISTRY:
        started = time.perf_counter()
        status = "COMPLETED"
        error_text = ""

        try:
            function = _load_function(spec)
            results[spec.result_key] = function(df)
        except ModuleNotFoundError as error:
            status = "MISSING"
            error_text = f"{type(error).__name__}: {error}"
            errors[spec.result_key] = error_text
        except Exception as error:
            status = "FAILED"
            error_text = f"{type(error).__name__}: {error}"
            errors[spec.result_key] = error_text
            errors[f"{spec.result_key}_traceback"] = traceback.format_exc(limit=4)

        status_rows.append(
            {
                "Group": spec.group,
                "Result Key": spec.result_key,
                "Module": spec.module_path,
                "Function": spec.function_name,
                "Status": status,
                "Duration (sec)": round(time.perf_counter() - started, 4),
                "Error": error_text,
            }
        )

    _run_top_contact_details(
        df=df,
        top_contacts_result=results.get("top_contacts"),
        results=results,
        errors=errors,
        status_rows=status_rows,
    )

    status_frame = pd.DataFrame(status_rows)
    return _apply_cgi_address_enrichment({
        "target": str(target or ""),
        "results": results,
        "errors": errors,
        "status": status_frame,
    })


def analysis_completion_summary(bundle: dict[str, Any]) -> dict[str, int]:
    """Return completed, failed, missing and skipped function counts."""
    status = bundle.get("status") if isinstance(bundle, dict) else None
    if not isinstance(status, pd.DataFrame) or status.empty or "Status" not in status:
        return {"completed": 0, "failed": 0, "missing": 0, "skipped": 0, "total": 0}

    counts = status["Status"].astype(str).str.upper().value_counts()
    return {
        "completed": int(counts.get("COMPLETED", 0)),
        "failed": int(counts.get("FAILED", 0)),
        "missing": int(counts.get("MISSING", 0)),
        "skipped": int(counts.get("SKIPPED", 0)),
        "total": int(len(status)),
    }
