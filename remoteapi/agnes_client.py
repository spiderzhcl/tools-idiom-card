"""Agnes AI 图像生成客户端（核心实现）。

提供文生图（T2I）和图生图（I2I）两种工作流，以及图像下载功能。

API 文档参考: https://agnes-ai.com/doc/agnes-image-21-flash
"""

from __future__ import annotations

import base64
import mimetypes
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, List, Optional

from . import config as _cfg


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _is_url(s: str) -> bool:
    return s.startswith(("http://", "https://"))


def _encode_local_image(path: str) -> str:
    """将本地图片文件编码为 data URI 字符串。"""
    abs_path = os.path.abspath(path)
    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"找不到参考图文件: {abs_path}")
    mime_type, _ = mimetypes.guess_type(abs_path)
    if not mime_type:
        mime_type = "image/jpeg"
    with open(abs_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime_type};base64,{b64}"


def _prepare_image_inputs(images: List[str]) -> List[str]:
    """准备图片输入列表：URL 保持原样，本地文件转为 data URI。"""
    result: List[str] = []
    for img in images:
        if _is_url(img):
            result.append(img)
        else:
            result.append(_encode_local_image(img))
    return result


def _probe_content_length(url: str, timeout: float = 30.0) -> Optional[int]:
    """通过 HEAD 请求获取文件总大小；服务器不支持 HEAD 则返回 None。"""
    import httpx
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.head(url)
            if resp.status_code < 400 and "Content-Length" in resp.headers:
                return int(resp.headers["Content-Length"])
    except Exception:
        pass
    return None


def _download_range(url: str, part_file: str, start: int, end: int,
                    timeout: float = 300.0,
                    max_retries: int = 5) -> int:
    """下载 [start, end] 字节区间到 `part_file`。

    每个区间使用独立的 part 文件（每个 _download_range 调用）：
    - 如果文件已存在且大小 >= 期望值：认为已完成；
    - 否则每次失败都会清空该文件并从头重新请求 [start, end]；
    - 不做复杂的断点续传只在多个线程写入，避免数据错乱。
    """
    import httpx
    last_error: Optional[Exception] = None

    expected_bytes = end - start + 1

    # 快速路径: 如果文件已完整存在，复用。
    if os.path.exists(part_file):
        try:
            if os.path.getsize(part_file) >= expected_bytes:
                return expected_bytes
        except OSError:
            pass
        # 否则清空损坏的文件，重开新请求
        try:
            os.remove(part_file)
        except OSError:
            pass

    for attempt in range(1, max_retries + 1):
        try:
            headers = {"Range": f"bytes={start}-{end}"}
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                with client.stream("GET", url, headers=headers) as resp:
                    if resp.status_code not in (200, 206):
                        resp.raise_for_status()
                    with open(part_file, "wb") as f:
                        for chunk in resp.iter_bytes(chunk_size=65536):
                            if chunk:
                                f.write(chunk)
            have = os.path.getsize(part_file)
            if have >= expected_bytes:
                return have
            print(f"[download_range WARN] 仅收到 {have}/{expected_bytes} 字节，重试...")
            try: os.remove(part_file)
            except OSError: pass
        except Exception as e:
            last_error = e
            print(f"[download_range WARN] 区间 {start}-{end} 第{attempt}次失败: {e}")
            try:
                if os.path.exists(part_file):
                    os.remove(part_file)
            except OSError:
                pass
            if attempt < max_retries:
                time.sleep(min(2 * attempt, 10))

    if last_error is not None:
        raise last_error
    raise RuntimeError(f"区间 {start}-{end} 下载失败")


