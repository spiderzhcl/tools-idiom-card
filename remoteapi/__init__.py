"""remoteapi —— 远程 AI 图像生成服务接口（仅 Agnes AI 云服务）。

提供文生图 (T2I) 和图生图 (I2I) 两种工作流。

使用示例：
    from remoteapi import text_to_image, image_to_image

    # 文生图
    result = text_to_image("一只穿着西装的柴犬", size="1024x1024", output_dir="output")

    # 图生图
    result = image_to_image(
        "水彩画风格，柔和色彩",
        image_urls=["assets/ref.jpg"],
        size="1024x1024",
        output_dir="output",
    )
"""

from .api import text_to_image, image_to_image
from .config import (
    AGNES_API_KEY,
    AGNES_BASE_URL,
    MODEL_IMAGE_20_FLASH,
    MODEL_IMAGE_21_FLASH,
    set_api_key,
    set_base_url,
)

__all__ = [
    "text_to_image",
    "image_to_image",
    "AGNES_API_KEY",
    "AGNES_BASE_URL",
    "MODEL_IMAGE_20_FLASH",
    "MODEL_IMAGE_21_FLASH",
    "set_api_key",
    "set_base_url",
]
