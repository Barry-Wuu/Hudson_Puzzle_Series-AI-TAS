#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vol.12 美術館(Akari)「やさしい」批量清关驱动（seg2）。

用法: python3.11 play_akari_seg2.py <起始关> <结束关> [warmup]

2026-10-28 实测标定：
  * 选关网格 10 列 × 5 行可见，行中心 y = 278,294,310,326,342（行距 16）
    列中心 x = 19 + 24*col；右侧 ▲(236,266) / ▼(236,352) 每次滚 1 行 = 10 关
  * 点格 = 选中（显示预览），再按 A(x) 才进关
  * 未解锁关卡显示「?」，点击无效 → 必须逐关解锁（前 40 关可玩，41+ 需解锁）
  * 10×10 盘面几何 X0=16 Y0=208 P=16（墙检测 100/100 精确匹配）
  * 触摸解禁需进关后 ~4.5s（实测前 8 灯被吞，第 9 灯起生效）
  * 点灯剂量：gap=0.04 hold=0.10 after=0.06（10×10 敏感度低于 6×6）
  * 通关判定：暗格数（黑格像素）≈0
"""
import json
import os
import sys
import time

import numpy as np

import ds

# ---------- 10×10 盘面几何 ----------
X0, Y0, P = 16, 208, 16
W, H = 10, 10

# ---------- 选关网格 ----------
ROW_Y = [278, 294, 310, 326, 342]
COL_X0, COL_DX = 19, 24
ARROW_UP, ARROW_DOWN = (236, 266), (236, 352)
N_VIS_ROWS = 5

PUZZLES = os.path.join(os.path.dirname(__file__), "..", "validation", "puzzles.json")

# 点灯剂量（10×10 实测）
DOSE = dict(gap=0.04, hold=0.10, after=0.06)
# 进关后触摸解禁等待（保守值；实测解禁 ≈5.1s，但用探针法更省）
UNLOCK_WAIT = 8.0
# 探针法：把第 1 盏灯当探针反复点，点亮即为输入解禁的信号
PROBE_MAX = 14          # 最多试 14 次（每次 ~0.55s）
PROBE_AFTER = 0.10

SENTINEL = "/tmp/v12_rec_start"
STOP_SENTINEL = "/tmp/v12_rec_stop"


def grab_np():
    return np.asarray(ds.grab("").convert("RGB")).astype(int)


# ---------- 选关页 ----------
def in_select_page(im=None):
    """是否在「問題選択」选关页。

    ★2026-10-28 重写（旧判据不可靠）：
      旧判据 = 下屏青蓝像素 > 800 ⇒ 关卡页（10×10 盘面有大量蓝格）也会误判 True，
      导致 Q50 时"回选关页"判定混乱。
    新判据 = 上屏 y=196..234 区域存在**贯穿的蓝色标题条**
      （「やさしい」+「クリアした問題 N/100」），实测：
        选关页：blue 行峰值 **恒为 190**（1122/1122 帧）
        关卡页：0 / 48 / 62 / 206 等，仅 0.14% 偶然等于 190
    ⇒ 用 blue >= 180 作为选关页判据。
    """
    if im is None:
        im = grab_np()
    im = np.asarray(im.convert("RGB")).astype(int) if not isinstance(im, np.ndarray) else im
    reg = im[196:234, 8:214, :].astype(int)
    m = (reg[:, :, 2] > 110) & (reg[:, :, 0] < 95) & (reg[:, :, 1] > 60)
    return int(m.sum(axis=1).max()) >= 180


def cursor_cell(im=None):
    """光标所在可见格 (row, col)。"""
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


def _grid_sig(im=None):
    """网格内容签名：50 个格心的白像素数向量。

    ★2026-10-28 修：原用整块图 diff 判定到边，但选关页**背景花纹是动态的**
      （整图 diff 永远 >3000），导致 scroll_edge 每次都点满 14 次 = 白等 10s/关。
      改用格心白像素向量 → 背景动不影响，2 次点击即判到边。
    """
    if im is None:
        im = grab_np()
    v = []
    for r in range(N_VIS_ROWS):
        for c in range(10):
            x = COL_X0 + COL_DX * c
            y = ROW_Y[r]
            reg = im[y - 6:y + 7, x - 6:x + 7, :]
            v.append(int(((reg[:, :, 0] > 190) & (reg[:, :, 1] > 190)
                          & (reg[:, :, 2] > 190)).sum()))
    return np.array(v)


def scroll_edge(down=True, tries=14):
    """连续点 ▲/▼ 直到画面不再变化（到边）。"""
    x, y = ARROW_DOWN if down else ARROW_UP
    prev = None
    for _ in range(tries):
        ds.tap_local(x, y, after=0.6)
        cur = _grid_sig()
        if prev is not None and int(np.abs(cur - prev).sum()) < 20:
            return True
        prev = cur
    return False


# ---------- 绝对定位导航 ----------
# 100 关 = 10 个全局行；选关页可见 5 行；▲/▼ 每次滚 1 行（=10 关）。
# 可见首行 top 的取值范围 0..5：
#   top=0 → 可见全局行 0..4（关 1..50）
#   top=1 → 1..5, ... top=5 → 5..9（关 51..100）
# 目标全局行 rg=(n-1)//10；需要 top<=rg<=top+4。
#   rg<=4 → 需 top<=rg（滚到顶再往下滚 rg 步最简单）
#   rg>=5 → 需 top=rg-4（精确滚）
_TOP = 0                  # 当前可见首行的全局行


def _scroll_up_to_top():
    """点 ▲ 滚到顶（top=0）。返回 True。"""
    global _TOP
    prev = None
    for _ in range(14):
        ds.tap_local(ARROW_UP[0], ARROW_UP[1], after=0.55)
        cur = _grid_sig()
        if prev is not None and int(np.abs(cur - prev).sum()) < 20:
            _TOP = 0
            return True
        prev = cur
    _TOP = 0
    return True


def _scroll_down_steps(k):
    """点 ▼ 滚 k 行（每行=10 关）。"""
    global _TOP
    for _ in range(k):
        ds.tap_local(ARROW_DOWN[0], ARROW_DOWN[1], after=0.55)
        _TOP += 1
    return _TOP


def goto_level(n):
    """把光标移到第 n 关并按下 A 进关。返回 True=已进入。

    ★2026-10-28 改为**绝对定位**：每关先滚到顶，再精确往下滚到目标行，
      最后点击目标格 —— 不依赖光标历史状态，避免跨页漂移。
      早期用 D-pad 走位（_PAGE_TOP_ROW 缓存）在跨页时会累积误差。
    ★2026-10-28 再修：导航前必须确保**真的在选关页**
      （里程碑画面下触摸无效 → 光标不动 → 反复进同一关）。
    """
    global _TOP
    if not wait_select_page(10.0):
        return False
    rg = (n - 1) // 10            # 目标全局行 0..9
    col = (n - 1) % 10            # 目标列 0..9
    # 需要 top 使 rg 落在可见 5 行内
    if rg <= 4:
        # top=0 时可见全局行 0..4，目标 rg 就在索引 rg 处
        _scroll_up_to_top()
        vis_row = rg
    else:
        # 需 top = rg-4，使目标落在可见最后一行
        _scroll_up_to_top()
        _scroll_down_steps(rg - 4)
        vis_row = 4
    ds.tap_local(COL_X0 + COL_DX * col, ROW_Y[vis_row], after=0.9)
    # ★2026-10-28 加校验：点击后确认光标真的落在目标格（绿色框）。
    #   若没落在目标格（点击被过渡页吞掉 / 位置算错），重试点击。
    for _ in range(4):
        im = ds.grab("")
        cc = cursor_cell(np.asarray(im.convert("RGB")).astype(int))
        if cc is None or cc == (vis_row, col):
            break
        ds.tap_local(COL_X0 + COL_DX * col, ROW_Y[vis_row], after=0.9)
    else:
        print(f"  [goto Q{n}] 光标未落到目标格 {vis_row},{col}", flush=True)
    ds.press("x", wait=0.6)         # A 进关
    return True


# ---------- 盘面 ----------
def board_pixels(im):
    """返回 10×10 的蓝色（墙）掩码。"""
    a = np.asarray(im.convert("RGB")).astype(int) if not isinstance(im, np.ndarray) else im
    a = a
    out = np.zeros((H, W), dtype=bool)
    for r in range(H):
        for c in range(W):
            cx, cy = int(X0 + P * (c + 0.5)), int(Y0 + P * (r + 0.5))
            cell = a[cy - 5:cy + 6, cx - 5:cx + 6].reshape(-1, 3)
            blue = ((cell[:, 2] > 100) & (cell[:, 2] > cell[:, 0] + 35)).mean()
            out[r, c] = blue > 0.35
    return out


def board_dark_count(im):
    """暗格数：非墙且未被点亮的格数（光照未扩散到）。"""
    a = np.asarray(im.convert("RGB")).astype(int) if not isinstance(im, np.ndarray) else im
    n = 0
    for r in range(H):
        for c in range(W):
            cx, cy = int(X0 + P * (c + 0.5)), int(Y0 + P * (r + 0.5))
            cell = a[cy - 5:cy + 6, cx - 5:cx + 6].reshape(-1, 3)
            blue = ((cell[:, 2] > 100) & (cell[:, 2] > cell[:, 0] + 35)).mean()
            if blue <= 0.35:
                n += 1
    return n


def _lit_at(bx, by):
    """该格是否已点灯（灯亮 = 黄块 (251,239,32)）。"""
    cx, cy = int(X0 + P * (bx + 0.5)), int(Y0 + P * (by + 0.5))
    a = np.asarray(ds.grab("").convert("RGB")).astype(int)
    cell = a[cy - 4:cy + 5, cx - 4:cx + 5].reshape(-1, 3)
    yellow = ((cell[:, 0] > 190) & (cell[:, 1] > 170) & (cell[:, 2] < 120)).sum()
    return yellow > 12


def _probe_lit(pt, pz):
    """兼容旧调用：探针灯是否点亮。"""
    bx, by = pz["bulbs"][0]
    return _lit_at(bx, by)


def bulb_points(pz):
    pts = []
    for (x, y) in pz["bulbs"]:
        pts.append((int(X0 + P * (x + 0.5)), int(Y0 + P * (y + 0.5) - 192)))
    return pts


def expected_walls(pz):
    """puzzles.json 的 given 数组 -> 墙布局（'W' 墙 / '.' 空）。"""
    w = pz["w"]
    return [''.join('.' if pz["given"][y * w + x] == 45 else 'W' for x in range(w))
            for y in range(pz["h"])]


def check_walls(im, pz, min_match=90):
    """墙布局比对（防御：确认真的进了目标关）。"""
    im = np.asarray(im.convert("RGB")).astype(int) if not isinstance(im, np.ndarray) else im
    exp = expected_walls(pz)
    got = []
    for r in range(pz["h"]):
        row = ''
        for c in range(pz["w"]):
            cx, cy = int(X0 + P * (c + 0.5)), int(Y0 + P * (r + 0.5))
            cell = im[cy - 5:cy + 6, cx - 5:cx + 6].reshape(-1, 3)
            blue = ((cell[:, 2] > 100) & (cell[:, 2] > cell[:, 0] + 35)).mean()
            row += 'W' if blue > 0.35 else '.'
        got.append(row)
    m = sum(x == y for r1, r2 in zip(got, exp) for x, y in zip(r1, r2))
    return m >= min_match, m


# ---------- 关号闭环校验 ----------
# ★2026-10-28 新增（关键修复）：
#   批量跑到 Q51 时出现「墙布局不匹配」⇒ 根因是**进关时游戏画面被上一关的
#   里程碑/说明页打断**，导致导航滚动态错位、选错了格。
#   反过来，puzzles.json 的编号是可靠的（实测 Q51/Q70 都能与实际盘面 100/100
#   精确匹配），所以**用下屏实际盘面反查真实关号**做闭环校验：
#     进关 → 读盘面 → 与 puzzles.json 全表比对 → 得到真实关号 → 若不是目标则重试。
_EPS = [(i + 1, expected_walls(p))
        for i, p in enumerate(json.load(open(PUZZLES))["やさしい"])
        if p["w"] == W and p["h"] == H]


def board_rows(im):
    """读下屏 10×10 盘面的墙布局。"""
    a = np.asarray(im.convert("RGB")).astype(int) if not isinstance(im, np.ndarray) else im
    out = []
    for r in range(H):
        row = ""
        for c in range(W):
            cx, cy = int(X0 + P * (c + 0.5)), int(Y0 + P * (r + 0.5))
            cell = a[cy - 5:cy + 6, cx - 5:cx + 6].reshape(-1, 3)
            blue = ((cell[:, 2] > 100) & (cell[:, 2] > cell[:, 0] + 35)).mean()
            row += "W" if blue > 0.35 else "."
        out.append(row)
    return out


def detect_level(im=None):
    """由下屏盘面反查真实关号。返回 (匹配数, 关号)；匹配数 <95 表示不可信。"""
    if im is None:
        im = ds.grab("")
    got = board_rows(im)
    best = (0, 0)
    for idx, exp in _EPS:
        m = sum(x == y for r1, r2 in zip(got, exp) for x, y in zip(r1, r2))
        if m > best[0]:
            best = (m, idx)
    return best


def escape_to_select():
    """Start 菜单 → 問題選択へ → はい → 回选关页。"""
    ds.press("Return", wait=1.5)
    ds.tap_local(197, 215, after=1.2)
    ds.press("x", wait=1.5)
    return wait_select_page(12.0)


def is_clear_panel(im=None):
    """通关成绩面板判定：上屏出现「クリアタイム」黄字 + 蓝底框。

    ★2026-10-28 修：通关后盘面已消失，此时用暗格数判定必然失败
      （实测 Q3 已通关但 dark=46 被误判失败）。改用面板特征判定。
    """
    if im is None:
        im = ds.grab("")
    a = np.asarray(im.convert("RGB")).astype(int)
    # ★2026-10-28 修（实测标定）：通关面板在**下屏**，特征是深蓝面板底色 (49,82,123)
    #   大面积出现；选关页该值 = 0。实测 Q3/Q4 通关面板 low_panel ≈ 5900，
    #   选关页 = 0 ⇒ 阈值 3000 稳健。（黄字/白字在两页都大量出现，不可用。）
    seg = a[190:384, :, :].reshape(-1, 3)
    panel = ((np.abs(seg[:, 0] - 49) < 14) & (np.abs(seg[:, 1] - 82) < 14)
             & (np.abs(seg[:, 2] - 123) < 14)).sum()
    return panel > 3000


# ---------- 2026-10-28 关键修复：三类"过渡页" ----------
# 根因（实测）：
#  1) 每 10 关通关后弹**里程碑画面**（「50問クリア達成しました！」等），
#     下屏仍渲染**上一关的盘面** ⇒ 关号闭环校验把它误判成"进错关"，
#     而此时 goto_level 的触摸落在里程碑画面上无效 ⇒ 光标停在 Q60 ⇒ 反复进 Q60。
#  2) 个别关进关后下屏有 **START 覆盖层**（「START スタート」大字幕），
#     需要再按一次 A 才能真正开始点灯。
#  3) 「ルール N/6」规则说明页：上屏绿标题栏，**下屏是真实盘面**，
#     不需翻页，直接点灯即可（但要能识别出来，避免误判）。
def has_start_overlay(im=None):
    """下屏是否有 START 大字幕覆盖层（需按一次 A）。"""
    if im is None:
        im = ds.grab("")
    a = np.asarray(im.convert("RGB")).astype(int)
    seg = a[192:300, 0:200].reshape(-1, 3)
    orange = ((seg[:, 0] > 200) & (seg[:, 1] > 110) & (seg[:, 1] < 215)
              & (seg[:, 2] < 95)).sum()
    return orange > 800


def is_milestone(im=None):
    """是否是里程碑/规则说明页（**不是**真正的选关页）。

    里程碑页特征：上屏有大幅标题/插画，但**没有**选关页的蓝色标题条
    （in_select_page 判据已覆盖反例）；这里补充一条：里程碑页下屏不出现
    关卡网格的白格阵列。实测里程碑页 in_select_page = False，
    故主要靠 in_select_page 排除；本函数用于打印诊断。
    """
    if im is None:
        im = ds.grab("")
    a = np.asarray(im.convert("RGB")).astype(int)
    seg = a[192:384].reshape(-1, 3)
    orange = ((seg[:, 0] > 200) & (seg[:, 1] > 110) & (seg[:, 1] < 215)
              & (seg[:, 2] < 95)).sum()
    return orange > 2500


def wait_select_page(timeout=12.0):
    """等待真正回到选关页。里程碑/说明页会挡路，需按 x 逐个跳过。"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        im = ds.grab("")
        a = np.asarray(im.convert("RGB")).astype(int)
        if in_select_page(a):
            return True
        ds.press("x", wait=0.8)
    return False


