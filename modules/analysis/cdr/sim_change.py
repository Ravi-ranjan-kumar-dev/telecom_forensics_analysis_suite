import pandas as pd

from .datetime_utils import canonical_datetime


def sim_change(df):
    'Return canonical device, SIM and identifier change review.'

    from modules.analysis.cdr.device_quality import (
        device_change_review,
    )

    return device_change_review(df)