def download_image(
    url: str,
    output_dir: str = "output",
    filename: Optional[str] = None,
    max_retries: int = 5,
    chunk_size_mb: int = 4,
    num_workers: int = 4,
) -> str:
    """下载图像 URL 到本地文件。

    **关键能力**
    - HTTP Range 分块并发下载（默认 4 线程，每块 4MB）
    - 断点续传：已写入的字节区间不会重复下载
    - 自动重试（指数退避），失败不会重新提交图像生成任务
    - 若服务器不支持 Range，自动退化为单线程流式下载（同样带重试）

    Args:
        url: 图像 URL
        output_dir: 输出目录，默认 output
        filename: 可选文件名；未指定时自动提取或使用时间戳
        max_retries: 单个区间或整文件的最大重试次数（内部使用）
        chunk_size_mb: 每个并发分块的大小，单位 MB
        num_workers: 并发线程数

    Returns:
        本地文件绝对路径
    """
    os.makedirs(output_dir, exist_ok=True)

    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        url_filename = os.path.basename(url).split("?")[0]
        if not url_filename.endswith((".png", ".jpg", ".jpeg", ".webp")):
            filename = f"image_{timestamp}.png"
        else:
            filename = f"{timestamp}_{url_filename}"

    filepath = os.path.join(output_dir, filename)
    temp_filepath = filepath + ".part"

    # 先检查目标是否已存在且合理大小 → 直接复用
    if os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
        print(f"[download_image INFO] 复用已有文件: {filepath}")
        return os.path.abspath(filepath)

    total_size = _probe_content_length(url)

    # --- 分支 1：已知总大小 → 并发分块下载 ---
    if total_size and total_size > 0:
        print(f"[download_image INFO] 开始并发下载 ({num_workers}线程, "
              f"分块 {chunk_size_mb}MB, 总大小 {total_size/1024/1024:.2f}MB): "
              f"{os.path.basename(filepath)}")

        chunk_bytes = chunk_size_mb * 1024 * 1024
        ranges: List[tuple[int, int]] = []
        start = 0
        while start < total_size:
            end = min(start + chunk_bytes - 1, total_size - 1)
            ranges.append((start, end))
            start = end + 1

        # 每个分块写入独立的 .part_{idx} 文件，避免多线程 seek 冲突
        part_prefix = filepath + ".tmp"
        part_files: List[str] = [f"{part_prefix}_{i}" for i in range(len(ranges))]

        last_error: Optional[Exception] = None
        try:
            with ThreadPoolExecutor(max_workers=num_workers) as executor:
                futures = {
                    executor.submit(_download_range, url, part_files[i], s, e,
                                    300.0, max_retries): (i, s, e)
                    for i, (s, e) in enumerate(ranges)
                }
                done_count = 0
                for fut in as_completed(futures):
                    i, s, e = futures[fut]
                    done_count += 1
                    try:
                        n = fut.result()
                        print(f"[download_image INFO] 区间 {s}-{e} 完成 "
                              f"({n} bytes) [{done_count}/{len(ranges)}]")
                    except Exception as e:
                        last_error = e
                        print(f"[download_image ERROR] 区间 {s}-{e} 失败: {e}")
        except Exception as e:
            last_error = e

        if last_error is None:
            # 按顺序合并所有 part 文件到最终文件
            try:
                with open(filepath, "wb") as fout:
                    for pf in part_files:
                        if os.path.exists(pf):
                            with open(pf, "rb") as fin:
                                fout.write(fin.read())
                        else:
                            raise RuntimeError(f"缺少分块文件: {pf}")
                # 校验大小
                final_size = os.path.getsize(filepath)
                if final_size >= total_size - 100:
                    # 清理 part 文件
                    for pf in part_files:
                        try: os.remove(pf)
                        except OSError: pass
                    print(f"[download_image OK] {filepath} ({final_size} bytes)")
                    return os.path.abspath(filepath)
                else:
                    print(f"[download_image WARN] 合并后大小不匹配: "
                          f"{final_size}/{total_size}，回退到单线程")
            except Exception as e:
                print(f"[download_image WARN] 分块合并失败: {e}，回退到单线程")
        else:
            print(f"[download_image WARN] 并发下载失败: {last_error}，回退到单线程")

        # 清理残留
        for pf in part_files:
            try: os.remove(pf)
            except OSError: pass
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except OSError:
            pass

    # --- 分支 2：未知大小 / 服务器不支持 Range → 单线程流式下载（仍带重试）---
    print(f"[download_image INFO] 单线程流式下载: {os.path.basename(filepath)}")
    import httpx

    last_error: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        try:
            with httpx.Client(timeout=300.0, follow_redirects=True) as client:
                with client.stream("GET", url) as resp:
                    if resp.status_code not in (200, 206):
                        resp.raise_for_status()
                    total = 0
                    with open(temp_filepath, "wb") as f:
                        for chunk in resp.iter_bytes(chunk_size=65536):
                            if chunk:
                                f.write(chunk)
                                total += len(chunk)

            if total > 1000:
                os.replace(temp_filepath, filepath)
                print(f"[download_image OK] {filepath} ({total} bytes)")
                return os.path.abspath(filepath)
            print(f"[download_image WARN] 下载文件太小 ({total} bytes)，重试...")
            if os.path.exists(temp_filepath):
                os.remove(temp_filepath)
        except Exception as e:
            last_error = e
            print(f"[download_image WARN] 第{attempt}次尝试失败: {e}")
            try:
                if os.path.exists(temp_filepath):
                    os.remove(temp_filepath)
            except OSError:
                pass
            if attempt < max_retries:
                time.sleep(min(2 * attempt, 10))

    if last_error is not None:
        raise last_error
    raise RuntimeError(f"下载失败（已重试{max_retries}次）")


