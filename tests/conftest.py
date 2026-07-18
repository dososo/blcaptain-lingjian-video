"""Test hermeticity guards.

灵剪 CLI 的 `@app.callback` 启动时会把系统安全存储(macOS 钥匙串等)里的凭据
注入本进程 `os.environ`。这是给真实用户的便利,但在 pytest 里所有测试共享同一个
进程:任意一个 CLI 调用一旦触发注入,`os.environ` 就会被真机钥匙串里的 key
(例如 `lingjian:VOLCENGINE_ARK_API_KEY`)污染,后续能力检测/路由测试就会因“凭空多出
发布级画面能力”而非确定性失败(在有该 key 的机器上必挂,在 CI 无 key 机器上却通过)。

下面的 autouse fixture 让每个测试都从一个干净、与真机钥匙串无关的凭据环境开始:
  1. 清掉全部已知密钥名(避免 shell/上一个测试残留泄漏);
  2. 关闭 CLI 启动注入(只 no-op 掉 main 命名空间里绑定的引用,
     `packages.core.credentials.inject_stored_credentials` 本体不动,
     直接单测该函数的用例仍可各自 monkeypatch)。

这样修复只作用于测试进程隔离,不改动任何产品注入逻辑,也不放宽任何发布门禁。
需要显式验证某个 key 存在的测试,请在用例内 `monkeypatch.setenv(...)` 自行设置。
"""

from __future__ import annotations

import pytest

from packages.core.credentials import KNOWN_SECRET_NAMES


@pytest.fixture(autouse=True)
def _isolate_stored_credentials(monkeypatch):
    for name in KNOWN_SECRET_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        "apps.cli.lingjian_cli.main.inject_stored_credentials",
        lambda *args, **kwargs: [],
    )
    yield
