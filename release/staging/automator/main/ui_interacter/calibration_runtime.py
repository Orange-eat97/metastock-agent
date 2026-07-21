from __future__ import annotations

import os
from typing import Optional

from ui_interacter.coordinate_calibration import (
    CalibrationStore,
    CoordinateMapper,
)
from ui_interacter.ui_core import log


CALIBRATION_PROFILE_ENV = "METASTOCK_CALIBRATION_PROFILE"


def resolve_calibration_profile_name(
    store: CalibrationStore,
) -> str | None:
    explicit_profile = (
        os.getenv(CALIBRATION_PROFILE_ENV)
        or ""
    ).strip()

    if explicit_profile:
        return explicit_profile

    active_profile = store.get_active_profile_name()

    if active_profile:
        os.environ[CALIBRATION_PROFILE_ENV] = (
            active_profile
        )

    return active_profile


def load_coordinate_mapper_from_env() -> Optional[CoordinateMapper]:
    """
    Load the active coordinate profile for the current process.

    Priority:
      1. METASTOCK_CALIBRATION_PROFILE;
      2. the active-profile marker in the calibration directory;
      3. default.json when it exists.

    When no profile is available, existing UIA and baseline coordinate
    behavior remains unchanged.
    """
    store = CalibrationStore()
    profile_name = resolve_calibration_profile_name(
        store
    )

    if not profile_name:
        return None

    profile = store.load(profile_name)
    log(
        "Loaded MetaStock calibration profile: "
        f"{profile_name!r} from {store.directory}"
    )
    return CoordinateMapper(profile)
