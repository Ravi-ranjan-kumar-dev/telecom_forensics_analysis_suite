# modules/loader/path_manager.py

from pathlib import Path


# ==============================================================
# PROJECT PATHS
# ==============================================================

# path_manager.py
# └── loader
#     └── modules
#         └── CDR_Analyzer
PROJECT_ROOT = Path(__file__).resolve().parents[2]

BASE_DATA = PROJECT_ROOT / "data"


# ==============================================================
# ALLOWED DIRECTORY VALUES
# ==============================================================

VALID_DATASETS = {
    "cdr",
    "ipdr",
    "tower_dump",
}

VALID_MODES = {
    "single",
    "multiple",
}


# ==============================================================
# DATA PATH GENERATOR
# ==============================================================

def get_data_path(dataset, mode, create=True):
    """
    Dataset ke liye absolute data-directory path return karta hai.

    Parameters:
        dataset:
            cdr | ipdr | tower_dump

        mode:
            single | multiple

        create:
            True hone par missing directory automatically create hogi.

    Returns:
        Absolute path as string.

    Raises:
        ValueError:
            Agar dataset ya mode invalid ho.

        OSError:
            Agar directory create nahi ho paye.
    """

    if not isinstance(dataset, str):
        raise TypeError(
            "dataset string hona chahiye. "
            f"Received: {type(dataset).__name__}"
        )

    if not isinstance(mode, str):
        raise TypeError(
            "mode string hona chahiye. "
            f"Received: {type(mode).__name__}"
        )

    dataset = dataset.strip().lower()
    mode = mode.strip().lower()

    if dataset not in VALID_DATASETS:
        raise ValueError(
            f"Invalid dataset: '{dataset}'. "
            f"Allowed values: {sorted(VALID_DATASETS)}"
        )

    if mode not in VALID_MODES:
        raise ValueError(
            f"Invalid mode: '{mode}'. "
            f"Allowed values: {sorted(VALID_MODES)}"
        )

    path = BASE_DATA / dataset / mode

    if create:
        try:
            path.mkdir(
                parents=True,
                exist_ok=True,
            )

        except OSError as error:
            raise OSError(
                f"Directory create nahi ho payi: {path}. "
                f"Reason: {error}"
            ) from error

    return str(path.resolve())


# ==============================================================
# OPTIONAL HELPER FUNCTIONS
# ==============================================================

def get_project_root():
    """Project root ka absolute path return karta hai."""

    return str(PROJECT_ROOT)


def get_base_data_path():
    """Main data folder ka absolute path return karta hai."""

    return str(BASE_DATA)