# ---------------------------------------------------------------------------
# AgnesImageClient
# ---------------------------------------------------------------------------

class AgnesImageClient:
    """Agnes AI 图像生成客户端。

    基于 openai SDK 兼容协议实现。提供文生图和图生图两种工作流。
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        self.api_key = api_key or _cfg.AGNES_API_KEY
        self.base_url = base_url or _cfg.AGNES_BASE_URL

        # 延迟导入 openai，避免未安装依赖时 import 整个包就失败
        try:
            import httpx
            from openai import OpenAI
        except ImportError as e:
            raise ImportError(
                "需要安装 openai 和 httpx: pip install openai httpx"
            ) from e

        self._http_client = httpx.Client(trust_env=False, proxy=None, timeout=120.0)
        self._client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            http_client=self._http_client,
        )

    def text_to_image(
        self,
        prompt: str,
        size: str = "1024x1024",
        n: int = 1,
        model: str = _cfg.MODEL_IMAGE_21_FLASH,
    ) -> Dict[str, Any]:
        """文生图：根据文本提示生成图像。

        Args:
            prompt: 图像描述文本，越详细越好。
            size: 输出图像尺寸，如 "1024x1024"、"1024x768"、"768x1024"
            n: 生成图像数量
            model: 模型名称，默认 agnes-image-2.1-flash

        Returns:
            {"created": <timestamp>, "data": [{"url": ...}, ...]}
        """
        response = self._client.images.generate(
            model=model,
            prompt=prompt,
            size=size,
            n=n,
        )
        return {
            "created": response.created,
            "data": [{"url": item.url} for item in response.data],
        }

    def image_to_image(
        self,
        prompt: str,
        image_urls: List[str],
        size: str = "1024x768",
        model: str = _cfg.MODEL_IMAGE_20_FLASH,
        seed: Optional[int] = None,
    ) -> Dict[str, Any]:
        """图生图：根据参考图像 + 文本提示生成新图像。

        Args:
            prompt: 描述想要的变化。
            image_urls: 参考图像列表，支持 URL 或本地文件路径
            size: 输出图像尺寸
            model: 图生图推荐使用 agnes-image-2.0-flash
            seed: 随机种子，固定值可复现结果

        Returns:
            {"created": <timestamp>, "data": [{"url": ...}, ...]}
        """
        if not image_urls:
            raise ValueError("image_urls 参数必须至少提供一个图像（URL 或本地文件路径）")

        processed_images = _prepare_image_inputs(image_urls)

        extra_body: Dict[str, Any] = {
            "tags": ["img2img"],
            "image": processed_images,
        }

        kwargs: Dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "size": size,
            "extra_body": extra_body,
        }
        if seed is not None:
            kwargs["seed"] = seed

        response = self._client.images.generate(**kwargs)
        return {
            "created": response.created,
            "data": [{"url": item.url} for item in response.data],
        }

    def download_images(
        self,
        result: Dict[str, Any],
        output_dir: str = "output",
        max_workers: int = 4,
    ) -> List[str]:
        """将响应中所有图像**并行**下载到本地，返回本地文件路径列表。

        每个图像内部仍会使用 `download_image` 的并发分块 + 断点续传能力；
        外层 `max_workers` 控制多图并行度。下载失败不会触发重新提交生成，
        只会在下载阶段重试。
        """
        items = result.get("data", [])
        if not items:
            return []
        if len(items) == 1:
            return [download_image(items[0]["url"], output_dir=output_dir)]

        saved_paths: List[str] = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(download_image, item["url"], output_dir):
                    i for i, item in enumerate(items)
            }
            results = [None] * len(items)
            for fut in as_completed(futures):
                idx = futures[fut]
                try:
                    results[idx] = fut.result()
                except Exception as e:
                    results[idx] = e
                    print(f"[download_images WARN] 第{idx}张图下载失败: {e}")

        # 按原始顺序收集结果，失败的跳过
        for r in results:
            if isinstance(r, str):
                saved_paths.append(r)

        return saved_paths

    def close(self) -> None:
        """关闭 HTTP 连接。"""
        try:
            self._http_client.close()
        except Exception:
            pass

    def __enter__(self) -> "AgnesImageClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


def create_client(
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
) -> AgnesImageClient:
    """便捷创建 AgnesImageClient 实例。"""
    return AgnesImageClient(api_key=api_key, base_url=base_url)
