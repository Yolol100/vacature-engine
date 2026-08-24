from __future__ import annotations

from typing import Any


def search_public_catalog(**kwargs: Any) -> list[dict[str, Any]]:
    """Query the optional keyless ats-scrapers hosted dataset.

    This intentionally imports only the base package. Do not install or invoke
    scraper extras here; the vacature-search Skill remains responsible for
    access-policy decisions and canonical verification.
    """
    try:
        from ats_scrapers import search
    except ImportError as exc:
        raise RuntimeError('Install optional dependency: pip install "vacature-engine[catalog]"') from exc
    frame = search(**kwargs)
    if hasattr(frame, "to_dict"):
        return frame.to_dict(orient="records")
    raise RuntimeError("ats-scrapers search returned an unsupported result")
