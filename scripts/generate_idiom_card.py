"""成语故事卡片生成脚本。

在 idiom.png 底图上贴写成语故事内容。

布局（参考图从上到下的百分比位置）：
    1. 顶部标题 "家长必讲的成语故事"         y=3-10%
    2. 拼音行                                  y=11-14%
    3. 成语大字（4个字）                       y=15-24%
    4. 插图区域                                y=25-48%（底图已有，不贴文字）
    5. 1.简单解释                              y=50-62%
    6. 2.故事讲述                              y=63-80%
    7. 3.家长提示                              y=81-95%
    8. 系列编号                                y=96-98%

使用方法：
    # 1) 直接传入 JSON 数据
    python scripts/generate_idiom_card.py --data '{...}' --output result.png

    # 2) 从 JSON 文件读取
    python scripts/generate_idiom_card.py --input data/idiom.json --output result.png

    # 3) 使用默认测试数据（东窗事发）
    python scripts/generate_idiom_card.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# 添加 remoteapi 搜索路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    from remoteapi import text_to_image
    REMOTEAPI_AVAILABLE = True
except Exception as e:
    REMOTEAPI_AVAILABLE = False
    _remoteapi_error = str(e)

# ---------------------------------------------------------------------------
# 项目路径
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
IDIOM_BG = PROJECT_ROOT / "styles" / "assets" / "idiom.png"
FONT_DIR = PROJECT_ROOT / "fonts"
FONT_ZH_BOLD = FONT_DIR / "CMSFont-Bold.TTF"
FONT_ZH_REG = FONT_DIR / "CMSFont-Bold.TTF"
FONT_MSYH_BOLD = FONT_DIR / "chinese" / "msyh" / "Bold.ttf"
FONT_MSYH_REG = FONT_DIR / "chinese" / "msyh" / "Regular.ttf"

# ---------------------------------------------------------------------------
# 颜色（从参考图提取）
# ---------------------------------------------------------------------------
COLOR_TITLE_BROWN = (89, 47, 20)       # 深棕色标题
COLOR_SECTION_BG = (160, 82, 45)       # 标签背景棕色
COLOR_TEXT = (60, 35, 15)              # 正文深棕色
COLOR_PINYIN = (89, 47, 20)            # 拼音棕色

# ---------------------------------------------------------------------------
# 默认测试数据
# ---------------------------------------------------------------------------
DEFAULT_DATA = {
    "idiom": "东窗事发",
    "pinyin": "dōng chuāng shì fā",
    "explanation": "在东窗下密谋的事败露了。后多用来形容秘密计划或坏事被发现、暴露。就像你偷偷吃零食，却被妈妈发现了。",
    "story": "南宋时期，金国大举进攻中原，岳飞率领岳家军顽强抵抗，连连取胜。可是宰相秦桧主张议和，想除掉岳飞。一天，秦桧坐在东窗下，正为无法除掉岳飞发愁。夫人王氏走进来，想了想说：我听说岳飞手下的王贵，在一次战斗中胆小怕死，岳飞要杀他，后来免了他一死。他肯定怀恨在心，你何不让他告发呢？秦桧派人找到王贵，要他诬告岳飞谋反。王贵不愿意，秦桧就严刑拷打他，还威胁杀他全家。王贵只好屈从。秦桧终于找到罪名把岳飞杀了。后来，秦桧也病死了。他死后七日，王氏请道士超度他的亡灵。道士装模作样做了一会儿法事，然后对王氏说：我看见秦桧正在地狱里受苦。秦大人对我说，麻烦你告诉夫人，当初在东窗下密谋陷害岳飞的事情败露了。",
    "tip": "问孩子：你觉得秦桧做的对吗？为什么？教育孩子：做坏事终究会被发现，就像东窗事发一样。也要告诉孩子：要做一个正直、善良的人。",
    "series_number": "E01/046",
}


# ---------------------------------------------------------------------------
# 插图工具
# ---------------------------------------------------------------------------

def generate_illustration(idiom: str, explanation: str,
                          output_dir: str | Path) -> str | None:
    """调用 remoteapi 文生图生成成语插图（无文字版）。

    策略：
    - 全英文 prompt 描述古代场景，不出现成语词汇，避免 AI 画书法文字
    - 简单启发式检测图片中是否有文字像素，检测到则自动重试
    - 最多尝试 max_tries 次，取最"干净"的一张
    """
    if not REMOTEAPI_AVAILABLE:
        print(f"[WARN] remoteapi 不可用: {_remoteapi_error}，跳过插图生成")
        return None

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_path = output_dir / f"{idiom}_illustration.png"

    if cache_path.exists() and cache_path.stat().st_size > 0:
        print(f"[INFO] 复用已有插图: {cache_path}")
        return str(cache_path)

    # 用中性的艺术风格描述，不触发"书法/中国风文字"联想
    # 特意不写 "Chinese"，避免 AI 联想到汉字/书法
    prompt = (
        "Watercolor and ink illustration, ancient historical scene. "
        f"Mood and story: {explanation[:60]}. "
        "Traditional costume, natural architecture, classical composition, "
        "warm sepia beige parchment tones, aged paper texture background, "
        "soft watercolor brushwork, delicate details, horizontal wide composition. "
        "CRITICAL - DO NOT DRAW: absolutely no text, no letters, no writing, "
        "no calligraphy, no symbols, no marks, no stamps, no seals, no signature, "
        "no borders, no frame, no decorative patterns."
    )

    print(f"[INFO] 正在生成成语插图: {idiom}")
    print(f"       提示词片段: {prompt[:70]}...")

    max_tries = 2
    best_path: str | None = None
    best_score = float("inf")  # 文字嫌疑分数，越小越干净

    for attempt in range(1, max_tries + 1):
        try:
            result = text_to_image(
                prompt=prompt,
                size="1024x512",
                n=1,
                model="agnes-image-2.1-flash",
                output_dir=str(output_dir),
            )

            if "local_paths" not in result or not result["local_paths"]:
                if "data" in result and result["data"]:
                    import httpx
                    url = result["data"][0]["url"]
                    resp = httpx.get(url, timeout=120.0, follow_redirects=True)
                    if resp.status_code == 200 and len(resp.content) > 1000:
                        tmp_path = output_dir / f"_tmp_{idiom}_{attempt}.png"
                        tmp_path.write_bytes(resp.content)
                        result.setdefault("local_paths", []).append(str(tmp_path))
                    else:
                        continue
                else:
                    continue

            raw_path = Path(result["local_paths"][0])
            if not raw_path.exists() or raw_path.stat().st_size < 1000:
                continue

            # 文字启发式检测：分数越低越干净
            text_score = _detect_text_in_image(str(raw_path))
            print(f"       第{attempt}次: 文字嫌疑分 = {text_score:.1f}")

            if text_score < best_score:
                best_score = text_score
                best_path = str(raw_path)

            # 分数够低，直接用这张
            if text_score < 30.0:
                break

        except Exception as e:
            print(f"       第{attempt}次尝试失败: {e}")
            continue

    if best_path is not None:
        cache_path.write_bytes(Path(best_path).read_bytes())
        print(f"[OK] 插图已保存: {cache_path}（文字嫌疑分 {best_score:.1f}）")
        return str(cache_path)

    print(f"[WARN] 未能生成干净的插图")
    return None


def _detect_text_in_image(img_path: str) -> float:
    """启发式文字检测：返回"文字嫌疑分数"，越高越可能有文字。

    核心检测逻辑：
    1. 把图片切成很小的网格（16x12）
    2. 找出"浅色背景上有密集深色笔画"的网格
    3. 这样的网格数量越多，分数越高

    正常画作：深色区域较大且分布均匀（人物/建筑）
    有文字的画：小区域内出现密集的笔画状像素
    """
    try:
        import numpy as np
        from PIL import Image

        img = Image.open(img_path).convert("L")
        img = img.resize((512, 384))
        arr = np.array(img, dtype=np.int16)

        h, w = arr.shape

        # 切成 16x12 的小网格 = 192 个网格
        rows, cols = 16, 12
        ch, cw = h // rows, w // cols

        # 全局背景亮度
        bg_bright = float(np.percentile(arr, 60))

        suspicious_cells = 0

        for r in range(rows):
            for c in range(cols):
                cell = arr[r * ch:(r + 1) * ch, c * cw:(c + 1) * cw]

                # 该网格比背景暗很多（有内容）
                cell_avg = float(cell.mean())
                if bg_bright - cell_avg < 25:
                    continue  # 这个网格就是背景，跳过

                # 该网格有"笔画状"的深色像素：
                # 深色像素占 10%-50% 之间（笔画的特征）
                dark_ratio = float(np.sum(cell < 100)) / cell.size
                if 0.10 < dark_ratio < 0.55:
                    # 同时该网格的边缘密度也较高
                    v_diff = np.abs(cell[:, 2:] - cell[:, :-2])
                    edge_density = float(np.sum(v_diff > 40)) / v_diff.size
                    if edge_density > 0.04:
                        suspicious_cells += 1

        # 分数 = 可疑网格数 / 总格数
        score = suspicious_cells / (rows * cols) * 100
        return round(score, 1)

    except Exception:
        return 0.0


def prepare_illustration_for_composite(src_path: str | Path,
                                       target_width: int,
                                       target_height: int,
                                       bg_color: tuple = (245, 235, 210)) -> tuple[Image.Image, Image.Image]:
    """把生成的插图处理成不规则圆角矩形，返回 (img_rgb, mask) 供调用方粘贴。

    处理流程：
    1. cover 模式裁切填满目标区域
    2. 色调向米黄纸色靠拢，提升整体一致性
    3. 4 个角各取 15%-20% 之间的**随机**半径 → 不规则圆角矩形
    4. 圆角区域完全透明，角的 10% 过渡带从 90% 透明渐变到完全不透明

    返回:
        (img_rgb, mask) —— 调用方应执行: canvas.paste(img_rgb, (x, y), mask)
        这样圆角的透明区域会显示底图的真实纸色/纹理/装饰元素，而不是纯色块
    """
    import random
    from PIL import ImageFilter

    img = Image.open(src_path).convert("RGB")
    iw, ih = img.size

    # ---- 1. cover 模式裁切填满 ----
    scale = max(target_width / iw, target_height / ih)
    new_w, new_h = int(iw * scale), int(ih * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_width) // 2
    top = (new_h - target_height) // 2
    img = img.crop((left, top, left + target_width, top + target_height))

    # ---- 2. 色调向纸色靠拢 ----
    try:
        import numpy as np
        arr = np.array(img, dtype=np.float32)
        bg_arr = np.array(bg_color, dtype=np.float32).reshape(1, 1, 3)
        arr = arr * 0.82 + bg_arr * 0.18
        arr = np.clip(arr, 0, 255).astype(np.uint8)
        img = Image.fromarray(arr)
    except ImportError:
        pass

    # ---- 3. 4 个角取随机半径 (30%-45% 之间) ----
    #    半径基准 = 短边 * 随机比例
    min_side = min(target_width, target_height)
    r_tl = int(min_side * random.uniform(0.30, 0.45))  # 左上
    r_tr = int(min_side * random.uniform(0.30, 0.45))  # 右上
    r_bl = int(min_side * random.uniform(0.30, 0.45))  # 左下
    r_br = int(min_side * random.uniform(0.30, 0.45))  # 右下

    # 过渡带宽：每个角的 fade_dist = 该角半径 * 25%-35%
    fade_dists = [
        int(r_tl * random.uniform(0.25, 0.35)),
        int(r_tr * random.uniform(0.25, 0.35)),
        int(r_bl * random.uniform(0.25, 0.35)),
        int(r_br * random.uniform(0.25, 0.35)),
    ]

    # ---- 4. 用 numpy 构造不规则圆角矩形的 alpha 遮罩 ----
    #    正确逻辑：
    #    1. 初始：全不透明
    #    2. 对每个角 bbox 范围内：
    #       - 在圆角曲线内 (dist < radius): 完全透明 (alpha=0)
    #       - 过渡带 (0 <= signed < fade_dist): alpha 从 0 线性变到 1.0
    #       - 其余: 完全不透明 (alpha=1.0)
    try:
        import numpy as np

        mw, mh = target_width, target_height

        yy = np.linspace(0, mh - 1, mh)[:, np.newaxis]
        xx = np.linspace(0, mw - 1, mw)[np.newaxis, :]

        # 初始：全不透明 (alpha=1.0)
        alpha = np.ones((mh, mw), dtype=np.float32)

        fade_dist_global = max(min(int(target_width * 0.10), int(target_height * 0.10)), 8)

        # 4 个角分别处理（每个角有独立的半径和过渡带）
        corners = [
            (r_tl,       r_tl,       r_tl, xx < r_tl,             yy < r_tl,             fade_dists[0]),
            (mw - r_tr,  r_tr,       r_tr, xx > mw - r_tr,        yy < r_tr,             fade_dists[1]),
            (r_bl,       mh - r_bl,  r_bl, xx < r_bl,             yy > mh - r_bl,         fade_dists[2]),
            (mw - r_br,  mh - r_br,  r_br, xx > mw - r_br,        yy > mh - r_br,         fade_dists[3]),
        ]

        for cx, cy, radius, x_mask, y_mask, fade_dist in corners:
            in_bbox = x_mask & y_mask
            if not np.any(in_bbox):
                continue

            dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
            signed = dist - radius  # <0: 圆内(靠近圆心=保留内容), >0: 圆外(靠近角尖=切掉透明)

            fade_dist = max(fade_dist, 8)  # 确保最小值

            # 1) signed > fade_dist: 远离曲线、靠近角尖 → 完全透明
            fully_transparent = in_bbox & (signed > fade_dist)
            alpha[fully_transparent] = 0.0

            # 2) 0 < signed <= fade_dist: 过渡带，从圆角曲线向角尖方向渐透明
            in_transition = in_bbox & (signed > 0) & (signed <= fade_dist)
            t = np.clip(signed[in_transition] / fade_dist, 0.0, 1.0)
            alpha[in_transition] = 1.0 - t  # t=0→1.0, t=1→0.0

            # 3) signed <= 0: 在圆角曲线内 → 完全不透明
            #    无需修改

        alpha = (alpha * 255).astype(np.uint8)
        mask = Image.fromarray(alpha)

        # 轻微模糊，让过渡更自然
        mask = mask.filter(ImageFilter.GaussianBlur(radius=2))

    except ImportError:
        # 降级方案
        mask = Image.new("L", (target_width, target_height), 255)
        avg_r = (r_tl + r_tr + r_bl + r_br) // 4
        mask_draw = ImageDraw.Draw(mask)
        # 先清空四角（用黑色=透明画圆角矩形的反向）
        mask_draw.rectangle([0, 0, target_width, target_height], fill=255)
        # 然后画一个内部圆角区域的填充...
        # 简化：用反色方案：画一个黑色圆角矩形做"切掉角"的效果
        mask = Image.new("L", (target_width, target_height), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle(
            [0, 0, target_width, target_height],
            radius=avg_r,
            fill=255,
        )
        mask = mask.filter(ImageFilter.GaussianBlur(radius=8))

    # ---- 5. 返回处理好的插图 + mask，让调用方自己贴到底图上 ----
    #    关键：不在这里填充背景色！让底图的真实纹理"透过来"
    #    这样圆角的透明区域会正确显示底图的纸色/纹理/装饰元素
    return img, mask


# ---------------------------------------------------------------------------
# 字体工具
# ---------------------------------------------------------------------------

def load_font(size: int, bold: bool = False, family: str = "cms") -> ImageFont.FreeTypeFont:
    """加载中文字体。

    Args:
        size: 字号
        bold: 是否加粗
        family: 字体家族，"cms"（招商证券体，默认）或 "msyh"（微软雅黑）
    """
    if family == "msyh":
        font_path = FONT_MSYH_BOLD if bold else FONT_MSYH_REG
    else:
        font_path = FONT_ZH_BOLD if bold else FONT_ZH_REG
    try:
        return ImageFont.truetype(str(font_path), size)
    except Exception as e:
        print(f"[WARN] 字体加载失败 {font_path}: {e}, 尝试系统字体")
        try:
            return ImageFont.truetype("msyh.ttc", size)
        except Exception:
            return ImageFont.load_default()


def measure_text(font: ImageFont.FreeTypeFont, text: str) -> tuple[int, int]:
    """测量文字尺寸。"""
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """按像素宽度对中文文本换行。

    文本中显式的 \\n 会作为分段标记：分段后保留一个空行在 lines 中（用空字符串占位），
    方便绘制时在段落之间加额外间距。
    """
    lines: list[str] = []
    paragraphs = text.split("\n")
    for p_idx, paragraph in enumerate(paragraphs):
        current_line = ""
        for ch in paragraph:
            test_line = current_line + ch
            w, _ = measure_text(font, test_line)
            if w > max_width and current_line:
                lines.append(current_line)
                current_line = ch
            else:
                current_line = test_line
        if current_line or paragraph == "":
            lines.append(current_line)
        # 段落之间加一个空行标记（最后一段不加）
        if p_idx < len(paragraphs) - 1:
            lines.append("")
    return lines


def draw_text_centered(draw: ImageDraw.ImageDraw, y: int, text: str,
                       font: ImageFont.FreeTypeFont, color: tuple[int, int, int],
                       image_width: int) -> int:
    """在指定 y 位置水平居中绘制文字，返回占用的高度。"""
    w, h = measure_text(font, text)
    x = (image_width - w) // 2
    draw.text((x, y), text, font=font, fill=color)
    return h


def draw_section_label(draw: ImageDraw.ImageDraw, y: int, label: str,
                       font: ImageFont.FreeTypeFont, image_width: int,
                       left_margin: int) -> int:
    """绘制棕色圆角标签（如 "1.简单解释"）。

    Returns:
        标签占用的总高度（包括下方间距）。
    """
    text_w, text_h = measure_text(font, label)
    padding_x = 24
    padding_y = 14

    x1 = left_margin
    y1 = y
    x2 = left_margin + text_w + padding_x * 2
    y2 = y + text_h + padding_y * 2

    # 圆角矩形
    radius = 18
    draw.rounded_rectangle([x1, y1, x2, y2], radius=radius,
                           fill=COLOR_SECTION_BG, outline=None)

    # 文字：用 textbbox 获取实际渲染尺寸，精准垂直居中
    bbox = draw.textbbox((0, 0), label, font=font)
    actual_top = bbox[1]
    actual_h = bbox[3] - bbox[1]
    block_h = y2 - y1
    text_y = y1 + (block_h - actual_h) // 2 - actual_top
    text_x = x1 + padding_x
    draw.text((text_x, text_y), label, font=font, fill=(255, 255, 255))

    return (y2 - y1) + 20  # 下方间距


def draw_paragraph(draw: ImageDraw.ImageDraw, y: int, text: str,
                   font: ImageFont.FreeTypeFont, color: tuple[int, int, int],
                   left_margin: int, right_margin: int,
                   image_width: int, line_spacing_ratio: float = 1.5) -> int:
    """在指定位置绘制多行段落（自动换行 + 段落之间加额外间距）。

    文本中的 \\n 会被视为分段标记，段落之间会比正常行间距多留一点空白，
    增强可读性。

    Returns:
        段落占用的总高度（像素）。
    """
    max_width = image_width - left_margin - right_margin
    lines = wrap_text(text, font, max_width)

    line_h = font.size
    normal_spacing = int(line_h * line_spacing_ratio)
    para_gap = int(line_h * 0.5)  # 段落之间额外加半行空白

    current_y = y
    for line in lines:
        if line == "":
            # 空行 = 段落分隔，跳过本行正常间距，只留一个小间距
            current_y += para_gap
        else:
            draw.text((left_margin, current_y), line, font=font, fill=color)
            current_y += normal_spacing

    total_h = current_y - y
    return total_h


# ---------------------------------------------------------------------------
# 主生成函数
# ---------------------------------------------------------------------------

def generate_idiom_card(data: dict, output_path: str | Path,
                        bg_path: str | Path = IDIOM_BG,
                        gen_illustration: bool = False,
                        illustration_dir: str | Path | None = None) -> str:
    """在底图上贴写成语故事内容，可选生成 AI 插图。

    Args:
        data: 成语数据字典（idiom, pinyin, explanation, story, tip, series_number）
        output_path: 输出图片路径
        bg_path: 底图路径
        gen_illustration: 是否调用 remoteapi 生成 AI 插图
        illustration_dir: 插图缓存目录（默认输出目录下的 illustrations 文件夹）

    Returns:
        实际输出路径
    """
    idiom = data["idiom"]
    pinyin = data.get("pinyin", "")
    explanation = data.get("explanation", "")
    story = data.get("story", "")
    tip = data.get("tip", "")
    series_number = data.get("series_number", "")

    # 打开底图
    img = Image.open(bg_path).convert("RGB")
    W, H = img.size
    draw = ImageDraw.Draw(img)

    # 各区域百分比位置
    top_title_y = int(H * 0.045)          # "家长必讲的成语故事"
    pinyin_y = int(H * 0.105)              # 拼音行
    idiom_y = int(H * 0.125)               # 成语大字
    # section1_label_y 会根据插图的实际高度动态调整

    # 左右边距
    left_margin = int(W * 0.08)
    right_margin = int(W * 0.06)

    # ---------------------------------------------------------------
    # 1. 顶部标题 "家长必讲的成语故事" + 右上角系列编号
    # ---------------------------------------------------------------
    font_title = load_font(int(W * 0.060), bold=True)
    draw_text_centered(draw, top_title_y, "家长必讲的成语故事",
                       font_title, COLOR_TITLE_BROWN, W)

    if series_number:
        font_series = load_font(int(W * 0.024), bold=True, family="msyh")
        series_text = f"{series_number}"
        w_series, h_series = measure_text(font_series, series_text)
        series_padding_x = 20
        series_padding_y = 8
        series_radius = 14
        series_box_x1 = W - right_margin - w_series - series_padding_x * 2
        series_box_x2 = W - right_margin
        series_box_y1 = top_title_y - series_padding_y
        series_box_y2 = top_title_y + h_series + series_padding_y
        draw.rounded_rectangle(
            [series_box_x1, series_box_y1, series_box_x2, series_box_y2],
            radius=series_radius,
            fill=COLOR_SECTION_BG, outline=None
        )
        series_text_x = series_box_x1 + series_padding_x
        bbox = draw.textbbox((0, 0), series_text, font=font_series)
        actual_top = bbox[1]
        actual_h = bbox[3] - bbox[1]
        block_h = series_box_y2 - series_box_y1
        series_text_y = series_box_y1 + (block_h - actual_h) // 2 - actual_top
        draw.text((series_text_x, series_text_y), series_text,
                  font=font_series, fill=(255, 255, 255))

    # ---------------------------------------------------------------
    # 先计算田字格位置（用于拼音和成语的对齐，兼容4/5/6字）
    # ---------------------------------------------------------------
    chars = list(idiom)
    n_chars = len(chars)

    # 动态分配田字格宽度：字越多，每个字越小
    if n_chars <= 4:
        cell_width = int(W * 0.16)
        idiom_size = int(W * 0.12)
        pinyin_size = int(W * 0.034)
    elif n_chars == 5:
        cell_width = int(W * 0.135)
        idiom_size = int(W * 0.10)
        pinyin_size = int(W * 0.030)
    else:
        cell_width = int(W * 0.12)
        idiom_size = int(W * 0.088)
        pinyin_size = int(W * 0.026)

    total_width = cell_width * n_chars
    start_x = (W - total_width) // 2

    # 解析拼音：按空格拆分
    pinyin_parts = pinyin.split()
    while len(pinyin_parts) < n_chars:
        pinyin_parts.append("")

    # ---------------------------------------------------------------
    # 2. 拼音行（每个字的拼音对齐到对应田字格的正上方）
    # ---------------------------------------------------------------
    font_pinyin = load_font(pinyin_size, bold=True)

    for i, py in enumerate(pinyin_parts[:n_chars]):
        if not py:
            continue
        cell_center_x = start_x + i * cell_width + cell_width // 2
        pw, _ = measure_text(font_pinyin, py)
        py_x = cell_center_x - pw // 2
        draw.text((py_x, pinyin_y), py,
                  font=font_pinyin, fill=COLOR_PINYIN)

    # ---------------------------------------------------------------
    # 3. 成语大字（支持4-6字，根据 n_chars 动态生成田字格）
    # ---------------------------------------------------------------
    font_idiom = load_font(idiom_size, bold=True)

    for i, ch in enumerate(chars):
        cell_x = start_x + i * cell_width
        cell_y = idiom_y

        cell_bg = (245, 235, 210)
        padding = 8
        draw.rounded_rectangle(
            [cell_x + padding, cell_y + padding,
             cell_x + cell_width - padding, cell_y + cell_width - padding],
            radius=10,
            fill=cell_bg,
            outline=(120, 70, 30),
            width=3,
        )

        cx_center = cell_x + cell_width // 2
        cy_center = cell_y + cell_width // 2
        cross_color = (180, 140, 100)
        draw.line(
            [cx_center, cell_y + padding, cx_center, cell_y + cell_width - padding],
            fill=cross_color, width=2,
        )
        draw.line(
            [cell_x + padding, cy_center, cell_x + cell_width - padding, cy_center],
            fill=cross_color, width=2,
        )

        # 文字（水平居中，向上偏移约10%以达到视觉居中）
        w, h = measure_text(font_idiom, ch)
        text_x = cell_x + (cell_width - w) // 2
        text_y = cell_y + (cell_width - h) // 2 - int(h * 0.10)
        draw.text((text_x, text_y), ch, font=font_idiom, fill=COLOR_TITLE_BROWN)

    # ---------------------------------------------------------------
    # 4. 插图（田字格下方，简单解释上方）
    #     插图区域占满文字区域宽度，高度约占卡片总高度的 32%
    # ---------------------------------------------------------------
    # 插图区域保持 2:1 比例（和 API 生成的 1024x512 一致）
    cells_bottom = idiom_y + cell_width
    illus_width = W - left_margin * 2 - int(W * 0.04)
    illus_height = illus_width // 2
    illus_y_start = cells_bottom + int(H * 0.020)
    illus_y_end = illus_y_start + illus_height

    illus_img = None
    if gen_illustration:
        illus_dir = Path(illustration_dir) if illustration_dir \
            else (Path(output_path).parent / "illustrations")
        illus_path = generate_illustration(idiom, explanation, illus_dir)
        if illus_path:
            illus_img, illus_mask = prepare_illustration_for_composite(
                illus_path, illus_width, illus_height
            )

    # 绘制插图区域：有插图直接贴上（无边框，边缘已融合），
    # 无插图时画一个精致的占位框
    illus_x = (W - illus_width) // 2 + int(W * 0.05)  # 从中心向右偏移10%

    if illus_img is not None:
        # 有插图：用 mask 贴上（透明角区域显示底图的真实纹理
        img.paste(illus_img, (illus_x, illus_y_start), illus_mask)
    else:
        # 无插图：绘制一个柔和的装饰虚线框（不是硬方框）
        # 用淡棕色绘制柔和的背景 + 两条淡色装饰线
        try:
            # 极淡的米色背景（比卡片底色深一点，让区域有存在感
            draw.rounded_rectangle(
                [illus_x, illus_y_start, illus_x + illus_width, illus_y_start + illus_height],
                radius=8,
                fill=(246, 236, 212),
                outline=(180, 140, 100),
                width=2,
            )
        except Exception:
            draw.rectangle(
                [illus_x, illus_y_start, illus_x + illus_width, illus_y_start + illus_height],
                outline=(180, 140, 100),
                width=2,
            )
        hint_font = load_font(int(W * 0.020), bold=False)
        hint = f"{idiom} · 成语故事插图"
        hw, hh = measure_text(hint_font, hint)
        hint_x = illus_x + (illus_width - hw) // 2
        hint_y = illus_y_start + (illus_height - hh) // 2
        draw.text((hint_x, hint_y), hint, font=hint_font, fill=(120, 70, 30))

    # ---------------------------------------------------------------
    # 4. 自适应字号：根据剩余空间 & 文字量自动计算
    # ---------------------------------------------------------------
    section1_label_y = illus_y_end + int(H * 0.02)
    # 签名图片: 宽18%*W, 比例4:1 → 高≈4.5%*W; 再留1.5%边距
    sig_height_est = int(W * 0.18 / 4) + int(H * 0.015)
    reserved_bottom = sig_height_est
    available_h = H - section1_label_y - reserved_bottom

    # 先估算各段文字需要的高度（按指定字号）
    para_left = left_margin + int(W * 0.01)
    para_right = right_margin + int(W * 0.01)
    para_max_w = W - para_left - para_right

    sections = [
        ("简单解释", explanation),
        ("故事讲述", story),
        ("家长提示", tip),
    ]

    def estimate_total_height(label_size_px: int, body_size_px: int) -> int:
        """估算底部所有文字（标题+正文）一共需要的像素高度。"""
        lf = load_font(label_size_px, bold=True, family="msyh")
        bf = load_font(body_size_px, bold=False, family="msyh")
        normal_spacing = int(bf.size * 1.5)
        para_gap = int(bf.size * 0.5)
        total = 0
        for label, text in sections:
            _, th = measure_text(lf, label)
            label_block_h = th + 20 + 20
            total += label_block_h
            lines = wrap_text(text, bf, para_max_w)
            for line in lines:
                if line == "":
                    total += para_gap
                else:
                    total += normal_spacing
            total += int(H * 0.01)
        return total

    # 从一个较合理的字号开始试（上限 ~ W*0.028），放不下就缩小
    best_label_px = int(W * 0.038)
    best_body_px = int(W * 0.032)
    min_label_px = int(W * 0.018)
    min_body_px = int(W * 0.015)

    while best_label_px > min_label_px and best_body_px > min_body_px:
        needed = estimate_total_height(best_label_px, best_body_px)
        if needed <= available_h:
            break
        best_label_px -= 2
        best_body_px -= 2

    label_font = load_font(best_label_px, bold=True, family="msyh")
    body_font = load_font(best_body_px, bold=False, family="msyh")

    print(f"[INFO] 自适应字号: 标题 {best_label_px}px / 正文 {best_body_px}px "
          f"(可用高度 {available_h}px)")

    # ---------------------------------------------------------------
    # 5. 按顺序绘制：简单解释 → 故事讲述 → 家长提示
    # ---------------------------------------------------------------
    current_y = section1_label_y

    for i, (label, text) in enumerate(sections):
        label_h = draw_section_label(draw, current_y, label,
                                     label_font, W, left_margin)
        para_y = current_y + label_h
        para_h = draw_paragraph(draw, para_y, text, body_font, COLOR_TEXT,
                                para_left, para_right, W)
        current_y = para_y + para_h + int(H * 0.01)

    # ---------------------------------------------------------------
    # 6. 最下方居中放置签名（sig-light.png）
    # ---------------------------------------------------------------
    sig_path = PROJECT_ROOT / "styles" / "assets" / "sig-dark.png"
    if sig_path.exists():
        try:
            sig = Image.open(sig_path).convert("RGBA")
            sig_target_w = int(W * 0.18)
            sig_ratio = sig_target_w / sig.width
            sig_target_h = int(sig.height * sig_ratio)
            sig = sig.resize((sig_target_w, sig_target_h), Image.LANCZOS)
            sig_x = (W - sig.width) // 2
            sig_y = H - sig.height - int(H * 0.015)
            img.paste(sig, (sig_x, sig_y), sig)
        except Exception as e:
            print(f"[WARN] 签名加载失败: {e}")

    # 保存
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, quality=95)
    return str(output_path)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="成语故事卡片生成工具（在底图上贴写文字 + 可选 AI 插图）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--input", type=str, default=None,
                        help="JSON 输入文件路径")
    parser.add_argument("--data", type=str, default=None,
                        help="JSON 字符串数据（与 --input 二选一）")
    parser.add_argument("--output", type=str, default=None,
                        help="输出图片路径，默认 tests/output_idiom/{成语}.png")
    parser.add_argument("--bg", type=str, default=str(IDIOM_BG),
                        help="底图路径，默认 styles/assets/idiom.png")
    parser.add_argument("--gen-illustration", action="store_true",
                        help="调用 remoteapi 文生图生成成语场景插图")
    args = parser.parse_args()

    # 加载数据
    if args.data:
        try:
            data = json.loads(args.data)
        except json.JSONDecodeError as e:
            print(f"[ERROR] JSON 解析失败: {e}")
            return 1
    elif args.input:
        try:
            with open(args.input, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[ERROR] 读取输入文件失败: {e}")
            return 1
    else:
        print("[INFO] 使用默认测试数据：东窗事发")
        data = DEFAULT_DATA

    # 输出路径
    if args.output:
        output_path = args.output
    else:
        output_dir = PROJECT_ROOT / "tests" / "output_idiom"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{data['idiom']}.png"

    # 校验必需字段
    for field in ("idiom", "explanation", "story"):
        if field not in data:
            print(f"[ERROR] 缺少必需字段: {field}")
            return 1

    print(f"[INFO] 底图: {args.bg}")
    print(f"[INFO] 成语: {data['idiom']}")
    print(f"[INFO] 输出: {output_path}")
    print(f"[INFO] 生成插图: {'是（Agnes AI）' if args.gen_illustration else '否'}")
    print("[INFO] 正在生成...")

    try:
        result = generate_idiom_card(
            data,
            output_path,
            bg_path=args.bg,
            gen_illustration=args.gen_illustration,
        )
        print(f"[OK] 生成成功: {result}")
        return 0
    except Exception as e:
        print(f"[ERROR] 生成失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
