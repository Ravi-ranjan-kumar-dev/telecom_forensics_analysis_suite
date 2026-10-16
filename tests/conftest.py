from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def sample_path(tmp_path: Path) -> Path:
    """Minimal anonymized Airtel GPRS sample for loader tests."""
    source = tmp_path / "airtel_gprs_sample.csv"
    source.write_text(
        "BHARTI AIRTEL LIMITED\n"
        "GPRS OF CELL ID : 405-01-12345 from 11-Jun-2026 00:00:00 to 11-Jun-2026 23:59:59\n"
        "Mobile No.,IP Address,IMEI,IMSI,Downlink Vol,Uplink Vol,Total Vol,Session Start Time,Session End Time,Pre/Post,Roaming Circle,2G/4G/5G,ICR Operator Name,Home Circle,IP,CGI Latitude,CGI Longitude,CGI\n"
        "9876543210,10.0.0.1,123456789012345,405010123456789,100,50,150,11-Jun-2026 12:00:00,11-Jun-2026 12:05:00,PREPAID,Bihar,4G,,Bihar,,25.5941,85.1376,405-01-12345\n",
        encoding="utf-8",
    )
    return source


# --- PySide6 Clean Teardown Hook for Python 3.14 ---
import gc
import pytest

@pytest.fixture(autouse=True)
def _cleanup_qt_widgets():
    yield
    try:
        from PySide6.QtCore import QCoreApplication, QEvent
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            if hasattr(app, "main_window"):
                app.main_window = None
            for widget in list(app.topLevelWidgets()):
                try:
                    widget.close()
                    widget.deleteLater()
                except Exception:
                    pass
            app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()
        gc.collect()
    except Exception:
        pass

@pytest.fixture(autouse=True)
def _clear_enrichment_caches():
    def _clear():
        try:
            from modules.enrichment import cgi_address_enrichment, sdr_subscriber_enrichment
            if hasattr(cgi_address_enrichment, '_lookup_cgi_addresses_cached'):
                cgi_address_enrichment._lookup_cgi_addresses_cached.cache_clear()
            if hasattr(sdr_subscriber_enrichment, 'lookup_sdr_subscribers_cached'):
                sdr_subscriber_enrichment.lookup_sdr_subscribers_cached.cache_clear()
            if hasattr(sdr_subscriber_enrichment, '_SDR_GLOBAL_ROW_CACHE'):
                sdr_subscriber_enrichment._SDR_GLOBAL_ROW_CACHE.clear()
            if hasattr(sdr_subscriber_enrichment, '_SDR_NEGATIVE_CACHE'):
                sdr_subscriber_enrichment._SDR_NEGATIVE_CACHE.clear()
        except Exception:
            pass
    _clear()
    yield
    _clear()
