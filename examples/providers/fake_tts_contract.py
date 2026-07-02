#!/usr/bin/env python3
"""仅演示 I/O 契约,非真实语音引擎,禁止用于 release 冒充。"""

from __future__ import annotations

import base64
import json
import sys


def main() -> None:
    json.load(sys.stdin)
    print(
        json.dumps(
            {
                "audio_base64": base64.b64encode(b"contract example audio").decode("ascii"),
                "duration_sec": 1.0,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
