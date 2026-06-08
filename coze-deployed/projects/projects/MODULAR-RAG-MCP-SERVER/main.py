"""Final Review Helper configuration smoke-test entry point."""

import sys
from pathlib import Path

from src.core.settings import SettingsError, load_settings
from src.observability.logger import get_logger


def main() -> int:
    """
    Load settings and verify the application can initialize.
    
    Returns:
        int: Exit code (0 for success, non-zero for failure)
    """
    print("期末复习助手 - configuration check")

    settings_path = Path("config/settings.yaml")
    try:
        settings = load_settings(settings_path)
    except SettingsError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    logger = get_logger(log_level=settings.observability.log_level)
    logger.info("Settings loaded successfully.")
    logger.info("Use scripts/start_api.py to start the FastAPI server.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
