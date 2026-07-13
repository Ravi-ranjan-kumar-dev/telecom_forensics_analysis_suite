"""Self-contained project smoke tests.

The previous file opened a real data/cdr1.csv at import time, which made pytest
collection depend on local evidence files. Tests must never require live case data.
"""


def test_core_packages_import_without_evidence_files():
    import modules.analysis.cdr  # noqa: F401
    import modules.cases  # noqa: F401
    import modules.loader.single_loader  # noqa: F401
