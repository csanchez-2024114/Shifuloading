"""
geo_service — IP → timezone + location via GeoLite2-City.

Uses a module-level Reader singleton so the mmdb file is opened once
at startup and reused across all requests (thread/async safe for reads).

Local development override (set in .env):
    GEOIP_DEV_TIMEZONE=America/Guatemala
    GEOIP_DEV_LOCATION=Guatemala City, Guatemala
  When the client IP is private/loopback these values are returned instead
  of an empty result, so timezone-dependent features work in local dev.

Returns:
    get_geo_from_ip(ip) -> GeoResult(timezone, location)
        timezone : IANA string, e.g. "America/Guatemala"  (None on miss)
        location : human string, e.g. "Guatemala City, Guatemala" (None on miss)
"""

from __future__ import annotations

import ipaddress
import logging
import os
from dataclasses import dataclass
from pathlib import Path

import geoip2.database
import geoip2.errors

logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).parent.parent / "core" / "geoip" / "GeoLite2-City.mmdb"

_reader: geoip2.database.Reader | None = None

# Local dev overrides — used when the client IP is private/loopback.
_DEV_TIMEZONE = os.getenv("GEOIP_DEV_TIMEZONE", "").strip() or None
_DEV_LOCATION = os.getenv("GEOIP_DEV_LOCATION", "").strip() or None


def _get_reader() -> geoip2.database.Reader | None:
    global _reader
    if _reader is not None:
        return _reader
    if not _DB_PATH.exists():
        logger.warning("[geo_service] GeoLite2-City.mmdb not found at %s", _DB_PATH)
        return None
    try:
        _reader = geoip2.database.Reader(str(_DB_PATH))
        logger.info("[geo_service] GeoLite2-City loaded from %s", _DB_PATH)
    except Exception as exc:
        logger.warning("[geo_service] failed to open mmdb: %s", exc)
    return _reader


@dataclass
class GeoResult:
    timezone:     str | None = None
    location:     str | None = None
    country_code: str | None = None  # ISO 3166-1 alpha-2, e.g. "GT", "MX", "US"


def get_geo_from_ip(ip: str | None) -> GeoResult:
    """
    Resolve an IP address to timezone + location using GeoLite2-City.

    For private/loopback IPs (local dev), returns GEOIP_DEV_TIMEZONE /
    GEOIP_DEV_LOCATION env vars if set, otherwise empty GeoResult.
    """
    if not ip:
        return GeoResult(timezone=_DEV_TIMEZONE, location=_DEV_LOCATION) if _DEV_TIMEZONE else GeoResult()

    # Check if private/loopback before trying GeoIP.
    _is_local = False
    try:
        addr = ipaddress.ip_address(ip)
        _is_local = addr.is_private or addr.is_loopback or addr.is_link_local
    except ValueError:
        return GeoResult()

    if _is_local:
        if _DEV_TIMEZONE:
            logger.debug("[geo_service] local IP %s — using dev override tz=%s loc=%s", ip, _DEV_TIMEZONE, _DEV_LOCATION)
            # Infer country_code from dev location string (first word after last comma)
            _dev_cc = None
            if _DEV_LOCATION:
                _country = _DEV_LOCATION.split(",")[-1].strip().lower()
                _cc_map = {"guatemala": "GT", "mexico": "MX", "united states": "US",
                           "spain": "ES", "colombia": "CO", "argentina": "AR"}
                _dev_cc = _cc_map.get(_country)
            return GeoResult(timezone=_DEV_TIMEZONE, location=_DEV_LOCATION, country_code=_dev_cc)
        return GeoResult()

    reader = _get_reader()
    if reader is None:
        return GeoResult()

    try:
        record = reader.city(ip)
        timezone = record.location.time_zone or None

        parts: list[str] = []
        city = record.city.name
        country = record.country.name
        if city:
            parts.append(city)
        if country:
            parts.append(country)
        location = ", ".join(parts) or None

        return GeoResult(
            timezone=timezone,
            location=location,
            country_code=record.country.iso_code or None,
        )

    except geoip2.errors.AddressNotFoundError:
        return GeoResult()
    except Exception as exc:
        logger.debug("[geo_service] lookup failed for %s: %s", ip, exc)
        return GeoResult()


def extract_client_ip(headers: dict[str, str], fallback: str | None) -> str | None:
    """
    Extract the real client IP from request headers, with proxy support.

    Priority:
      1. CF-Connecting-IP   — Cloudflare
      2. X-Real-IP          — Nginx single-proxy
      3. X-Forwarded-For    — first entry (leftmost = client)
      4. fallback           — websocket.client.host
    """
    for header in ("cf-connecting-ip", "x-real-ip"):
        val = headers.get(header, "").strip()
        if val:
            return val

    forwarded = headers.get("x-forwarded-for", "").strip()
    if forwarded:
        first = forwarded.split(",")[0].strip()
        if first:
            return first

    return fallback or None
