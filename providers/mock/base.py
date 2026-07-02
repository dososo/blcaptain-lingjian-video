from __future__ import annotations

from providers.base import LicenseInfo, Provider, ProviderStatus


class MockProvider(Provider):
    def __init__(self, provider_id: str, name: str, kind: str, capabilities: list[str]) -> None:
        self.id = provider_id
        self.name = name
        self.kind = kind
        self.capabilities = capabilities
        self.is_mock = True

    def is_installed(self) -> bool:
        return True

    def is_configured(self) -> bool:
        return True

    def doctor(self) -> ProviderStatus:
        return ProviderStatus(self.id, True, "mock provider 可用于测试和预览,不能 release。")

    def setup_hint(self) -> str:
        return "无需配置。mock 只能用于测试、预览和非 release 导出。"

    def license_info(self) -> LicenseInfo:
        return LicenseInfo("Project test fixture")
