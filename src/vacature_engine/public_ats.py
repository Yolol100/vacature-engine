"""Backward-compatible public ATS helpers.

New code should use ``vacature_engine.adapters.AdapterRegistry`` so every
source shares the same normalized model and HTTP policy.
"""
from __future__ import annotations

from .adapters import AdapterRegistry
from .http import PublicHttpClient


def greenhouse_jobs(board_token: str, include_content: bool = True):
    if not include_content:
        client = PublicHttpClient()
        return client.get_json(
            f"https://boards-api.greenhouse.io/v1/boards/{board_token.strip().strip('/')}/jobs",
            allowed_hosts={"boards-api.greenhouse.io"},
        )
    return {"jobs": [j.to_dict() for j in AdapterRegistry.create("greenhouse", board_token).fetch()]}


def lever_jobs(site: str, region: str = "global"):
    return [j.to_dict() for j in AdapterRegistry.create("lever", site, region=region).fetch()]
