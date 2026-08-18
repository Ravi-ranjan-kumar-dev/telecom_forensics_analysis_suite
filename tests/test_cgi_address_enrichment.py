from __future__ import annotations

import duckdb
import pytest

from modules.enrichment import (
    cgi_address_enrichment,
)


def test_missing_cgi_table_returns_an_empty_lookup(
    monkeypatch,
):
    def missing_table(
        *_args,
        **_kwargs,
    ):
        raise duckdb.CatalogException(
            "Table with name cgi_addresses does not exist!"
        )
    monkeypatch.setattr(
        cgi_address_enrichment,
        "query_dataframe",
        missing_table,
    )

    result = (
        cgi_address_enrichment
        .lookup_cgi_addresses(
            [
                "405-70-123-456"
            ]
        )
    )

    assert result.empty
    assert list(
        result.columns
    ) == (
        cgi_address_enrichment
        .CGI_LOOKUP_COLUMNS
    )


def test_unrelated_catalog_error_is_not_hidden(
    monkeypatch,
):
    def invalid_query(
        *_args,
        **_kwargs,
    ):
        raise duckdb.CatalogException(
            "Unrelated catalog failure"
        )

    monkeypatch.setattr(
        cgi_address_enrichment,
        "query_dataframe",
        invalid_query,
    )

    with pytest.raises(
        duckdb.CatalogException,
        match="Unrelated catalog failure",
    ):
        (
            cgi_address_enrichment
            .lookup_cgi_addresses(
                [
                    "405-70-123-456"
                ]
            )
        )
