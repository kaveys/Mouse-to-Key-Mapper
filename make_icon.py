# -*- coding: utf-8 -*-
"""
生成应用图标 icon.ico（蓝底圆角方块 + "MK" 字样）。

这是软件图标的唯一来源：
  - PyInstaller 用它作为 exe 文件图标 (--icon=icon.ico)
  - 运行时窗口标题栏/任务栏用 iconbitmap 加载它
  - 运行时系统托盘用 PIL.Image.open 加载它
三者因此保持完全一致。

清晰度：先在 4 倍超采样画布上绘制母图，再用 LANCZOS 高质量滤波
降采样到每个目标尺寸，避免小尺寸下的锯齿与模糊，文字与圆角更锐利。

用法：
  python make_icon.py
"""

from PIL import Image, ImageDraw, ImageFont

# 主题色（与界面一致）
BG_COLOR = (40, 120, 200)       # 蓝色底
FG_COLOR = (255, 255, 255)      # 白色字
TEXT = 'MK'

# 超采样倍数：母图 = 目标尺寸 × 此值，越大越清晰（代价是内存/耗时）
SUPER = 4
MASTER = 256                    # 逻辑母图尺寸（实际绘制 = 256 × 4 = 1024）


def _load_font(size_px):
    """尽量用系统 Arial，失败则回退默认位图字体。"""
    for name in ('arial.ttf', 'arialbd.ttf', 'segoeuib.ttf', 'segoeui.ttf'):
        try:
            return ImageFont.truetype(name, size_px)
        except Exception:
            continue
    return ImageFont.load_default()


def render_master(logical=MASTER, super_sample=SUPER):
    """在超大画布上绘制，返回高分辨率 RGBA 母图。"""
    size = logical * super_sample
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    margin = max(2, size // 16)
    x1, y1 = margin, margin
    x2, y2 = size - margin, size - margin
    # 圆角底
    try:
        d.rounded_rectangle([x1, y1, x2, y2],
                            radius=max(4, size // 5),
                            fill=BG_COLOR)
    except Exception:
        d.rectangle([x1, y1, x2, y2], fill=BG_COLOR)
    # 文字（在超大画布上绘制，降采样后边缘更平滑）
    font = _load_font(int(size * 0.5))
    try:
        bbox = d.textbbox((0, 0), TEXT, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        d.text(((size - tw) / 2, (size - th) / 2 - bbox[1]),
               TEXT, fill=FG_COLOR, font=font)
    except Exception:
        d.text((size // 4, size // 4), TEXT, fill=FG_COLOR, font=font)
    return img


def save_icon(path='icon.ico'):
    # 多尺寸，适配文件/窗口/托盘各种显示场景
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
             (128, 128), (256, 256)]
    master = render_master()  # 1024×1024 高分辨率母图
    # PIL 会从 1024 母图高质量降采样到每个目标尺寸（BICUBIC）
    master.save(path, format='ICO', sizes=sizes)
    print(f'已生成图标: {path}（母图 {master.size[0]}px，{len(sizes)} 种尺寸）')


if __name__ == '__main__':
    save_icon('icon.ico')
