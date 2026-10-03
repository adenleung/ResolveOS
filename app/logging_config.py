import logging.config
from typing import Any


def configure_logging(log_level: str = "INFO") -> None:
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "level": log_level.upper(),
                }
            },
            "root": {
                "handlers": ["console"],
                "level": log_level.upper(),
            },
        }
    )
