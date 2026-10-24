"""Shared project settings; importing this module does not write files."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
import sys

PROJECT_NAME: str = "Cancer Clock"
STAGE: int = 5
MIN_PYTHON: tuple[int, int] = (3, 11)
ROOT_DIR: Path = Path(__file__).resolve().parent
DATA_DIR: Path = ROOT_DIR / "data"
RAW_DIR: Path = DATA_DIR / "raw"
PROCESSED_DIR: Path = DATA_DIR / "processed"
STATIC_DIR: Path = DATA_DIR / "static"
OUTPUTS_DIR: Path = ROOT_DIR / "outputs"
DOCS_DIR: Path = ROOT_DIR / "docs"
START_PERIOD: date = date(2023, 10, 1)
BACKLOG_START: date = date(2023, 4, 9)
EVALUATION_START: date = date(2023, 10, 1)
FORECAST_HORIZONS_WEEKS: tuple[int, ...] = (4, 8, 12)
FORECAST_QUANTILES: tuple[float, ...] = (0.1, 0.5, 0.9)
RANDOM_SEED: int = 42
WEB_UPLOAD_MAX_FILES: int = 100
WEB_UPLOAD_MAX_FILE_BYTES: int = 25_000_000
DISCLAIMER: str = (
    "Planning information, not medical advice. "
    "Forecasts are hospital-level, not personal."
)


@dataclass(frozen=True)
class Assumption:
    """An explicit proposed default, with provenance and verification status."""

    value: int | float
    unit: str
    source: str
    status: str
    caveat: str


ASSUMPTIONS: dict[str, Assumption] = {
    "publication_lag_months": Assumption(
        value=2,
        unit="calendar months after observation month",
        source="User build brief; not independently verified in Stage 0",
        status="assumed",
        caveat="Approximate availability only; does not reconstruct historical revisions.",
    ),
    "publication_day": Assumption(
        value=14,
        unit="day of publication month",
        source="User build brief; not independently verified in Stage 0",
        status="assumed",
        caveat="Not guaranteed conservative. Prefer an evidenced release date.",
    ),
    "strike_capacity_factor": Assumption(
        value=0.952,
        unit="multiplier of scenario capacity",
        source="User build brief; claimed national activity ratio, unverified in Stage 0",
        status="assumed",
        caveat="National activity is not a measured trust-level cancer capacity effect.",
    ),
}


def check_python_version() -> None:
    """Fail clearly if the interpreter is older than the supported minimum."""
    if sys.version_info[:2] < MIN_PYTHON:
        raise RuntimeError("Python 3.11 or newer is required.")


def ensure_directories() -> None:
    """Create local working directories, including the excluded raw-data folder."""
    for directory in (RAW_DIR, PROCESSED_DIR, STATIC_DIR, OUTPUTS_DIR, DOCS_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def main() -> None:
    """Check the runtime and initialise directories without downloading data."""
    check_python_version()
    ensure_directories()
    print(f"{PROJECT_NAME} | Stage {STAGE} configuration ready")
    print("Python requirement: 3.11+ OK")
    print("Working directories ready; no data downloaded.")
    print(DISCLAIMER)


if __name__ == "__main__":
    main()
