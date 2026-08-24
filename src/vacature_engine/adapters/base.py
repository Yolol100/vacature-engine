from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from ..http import PublicHttpClient
from ..models import JobRecord


class BaseAdapter(ABC):
    source: ClassVar[str]

    def __init__(self, slug: str, *, client: PublicHttpClient | None = None) -> None:
        slug = slug.strip().strip("/")
        if not slug:
            raise ValueError("slug required")
        self.slug = slug
        self.client = client or PublicHttpClient()

    @abstractmethod
    def fetch(self) -> list[JobRecord]:
        raise NotImplementedError


class AdapterRegistry:
    _adapters: dict[str, type[BaseAdapter]] = {}

    @classmethod
    def register(cls, adapter: type[BaseAdapter]) -> type[BaseAdapter]:
        cls._adapters[adapter.source] = adapter
        return adapter

    @classmethod
    def create(cls, source: str, slug: str, **kwargs: object) -> BaseAdapter:
        key = source.strip().lower()
        try:
            adapter_cls = cls._adapters[key]
        except KeyError as exc:
            raise ValueError(f"unsupported adapter: {source}; available={sorted(cls._adapters)}") from exc
        return adapter_cls(slug, **kwargs)  # type: ignore[arg-type]

    @classmethod
    def available(cls) -> list[str]:
        return sorted(cls._adapters)
