#!/usr/bin/env python3
"""仅演示 I/O 契约,非真实模型,禁止用于 release 冒充。"""

from __future__ import annotations

import json
import sys


def main() -> None:
    json.load(sys.stdin)
    print(
        json.dumps(
            {
                "scenes": [
                    {
                        "id": "s1",
                        "narration_text": "这里只是 provider 契约示例,不能作为真实发布内容。",
                    }
                ]
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
