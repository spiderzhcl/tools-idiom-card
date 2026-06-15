"""remoteapi 高级接口 —— 文生图 & 图生图。

对 AgnesImageClient 做轻量级封装，提供更易用的函数接口。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .agnes_client import AgnesImageClient, download_image


# ---------------------------------------------------------------------------
# 文生图
# ---------------------------------------------------------------------------

def text_to_image(
    prompt: str,
    size: str = "1200x1600",
    n: int = 1,
    model: str = "agnes-image-2.1-flash",
    output_dir: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """调用 Agnes AI 文生图 API。

    Args:
        prompt: 图像描述文本，越详细越好。推荐结构：
                [主体] + [场景/环境] + [风格] + [光照] + [构图] + [质量要求]
        size: 输出图像尺寸，如 "1024x1024"、"1024x768"、"768x1024"
        n: 生成图像数量
        model: 文生图模型，默认 agnes-image-2.1-flash
        output_dir: 可选，指定时将生成的图像下载到该目录
        api_key: 可选，覆盖默认 API Key
        base_url: 可选，覆盖默认 Base URL

    Returns:
        响应字典:
        {
            "created": <int 时间戳>,
            "data": [{"url": "https://..."}, ...],
            "local_paths": ["D:/.../output/image_xxx.png", ...]  # 仅当指定 output_dir 时
        }

    API Endpoint:
        POST https://apihub.agnes-ai.com/v1/images/generations
        Header: Authorization: Bearer <API_KEY>
    """
    with AgnesImageClient(api_key=api_key, base_url=base_url) as client:
        result = client.text_to_image(prompt=prompt, size=size, n=n, model=model)

    if output_dir:
        local_paths: List[str] = []
        for item in result["data"]:
            path = download_image(item["url"], output_dir=output_dir)
            local_paths.append(path)
        result["local_paths"] = local_paths

    return result


# ---------------------------------------------------------------------------
# 图生图
# ---------------------------------------------------------------------------

def image_to_image(
    prompt: str,
    image_urls: List[str],
    size: str = "1200x1600",
    model: str = "agnes-image-2.0-flash",
    seed: Optional[int] = None,
    output_dir: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """调用 Agnes AI 图生图 API。

    Args:
        prompt: 描述想要的变化。推荐结构：
                [需要改变什么] + [需要保持什么不变]
        image_urls: 参考图像列表，支持 URL 或本地文件路径（一张或多张）
        size: 输出图像尺寸
        model: 图生图推荐使用 agnes-image-2.0-flash
        seed: 可选，随机种子；固定值可复现结果
        output_dir: 可选，指定时将生成的图像下载到该目录
        api_key: 可选，覆盖默认 API Key
        base_url: 可选，覆盖默认 Base URL

    Returns:
        响应字典（格式同 text_to_image）
    """
    if not image_urls:
        raise ValueError("image_urls 参数必须至少提供一个图像（URL 或本地文件路径）")

    with AgnesImageClient(api_key=api_key, base_url=base_url) as client:
        result = client.image_to_image(
            prompt=prompt,
            image_urls=image_urls,
            size=size,
            model=model,
            seed=seed,
        )

    if output_dir:
        local_paths: List[str] = []
        for item in result["data"]:
            path = download_image(item["url"], output_dir=output_dir)
            local_paths.append(path)
        result["local_paths"] = local_paths

    return result
