"""Stage 0 smoke check; data and model tests arrive with their stages."""

import config


def test_skeleton_imports() -> None:
    """Confirm the shared configuration imports on a supported interpreter."""
    config.check_python_version()
    assert config.ROOT_DIR.is_dir()
