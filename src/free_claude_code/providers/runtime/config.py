"""Provider configuration construction from neutral catalog metadata."""

from urllib.parse import urlparse

from loguru import logger

from free_claude_code.application.errors import ApplicationUnavailableError
from free_claude_code.config.provider_catalog import ProviderDescriptor
from free_claude_code.config.settings import Settings
from free_claude_code.providers.base import ProviderConfig

_SUPPORTED_PROXY_SCHEMES = frozenset({"http", "https", "socks4", "socks5", "socks5h"})


def string_setting(settings: Settings, attr_name: str | None, default: str = "") -> str:
    """Return a string-valued settings attribute, ignoring non-string mocks."""
    if attr_name is None:
        return default
    value = getattr(settings, attr_name, default)
    return value if isinstance(value, str) else default


def provider_credential(descriptor: ProviderDescriptor, settings: Settings) -> str:
    """Return the configured credential for a provider descriptor."""
    if descriptor.static_credential is not None:
        return descriptor.static_credential
    if descriptor.credential_attr:
        return string_setting(settings, descriptor.credential_attr)
    return ""


def has_provider_configuration(
    descriptor: ProviderDescriptor, settings: Settings
) -> bool:
    """Return whether all provider-defining settings are present."""
    attrs = descriptor.configuration_attrs()
    if attrs:
        return all(string_setting(settings, attr).strip() for attr in attrs)
    return descriptor.static_credential is not None


def require_provider_credential(
    descriptor: ProviderDescriptor, credential: str
) -> None:
    """Raise a user-facing configuration error when a required key is missing."""
    if descriptor.credential_env is None:
        return
    if credential and credential.strip():
        return
    message = f"{descriptor.credential_env} is not set. Add it to your .env file."
    if descriptor.credential_url:
        message = f"{message} Get a key at {descriptor.credential_url}"
    raise ApplicationUnavailableError(message)


def _normalize_proxy_url(raw: str) -> str:
    """Validate and normalise a provider proxy URL.

    Bare ``host:port`` strings are upgraded to ``http://host:port``.
    Unsupported schemes are rejected with a clear error so users get
    immediate feedback instead of a silent failure at request time.
    """
    if not raw or not raw.strip():
        return ""
    stripped = raw.strip()
    if "://" not in stripped:
        stripped = f"http://{stripped}"
    parsed = urlparse(stripped)
    if parsed.scheme not in _SUPPORTED_PROXY_SCHEMES:
        logger.warning(
            "PROXY: unsupported proxy scheme {!r} in {!r}; "
            "httpx supports http, https, socks4, socks5, socks5h. "
            "The proxy setting will be ignored.",
            parsed.scheme,
            raw,
        )
        return ""
    return stripped


def build_provider_config(
    descriptor: ProviderDescriptor, settings: Settings
) -> ProviderConfig:
    """Build shared provider configuration for one provider descriptor."""
    credential = provider_credential(descriptor, settings)
    require_provider_credential(descriptor, credential)
    base_url = string_setting(
        settings, descriptor.base_url_attr, descriptor.default_base_url or ""
    )
    resolved_base_url = base_url or descriptor.default_base_url
    if not resolved_base_url:
        raise AssertionError(
            f"Provider {descriptor.provider_id!r} has no configured base URL."
        )
    proxy = _normalize_proxy_url(string_setting(settings, descriptor.proxy_attr))
    return ProviderConfig(
        api_key=credential,
        base_url=resolved_base_url,
        rate_limit=settings.provider_rate_limit,
        rate_window=settings.provider_rate_window,
        max_concurrency=settings.provider_max_concurrency,
        http_read_timeout=settings.http_read_timeout,
        http_write_timeout=settings.http_write_timeout,
        http_connect_timeout=settings.http_connect_timeout,
        proxy=proxy,
        log_raw_sse_events=settings.log_raw_sse_events,
        log_api_error_tracebacks=settings.log_api_error_tracebacks,
    )