def wait_clear(timeout=10.0):
    """等待通关面板出现。"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if is_clear_panel(ds.grab("")):
            return True
        time.sleep(0.35)
    return False


def play_one(n, pz, _try=0):
    """进关 → 点灯 → 通关 → 回选关页。返回 True 成功。

    ★2026-10-28 关键改造：**用下屏实际盘面反查真实关号**做闭环校验。
      起因：批量跑到 Q51 时「墙布局不匹配」—— 根因是上一关的里程碑/说明页
      打断了导航时序，光标停在别的格 ⇒ 进了别的关。
      现在进关后先 detect_level() 反查真实关号：
        * 真实关号 == 目标 n ⇒ 正常点灯
        * 不等 ⇒ 打印实际关号并返回 False（由 main 的重试逻辑重来）
    """
    if not goto_level(n):                     # 内含按 A 进关
        print(f"  [Q{n}] goto 失败", flush=True)
        return False
    # 等盘面画出，并用**盘面反查关号**判定是否真的进了目标关
    im = ds.grab(f"Q{n}_in")
    m, real = detect_level(im)
    for _ in range(12):
        if m >= 95:
            break
        time.sleep(0.8)
        im = ds.grab("")
        m, real = detect_level(im)
    # ★START 覆盖层：部分关进关后下屏叠「START スタート」大字幕（会自行淡出，
    #   实测 Q61/Q62 都有）。此时下屏仍是本关盘面 ⇒ 关号校验能通过，
    #   只是**触摸点灯会被字幕挡住**，故等它淡出再点灯。
    #   真正会导致"进错关"的是**里程碑画面**（下屏渲染上一关盘面），
    #   那种情况盘面匹配的是**别的关号**（real != n），靠上面的 real 校验抓出。
    if m < 95:
        # 盘面还没画好 → 再等（最多 12s）
        for _ in range(12):
            time.sleep(0.8)
            im = ds.grab("")
            m, real = detect_level(im)
            if m >= 95:
                break
    if m < 95:
        print(f"  [Q{n}] 盘面不可信 (m={m})", flush=True)
        return False
    if real != n:
        print(f"  [Q{n}] 进错关：实际是第 {real} 关", flush=True)
        return False
    # 等 START 字幕淡出（不按键，只等）
    for _ in range(10):
        if not has_start_overlay(im):
            break
        time.sleep(0.6)
        im = ds.grab("")
    # ★逐盏点灯 + 逐盏校验
    #   旧「探针法」用第 1 盏灯当探针反复点，点亮后若检测慢一拍会**再点一次**，
    #   Akari 里再点灯会熄灭 ⇒ 出现 14/15 亮、1 盏黑（实测 Q2 失败）。
    #   新策略：每盏灯点一次，点完逐盏校验；未亮的补点一次（最多 2 轮）。
    #   灯亮特征：黄块 (251,239,32)，黄像素 > 12 视为已亮。
    pts = bulb_points(pz)
    coords = [(int(X0 + P * (bx + 0.5)), int(Y0 + P * (by + 0.5) - 192))
              for (bx, by) in pz["bulbs"]]
    # 触摸解禁等待（实测 ≈5.1s，取 6.5s 留余量）
    time.sleep(6.5)
    for rnd in range(3):
        # 点所有当前未亮的灯
        for i, (bx, by) in enumerate(pz["bulbs"]):
            if not _lit_at(bx, by):
                ds.tap(coords[i][0], coords[i][1], hold=DOSE["hold"], after=DOSE["after"])
        time.sleep(0.5)
        dark_left = [ (bx, by) for (bx, by) in pz["bulbs"] if not _lit_at(bx, by) ]
        if not dark_left:
            break
        if rnd == 2:
            print(f"  [Q{n}] 仍有未亮灯 {dark_left}", flush=True)
    time.sleep(0.6)
    if not wait_clear(10.0):
        dk = board_dark_count(ds.grab(f"Q{n}_fail"))
        print(f"  [Q{n}] 未通关，暗格 {dk}", flush=True)
        return False
    time.sleep(2.5)                          # 结算稳定
    # ★回选关页要按多次 x：
    #   通关面板 →（可能插入「50問クリア達成しました！」里程碑画面）→ 选关页。
    #   实测第 30 关触发里程碑，多按一次 x 才能回到选关页且光标仍在原格。
    # ★2026-10-28：通关后的关卡格会变绿底 ⇒ 光标框消失，cursor_cell 判 None。
    #   故回选关页只看 in_select_page（蓝色标题条判据），不再要求光标可见。
    for _ in range(12):
        ds.press("x", wait=0.9)
        if in_select_page(grab_np()):
            return True
        time.sleep(0.3)
    return False


def main():
    lo, hi = int(sys.argv[1]), int(sys.argv[2])
    data = json.load(open(PUZZLES))
    seq = data["やさしい"]
    if not in_select_page():
        print("不在选关页", flush=True)
        return 1
    try:
        open(SENTINEL, "w").close()
    except OSError:
        pass
    print(f"[rec] START @ select", flush=True)
    time.sleep(0.8)
    ok_n = 0
    for n in range(lo, hi + 1):
        pz = seq[n - 1]
        if pz["w"] != W or pz["h"] != H:
            print(f"  [Q{n}] 尺寸 {pz['w']}x{pz['h']} 非 10×10，跳过", flush=True)
            break
        ok = play_one(n, pz)
        # ★自愈重试：偶发「进错关 / 过场打断」。
        #   布局本身经核对与 puzzles.json **100/100 精确匹配**（Q51/Q70 实测），
        #   问题在瞬时状态 ⇒ 退回选关页重试即可（实测重试可自愈 Q46）。
        for attempt in range(4):
            if ok:
                break
            print(f"  [Q{n}] 重试 {attempt + 1}/4", flush=True)
            try:
                escape_to_select()
            except Exception:
                pass
            time.sleep(1.2)
            ok = play_one(n, pz)
        print(f"  [Q{n}] ok={ok}", flush=True)
        if not ok:
            print(f"FAIL Q{n}", flush=True)
            break
        ok_n += 1
        if n == hi:
            try:
                open(STOP_SENTINEL, "w").close()
            except OSError:
                pass
            print(f"[rec] STOP @ select (after Q{n})", flush=True)
    print(f"cleared {ok_n}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
