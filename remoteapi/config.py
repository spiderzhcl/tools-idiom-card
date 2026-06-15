"""remoteapi 配置管理。

封装 Agnes AI API Key、Base URL 以及默认模型名称。

配置优先级（从高到低）：
  1. 代码中通过 set_api_key() / set_base_url() 动态设置
  2. 环境变量 AGNES_API_KEY / AGNES_BASE_URL
  3. 当前项目根目录下的 .env 文件（若存在）
  4. 默认值（空 key / 默认 Base URL）
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv

    # 尝试从当前项目根目录加载 .env
    _project_root = Path(__file__).resolve().parent.parent
    _env_path = _project_root / ".env"
    if _env_path.exists():
        load_dotenv(dotenv_path=str(_env_path))
except ImportError:
    pass


AGNES_BASE_URL = os.getenv("AGNES_BASE_URL", "https://apihub.agnes-ai.com/v1")
AGNES_API_KEY = os.getenv("AGNES_API_KEY", "")

MODEL_IMAGE_21_FLASH = "agnes-image-2.1-flash"
MODEL_IMAGE_20_FLASH = "agnes-image-2.0-flash"


def set_api_key(key: str) -> None:
    """动态设置 Agnes AI API Key。"""
    global AGNES_API_KEY
    AGNES_API_KEY = key


def set_base_url(url: str) -> None:
    """动态设置 Agnes AI Base URL。"""
    global AGNES_BASE_URL
    AGNES_BASE_URL = url


def validate_api_key() -> Optional[str]:
    """检查 API Key 是否已配置（非空且非占位符）。若未配置返回错误信息字符串。"""
    if not AGNES_API_KEY or AGNES_API_KEY == "YOUR_API_KEY_HERE":
        return (
            "Agnes AI API Key 未设置。请在项目根目录的 .env 文件中，将 "
            "'AGNES_API_KEY=YOUR_API_KEY_HERE' 的值替换为你的实际 Key，"
            "或通过环境变量 AGNES_API_KEY 设置，"
            "或调用 remoteapi.set_api_key('your-key') 动态设置。"
        )
    return None
