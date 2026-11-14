"""Settings and cloud configuration endpoints."""

from __future__ import annotations
from typing import Literal
from fastapi import APIRouter, Depends

from api.container import AppContainer
from api.deps import get_container
from api.errors import ApiError
from api.schemas.settings import AppSettings, CloudSettings, LimitsSettings, UpdateCloudSettings
from core.limits import MAX_CHAT_TURNS, MAX_FILE_MB, MAX_PAGES

router = APIRouter(tags=["settings"])


def _build_app_settings(c: AppContainer) -> AppSettings:
    mode: Literal["local", "cloud"] = "cloud" if c.cloud.enabled else "local"
    provider = c.cloud.provider
    if provider not in ("groq", "openai", "anthropic"):
        provider = "groq"

    return AppSettings(
        mode=mode,
        egress_policy=mode,
        limits=LimitsSettings(
            max_file_mb=MAX_FILE_MB,
            max_pages=MAX_PAGES,
            max_chat_turns=MAX_CHAT_TURNS,
        ),
        cloud=CloudSettings(
            enabled=c.cloud.enabled,
            provider=provider,  # type: ignore[arg-type]
            model=c.cloud.model,
            consented=c.cloud.consented,
            has_key=c.cloud.has_key(provider),
        ),
    )


@router.get("/settings", response_model=AppSettings)
async def get_settings(c: AppContainer = Depends(get_container)) -> AppSettings:
    """Retrieve active system settings, limits, and cloud provider status."""
    return _build_app_settings(c)


@router.put("/settings/cloud", response_model=AppSettings)
async def update_cloud_settings(
    body: UpdateCloudSettings,
    c: AppContainer = Depends(get_container),
) -> AppSettings:
    """Update cloud provider settings, consent, and API key with build-first swap."""
    warning = c.cloud.apply(
        enabled=body.enabled,
        provider=body.provider,
        model=body.model,
        consent=body.consent,
        api_key=body.api_key,
    )
    if warning:
        raise ApiError(
            status_code=400,
            code="cloud_configuration_warning",
            title="Cloud Configuration Warning",
            detail=warning,
        )
    return _build_app_settings(c)


@router.delete("/settings/cloud/credentials", response_model=AppSettings)
async def revoke_cloud_credentials(c: AppContainer = Depends(get_container)) -> AppSettings:
    """Clear in-memory cloud API keys, revoke consent, and revert to local engine."""
    c.cloud.revoke()
    return _build_app_settings(c)
