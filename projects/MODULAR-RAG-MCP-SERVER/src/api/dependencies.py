"""Shared dependency injection for FastAPI routers."""

from __future__ import annotations

from functools import lru_cache

from src.core.settings import Settings, load_settings


@lru_cache()
def get_settings() -> Settings:
    return load_settings()


def get_data_service():
    from src.observability.dashboard.services.data_service import DataService
    return DataService()


def get_trace_service():
    from src.observability.dashboard.services.trace_service import TraceService
    return TraceService()


def get_config_service():
    from src.observability.dashboard.services.config_service import ConfigService
    return ConfigService()
