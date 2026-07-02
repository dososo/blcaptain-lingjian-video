from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProviderStatus:
    id: str
    ok: bool
    message_zh: str


@dataclass(frozen=True, slots=True)
class LicenseInfo:
    name: str
    url: str | None = None


class Provider(ABC):
    id: str
    name: str
    kind: str
    capabilities: list[str]
    is_mock: bool

    @abstractmethod
    def is_installed(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def is_configured(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def doctor(self) -> ProviderStatus:
        raise NotImplementedError

    @abstractmethod
    def setup_hint(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def license_info(self) -> LicenseInfo:
        raise NotImplementedError
