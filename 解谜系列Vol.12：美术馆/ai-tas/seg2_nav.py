#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Seg2 选关导航（Vol.12 美術館「やさしい」100 关）。

实测几何（limiter ON，256×384）：
  * 数字网格 10 列 × 5 行可见
      行中心 y = 278, 294, 310, 326, 342（行距 16）
      列中心 x = 19 + 24*col（col 0..9）
  * 右侧黑色三角箭头：▲ (236, 266)、▼ (236, 352)
      **每点一次滚 1 行 = 10 关**（实测首格 1 → 11 → 21 → 31 → ?）
  * 100 关 = 10 行；顶屏可见全局行 0..4（关 1..50），滚到底可见行 5..9（关 51..100）
  * 已解锁 = 白数字；未解锁 = 「?」（问号，白像素约 12）
  * 选中格会显示预览（盘面图 + SIZE），按 A（x 键）才真正进关
  * 光标 = 亮绿描边框，D-pad 可在可见 5 行内移动（D-pad 不翻页）

本模块提供：数字 OCR（读任意格关卡号）、翻页到指定行、点击关卡。
"""
import time

import numpy as np

import ds

ROW_Y = [278, 294, 310, 326, 342]
COL_X0, COL_DX = 19, 24
ARROW_UP = (236, 266)
ARROW_DOWN = (236, 352)
N_VIS_ROWS = 5
N_COLS = 10
TOTAL = 100
ROWS_TOTAL = (TOTAL + N_COLS - 1) // N_COLS     # 10

# ---------- 数字 OCR ----------
# 单字符模板（14×14 二值掩码，格子右半 / 单数字整格）
_TPL = {}
_HALF = 7


def _cell_mask(im, row, col):
    """格内数字笔画二值掩码。"""
    x = COL_X0 + COL_DX * col
    y = ROW_Y[row]
    reg = im[y - 7:y + 7, x - 7:x + 7, :]
    R, G, B = reg[:, :, 0], reg[:, :, 1], reg[:, :, 2]
    return (R > 190) & (G > 190) & (B > 190)


def _is_q(m):
    """问号「?」的笔画特征：像素少且左右不均。"""
    if m.sum() <= 3:
        return True
    cols = m.sum(axis=0)
    nz = np.nonzero(cols)[0]
    return bool(nz.size and (nz.max() - nz.min()) <= 8 and m.sum() < 16)


def build_ocr(im):
    """从「已知编号」的格子采集 10 个单字符模板。

    需在顶屏（首行=第 1 关）调用：第 0 行是 1..10，可拿到 1..9 及 "10" 的两半。
    统一在 **右半 14×7** 空间比对：
      一位数 → 取该格右半（数字偏右对齐，右半即字符本体）
      两位数左位 → 取左半再压到右半宽度不适用，故两位数分两半各读一次。
    """
    global _TPL
    _TPL = {}
    for col in range(N_COLS):
        num = col + 1
        m = _cell_mask(im, 0, col)
        if m.sum() <= 3:
            continue
        if num < 10:
            # 一位数：字符在格中央，两半都含部分笔画；
            # 取较"满"的一半作为模板，统一用 14×7
            left = m[:, :_HALF]
            right = m[:, _HALF:]
            _TPL[num] = right if right.sum() >= left.sum() else left
        else:
            # "10"：左半=1，右半=0
            left = m[:, :_HALF]
            right = m[:, _HALF:]
            if left.sum() > 3:
                _TPL.setdefault(1, left)
            if right.sum() > 3:
                _TPL.setdefault(0, right)
    return sorted(_TPL)


def _match(mask):
    """与单字符模板匹配，返回 (数字, 距离)。"""
    best, bd = None, 10 ** 9
    for d, tpl in _TPL.items():
        if tpl.shape != mask.shape:
            continue
        dist = int((mask != tpl).sum())
        if dist < bd:
            best, bd = d, dist
    return best, bd


def read_num(im, row, col):
    """读格内关卡号（1..100）。返回 int 或 None（问号/识别失败）。"""
    m = _cell_mask(im, row, col)
    if m.sum() <= 3:
        return None
    cols = m.sum(axis=0)
    nz = np.nonzero(cols)[0]
    if nz.size == 0:
        return None
    width = nz.max() - nz.min()
    if width <= 8:                       # 一位数
        d, dist = _match(m)
        return d if dist < 40 else None
    # 两位数：左右各半
    ld, ldist = _match(m[:, :_HALF])
    rd, rdist = _match(m[:, _HALF:])
    if ldist >= 45 or rdist >= 45:
        return None
    return ld * 10 + rd


def grab_np():
    return np.asarray(ds.grab("").convert("RGB")).astype(int)


# ---------- 页面状态 ----------
def in_select_page(im=None):
    """选关页判定：下半部有青色格子。"""
    if im is None:
        im = grab_np()
    R, G, B = im[:, :, 0], im[:, :, 1], im[:, :, 2]
    m = (B > 110) & (G > 80) & (R < 90)
    m[:265, :] = False
    return int(m.sum()) > 800


def cursor_cell(im=None):
    """光标所在可见格 (row, col)；无则 None。"""
    if im is None:
        im = grab_np()
    R, G, B = im[:, :, 0], im[:, :, 1], im[:, :, 2]
    m = (G > 225) & (R < 40) & (B < 120) & (G - B > 120)
    m[:265, :] = False
    ys, xs = np.nonzero(m)
    if len(ys) < 10:
        return None
    cx, cy = float(np.median(xs)), float(np.median(ys))
    col = int(round((cx - COL_X0) / COL_DX))
    row = int(round((cy - ROW_Y[0]) / 16))
    if 0 <= col <= 9 and 0 <= row <= N_VIS_ROWS - 1:
        return row, col
    return None


def page_top_num():
    """当前可见首行首格的关卡号（= 页首关卡号）；读不出返回 None。"""
    im = grab_np()
    for c in range(N_COLS):
        n = read_num(im, 0, c)
        if n is not None:
            return n
    return None


# ---------- 翻页 ----------
def scroll_once(down=True, after=0.7):
    x, y = ARROW_DOWN if down else ARROW_UP
    ds.tap_local(x, y, after=after)


def scroll_to_top():
    """滚到顶屏（可见首行=第 1 关）。"""
    for _ in range(12):
        before = page_top_num()
        scroll_once(down=False)
        after = page_top_num()
        if before is not None and after is not None and before == after:
            return True
        if before is None and after is None:
            # 读不出号时退化为图像判据
            pass
    return True


def scroll_to_bottom():
    """滚到底屏（可见首行=第 51 关）。"""
    for _ in range(12):
        before = page_top_num()
        scroll_once(down=True)
        after = page_top_num()
        if before is not None and after is not None and before == after:
            return True
    return True


def goto_level(n):
    """把第 n 关点选（进入预览）。返回 True=已点击。

    策略：先读当前页首号 → 计算目标行是否可见 → 需翻页则翻到对应位置。
    """
    top = page_top_num()
    if top is None:
        scroll_to_top()
        top = page_top_num() or 1
    row_global = (n - 1) // N_COLS
    cur_top_row = (top - 1) // N_COLS
    vis_row = row_global - cur_top_row
    if not (0 <= vis_row < N_VIS_ROWS):
        # 需要翻页：先滚到底（页首=51）再滚到目标
        scroll_to_bottom()
        top2 = page_top_num() or 51
        cur_top_row = (top2 - 1) // N_COLS
        vis_row = row_global - cur_top_row
        if not (0 <= vis_row < N_VIS_ROWS):
            return False
    col = (n - 1) % N_COLS
    ds.tap_local(COL_X0 + COL_DX * col, ROW_Y[vis_row], after=1.2)
    return True


def main():
    im = grab_np()
    print("在选关页:", in_select_page(im))
    print("模板:", build_ocr(im))
    print("第0行:", [read_num(im, 0, c) for c in range(N_COLS)])
    print("第1行:", [read_num(im, 1, c) for c in range(N_COLS)])
    print("第4行:", [read_num(im, 4, c) for c in range(N_COLS)])
    print("页首号:", page_top_num())
    print("光标:", cursor_cell(im))


if __name__ == "__main__":
    main()
