#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vol.12 美術館(Akari)「むずかしい」批量清关驱动（muzusaki，70 关）。

用法: python3.11 play_akari_muzu.py [--tutorial] <起始关> <结束关>

尺寸分组（puzzles.json 实测）：
  Q1-50   24×14    几何同ふつう seg3（X0=16 Y0=208 P=16, big）
  Q51-70  36×20    新增大盘尺寸（已标定几何，big）

★ 核心录制策略（用户硬性要求）：
  1. 点击剂量尽量快：大盘走 touch 直点 batch（gap=0.02/hold=0.06≈0.08s/盏，
     实测 15/15 零丢失），光标本身不移动、不扫全场；
  2. 不浪费题面滚动步数：复用 seg3 的「触屏直点 + 视口记账」路线（light_big），
     视口只被**直接驱动**到需要的窗口（dc/dr 增量步进），绝不在每画面点灯前后
     用光标在整个关卡里滚动一整圈（旧光标走位方案的病根，本脚本从根上废除）；
  3. 录 muzusaki 前先打过入門第一关（--tutorial），以免后续再弹教程。

★ BGM：开录前由 setup_bgm*.py 设好；pkill 刷 SRAM 后重启会继承。

沿用 seg3 全部已验证机制：绝对定位导航 + 光标落格校验 + 盘面反查关号
闭环校验 + START 覆盖层等待 + 4 次自愈重试。
"""
import json
import os
import sys
import time

import numpy as np

import ds

PUZZLES = os.path.join(os.path.dirname(__file__), "..", "validation", "puzzles.json")
import gridocr                      # 选关网格数字 OCR（模板匹配）
DIFF = "やさしい"
N_TOTAL = 100

# ---------- 盘面几何（按尺寸） ----------
# (w,h) -> dict(X0, Y0, P)；None = 未标定
# ★2026-10-28 晚实测：18×10 与 10×10 同几何（X0=16 Y0=208 P=16），
#   但 18×16=288px 超出下屏视口（~13 列可见）→ 盘面**可横向滚动**；
#   24×14 同理且纵向也超出（14×16=224 > ~172）→ 纵向滚动。
#   滚动 = D-pad 移动光标到视口边缘自动滚；光标(橙角括号)始终被视口包含。
GEO = {
    (10, 10): dict(X0=16, Y0=208, P=16),
    (18, 10): dict(X0=16, Y0=208, P=16, big=True),
    (24, 14): dict(X0=16, Y0=208, P=16, big=True),
    (36, 20): dict(X0=16, Y0=208, P=16, big=True),
    # ★ 入門 6×6 几何为**推断值**（同 10×10 锚点 X0=16 Y0=208 P=16），真机首跑须
    #   核对 board 左上角像素；若错位只改这一条即可。仅教程前置（打 L1）用到。
    (6, 6): dict(X0=16, Y0=208, P=16),
}
# 视口可见格数（18×10 实测 ~13 列；保守用 11 列做匹配，避开边缘半格）
VIS_W = 11
VIS_H = 8
# 点灯剂量（按尺寸）
DOSE_BY_SIZE = {
    # ★2026-11-01 补 (6,6)：教程前置 tutorial_prep 要打入門 L1（入門 20 关全是 6×6），
    #   缺键会 KeyError 直接崩 driver（play_one 首行就取 dose）。
    (6, 6): dict(gap=0.04, hold=0.10, after=0.06),
    (10, 10): dict(gap=0.04, hold=0.10, after=0.06),
    (18, 10): dict(gap=0.04, hold=0.10, after=0.06),   # 初值，标定时校准
    (24, 14): dict(gap=0.04, hold=0.10, after=0.06),
    (36, 20): dict(gap=0.04, hold=0.10, after=0.06),
}

# ---------- 选关网格（110 关 = 11 全局行，其余同 seg2） ----------
ROW_Y = [278, 294, 310, 326, 342]
COL_X0, COL_DX = 19, 24
ARROW_UP, ARROW_DOWN = (236, 266), (236, 352)
N_VIS_ROWS = 5

SENTINEL = "/tmp/v12_yasa_rec_start"
STOP_SENTINEL = "/tmp/v12_yasa_rec_stop"


_LAST_FRAME = [None]


def grab_np():
    """抓帧 → ndarray(int)。优先常驻帧流（零进程开销、不抢 X 服务），失败回退旧 ffmpeg 截图。

    ★2026-11-03 修：录制时 driver 与录制器各自 x11grab 已争抢 X/CPU；旧 grab() 每次
      再 spawn ffmpeg ⇒ 进程风暴 ⇒ desmume 欠载、音乐卡顿。改走 ds.grab_np_fast()
      （单后台 ffmpeg 持续出帧，取最新）。仍保留 legacy 兜底与上一帧兜底（C 段 Q51 教训）。
    """
    try:
        a = ds.grab_np_fast()
        if a is not None:
            a = a.astype(int)
            _LAST_FRAME[0] = a
            return a
    except Exception:
        pass
    try:
        a = np.asarray(ds.grab("").convert("RGB")).astype(int)
        _LAST_FRAME[0] = a
        return a
    except Exception:
        time.sleep(0.6)
        try:
            a = np.asarray(ds.grab("").convert("RGB")).astype(int)
            _LAST_FRAME[0] = a
            return a
        except Exception:
            if _LAST_FRAME[0] is not None:
                return _LAST_FRAME[0]
            raise


# ---------- 棋盘光标实测（替代"盲按 20 次钉角"） ----------
# ★2026-11-04 实测定标：光标是盘面格上的**橙色四角括号**，全屏唯一，由固定三色
#   构成 (255,82,0)/(246,205,0)/(238,57,0)，共 120 px，bbox 20×20。
#   视口内第 (vc,vr) 格的光标框左上角 = (14 + 16*vc, 206 + 16*vr)；
#   实测 Right×3+Down×2 后 bbox 精确平移 (48,32) = (3×16, 2×16) ⇒ 反解可靠。
CUR_X0, CUR_Y0, CUR_DX = 14, 206, 16


def _cursor_cell(a):
    """从帧里读出棋盘光标在**视口内**的格坐标 (vc, vr)；读不到返回 None。

    只认光标专属三色，且要求 bbox 形态吻合（约 20×20、像素数 90~160），
    避免把灯泡/数字误认成光标。vc/vr 为视口内坐标（0 起），供上层加视口
    偏移 dc/dr 换算成棋盘绝对坐标。
    """
    try:
        r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
        m = (((r == 255) & (g == 82) & (b == 0)) |
             ((r == 246) & (g == 205) & (b == 0)) |
             ((r == 238) & (g == 57) & (b == 0)))
        ys, xs = np.nonzero(m)
        if len(xs) < 80 or len(xs) > 170:
            return None
        x0, x1 = int(xs.min()), int(xs.max())
        y0, y1 = int(ys.min()), int(ys.max())
        if not (16 <= x1 - x0 <= 26 and 16 <= y1 - y0 <= 26):
            return None                     # 形态不符：不是光标括号
        vc = int(round((x0 - CUR_X0) / CUR_DX))
        vr = int(round((y0 - CUR_Y0) / CUR_DX))
        if not (-1 <= vc <= 10 and -1 <= vr <= 9):
            return None
        return max(0, vc), max(0, vr)
    except Exception:
        return None


# ---------- 选关页（判据同 seg2：上屏蓝色标题条） ----------
def in_select_page(im=None):
    """选关页判据 v2（2026-10-30）：蓝标题带 + 关卡网格签名 **双条件**。

    ★旧单蓝带判据被盘面页误触发：大盘顶部行 y196-234 与蓝墙格重叠，一整行
      蓝墙即可凑满 180px ⇒ escape_to_select 假成功、goto_level 按键全打进
      盘面（Q31 m=0 四连败 + 编排器 C/D/E1/E2 全部空跑的根因）。
      补 state2.cells 同款网格签名（teal/green 单元格，盘面页黑/蓝格不命中）。
    """
    if im is None:
        im = grab_np()
    im = np.asarray(im.convert("RGB")).astype(int) if not isinstance(im, np.ndarray) else im
    reg = im[196:234, 8:214, :]
    m = (reg[:, :, 2] > 110) & (reg[:, :, 0] < 95) & (reg[:, :, 1] > 60)
    if int(m.sum(axis=1).max()) < 180:
        return False
    g = im[268:302, 8:248, :]
    teal = ((g[:, :, 0] < 40) & (g[:, :, 1] > 70) & (g[:, :, 1] < 170)
            & (g[:, :, 2] > 100) & (g[:, :, 2] < 180))
    green = ((g[:, :, 0] < 140) & (g[:, :, 1] > 100) & (g[:, :, 1] > g[:, :, 0] + 50)
             & (g[:, :, 2] < 130))
    if int((teal | green).sum()) <= 800:
        return False
    # ★弹窗条的深蓝 (0,98,131) 也满足上面的 teal 掩码 ⇒ 弹窗页会假阳性，
    #   必须显式排除（v6 首测 force_futsuu 跳过点选的根因）
    return not _popup_open(im)


def cursor_cell(im=None):
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


def _scroll_up_to_top():
    global _TOP
    prev = None
    for _ in range(16):
        ds.tap_local(ARROW_UP[0], ARROW_UP[1], after=0.55)
        cur = _grid_sig()
        if prev is not None and int(np.abs(cur - prev).sum()) < 20:
            _TOP = 0
            return True
        prev = cur
    _TOP = 0
    return True


def _scroll_down_steps(k):
    global _TOP
    for _ in range(k):
        ds.tap_local(ARROW_DOWN[0], ARROW_DOWN[1], after=0.55)
        _TOP += 1
    return _TOP


_TOP = 0


_CUR = [None]     # 选关网格光标的绝对关号（None=未知）；跨关记忆避免每关重定位
_TPL = gridocr.load_templates(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           "grid_digits.json"))


def _popup_open(im):
    """难度弹窗判据：ふつう条带(y299-316)深蓝实心条最长连续 run > 80。

    ★2026-10-30 实测标定：弹窗 4 条位置固定（入門242-261/やさしい270-289/
      ふつう298-317/ずかんしい326-345），条色 (0,98,131)。条带内最长连续 run
      弹窗=152，选关页/盘面页/标题=0（网格格仅 ~20px 宽）。
    ★弹窗条色恰好也满足网格 teal 掩码 ⇒ in_select_page 在弹窗上也为 True，
      不能用网格签名判弹窗（v6 首测跳过点选的根因）。
    """
    m = ((np.abs(im[:, :, 0] - 0) < 30) & (np.abs(im[:, :, 1] - 98) < 25)
         & (np.abs(im[:, :, 2] - 131) < 28))
    best = 0
    for y in range(299, 316):
        run = cur = 0
        for x in range(8, 248):
            cur = cur + 1 if m[y, x] else 0
            if cur > best:
                best = cur
    return best > 80


def force_futsuu(max_try=3):
    """确保处于「ふつう」选关网格态（v8.8 改为**纯校验**，绝不按键）。

    ★2026-10-30 第二轮实测（会话重启后）：
      本游戏 B(z) 在选关网格页 = 「难度一览」页（入門/やさしい/ふつう/むずかしい
      四条 + 顶部当前难度网格预览），该页 in_select_page()=False。旧实现先按 z
      想「呼出弹窗」，实际是**把网格页踢进难度一览页** → goto_level 里
      in_select_page() 恒 False → 4 轮 attempt 全 continue → 必然失败。
      而 _popup_open() 只用 ふつう 一条 y299-316 判据，在主菜单(ヘルプ按钮)上
      假阳性 True（实测 bars4=[203,106,85,71]），更套不住四条的难度一览页。
    ⇒ 难度由**录制前人工 bring-up** 固定为ふつう（已核实 ふつう 110/110），
      本函数只负责「确认在网格态」，任何按键都不发，最坏退回人工。
    """
    for _ in range(max_try):
        if in_select_page(grab_np()):
            return True
        time.sleep(0.8)
    return in_select_page(grab_np())


# ---------- 难度切换 + 教程前置 ----------
# 难度一览页：选关网格页按 B 打开，显示 入門/やさしい/ふつう/むずかしい 四条横条。
# ★ 条带 y 按 seg3 `_popup_open` 标注（242-261/270-289/298-317/326-345）推算的
#   下屏 nds_y（= 条中心 - 192），为**推断坐标**；B 键名（B_KEY）按 desmume 传统
#   默认 "z"，均须真机首跑核对微调（改这两个常量即可）。
B_KEY = "z"
DIFF_BARS = {
    "入門": (128, 59), "やさしい": (128, 87),
    "ふつう": (128, 115), "むずかしい": (128, 143),
}


def _load_diff(name):
    """切换模块级难度数据（_SEQ / _EPS_BY_SIZE / DIFF），使 goto_level / play_one
    等导航与关号自证函数立即对目标难度生效。教程前置要在 入門 ↔ むずかしい 间切换。"""
    global _SEQ, _EPS_BY_SIZE, DIFF
    DIFF = name
    _SEQ = json.load(open(PUZZLES))[name]
    _EPS_BY_SIZE = {}
    for i, p in enumerate(_SEQ):
        key = (p["w"], p["h"])
        if GEO.get(key) is not None:
            _EPS_BY_SIZE.setdefault(key, []).append((i + 1, expected_walls(p)))


# ---------- 难度一览页：选中条像素判读（2026-11-02 实测标定，4/4 离线验证） ----------
# 难度一览页：**上屏**难度预览（难度名 + クリアした問題 x/N + 网格），**下屏**四条难度列表。
# 四条下边框截图 y = 263/291/319/347（上边框 -22）。
# 未选中条描边恒为青 (0,148,205)；**选中条描边变绿 (77,235,102)**，离群度 ≈266。
# 判据据此用「离群色」而非绝对颜色：三条同色、一条异色 ⇒ 异色即选中，抗个别像素噪声。
# ★为什么必须像素闭环：实测「点条+x」会停在入門；「Up×6 夹到顶再 Down×1」
#   也因按键被吞只走了 2 格（入門→ふつう）。固定步数不可靠 ⇒ 逐格判读纠偏。
DIFF_ORDER = ("入門", "やさしい", "ふつう", "むずかしい")
DIFF_BORDER_Y = (263, 291, 319, 347)      # 各条**下边框**截图 y


def diff_selected_index(im=None):
    """读难度一览页当前选中的条号 0..3；不在该页/判读不可信返回 None。"""
    if im is None:
        im = grab_np()
    a = np.asarray(im.convert("RGB")).astype(int) if not isinstance(im, np.ndarray) else im
    cols = np.array([a[y, 30:226, :].mean(axis=0) for y in DIFF_BORDER_Y])
    med = np.median(cols, axis=0)
    dev = np.abs(cols - med).sum(axis=1)
    i = int(np.argmax(dev))
    if float(dev[i]) < 120:               # 实测选中 266 / 全同色 0
        return None
    return i


def goto_difficulty(name, max_try=4):
    """切到指定难度选关网格：B → 难度一览 → 闭环方向键纠偏 → x 进入。

    ★2026-11-02 重写：旧实现两种打法都不可靠（点条仍停入門 / Up×6 只走 2 格）。
      现改为「读选中条 → 按差值上下逐格纠偏 → 再读一次确认 → x 进入」。
    """
    if name not in DIFF_ORDER:
        return False
    target = DIFF_ORDER.index(name)
    for _ in range(max_try):
        im = grab_np()
        if not _popup_open(im):
            if in_select_page(im):
                ds.press(B_KEY, wait=1.4)        # 选关网格 → 难度一览页
                time.sleep(0.7)
                im = grab_np()
            else:
                escape_to_select()
                time.sleep(0.9)
                continue
        if not _popup_open(im):                  # 没打开难度一览 → 撤回重来
            continue
        for _step in range(8):
            cur = diff_selected_index(im)
            if cur is None or cur == target:
                break
            ds.press("Down" if cur < target else "Up", wait=0.55)
            time.sleep(0.25)
            im = grab_np()
        got = diff_selected_index(im)
        if got != target:
            print(f"  [diff] 纠偏后选中={got} ≠ {target}，重试", flush=True)
            continue
        ds.press("x", wait=1.7)                  # A = 进入该难度选关网格
        time.sleep(0.5)
        if in_select_page(grab_np()) and not _popup_open(grab_np()):
            print(f"  [diff] 已切到 {name}（条号 {target}）", flush=True)
            return True
    return in_select_page(grab_np())


def tutorial_prep(max_try=4):
    """录 muzusaki 前先打过入門第一关，抑制后续教程弹窗。

    流程：切 入門 → 打 L1（首次游玩触发教程，打完即抑制）→ 切回 むずかしい。
    ★ 入門 6×6 几何 / 难度一览条带坐标 / B 键名 均为推断值，真机首跑须核对。
      本函数失败**不至于阻断** muzusaki 录制（返回 False 时 main 仍继续），
      但教程可能照弹 —— 那时请在存档里手动把入門 L1 打一次再重跑。
    """
    _load_diff("入門")
    ok = goto_difficulty("入門")
    tut_ok = False
    if ok:
        tut_ok = play_one(1, _SEQ[0])
    _load_diff("むずかしい")
    goto_difficulty("むずかしい")
    print(f"  [tutorial] 入門 L1 前置 = {tut_ok}", flush=True)
    return tut_ok


def _best_match(a, q):
    """屏幕可见窗口与谜题 q 任意 (sx,sy) 窗口的最大吻合率（0~1）。

    ★v9.1：窗口尺寸取 min(VIS_W,q.w) × min(VIS_H,q.h)——10×10 等小盘 w<VIS_W(=11)
      时旧写法 range(0, w-VIS_W+1) 为空、永远 0 分，导致小盘一律识别失败。
    """
    # ★v9.3：窗口取「屏幕实际可见」(11 列 × 12 行)。旧用 VIS_H=8 只比 8 行，
    #   10×10 盘有 2 行不参与比对 → 相邻关常打平，识别会串关（实测第11問→1）。
    nc, nr = min(VIS_W, q["w"]), min(12, q["h"])
    exp = expected_walls(q)
    E = np.array([[c == 'W' for c in r] for r in exp])
    G = np.array([[c == 'W' for c in r]
                  for r in read_vis_walls(a, q, 0, 0, ncols=nc, nrows=nr)])
    best = 0
    for sy in range(0, q["h"] - nr + 1):
        for sx in range(0, q["w"] - nc + 1):
            m = int((E[sy:sy + nr, sx:sx + nc] == G).sum())
            if m > best:
                best = m
    return best / float(nc * nr)


def _ident_current(pz=None):
    """识别当前盘面是第几关；失败返回 -1。

    ★v9.1：两轮扫描（同尺寸优先 → 全尺寸兜底），按**吻合率**判：冠军 ≥0.90
      且领先亚军 ≥0.06 才算数（相邻关墙图案常高度相似）。
    """
    a = grab_np()

    def _scan(cands):
        bm, bk, sec = 0.0, -1, 0.0
        for k, q in cands:
            m = _best_match(a, q)
            if m > bm:
                sec, bm, bk = bm, m, k
            elif m > sec:
                sec = m
        return bm, bk, sec

    if pz is not None:
        bm, bk, sec = _scan([(k, q) for k, q in enumerate(_SEQ, 1)
                             if (q["w"], q["h"]) == (pz["w"], pz["h"])])
        if bk > 0 and bm >= 0.90 and (bm - sec) >= 0.06:
            return bk
    bm, bk, sec = _scan(list(enumerate(_SEQ, 1)))
    if bk > 0 and bm >= 0.90 and (bm - sec) >= 0.06:
        return bk
    return -1


def _ident_after_enter(pz, tries=8, press_a=True):
    """进关并识别关号（进关过场/解答确认动画期抓帧会识别失败，故重试）。

    ★v8.9 教训：旧版「不在盘面页就按 A」在 24×14 进关动画期会**误按 A 打断流程**
      （实测 Q91 收尾连按 5 次 A → 实际进了 Q96，识别一路 -1）。改为：
      前 2 轮只等不按键，之后才补按 A。
    """
    pressed = False
    for _ in range(tries):
        a = grab_np()
        if in_play_page(a):
            k = _ident_current(pz)
            if k > 0:
                return k
        elif press_a and in_select_page(a) and not pressed:
            # ★v10.1：A 只作用于游戏内部"当前光标关"，而触摸悬停**不会**更新它，
            #   所以触摸没点中时按 A 会进到旧关（实测点 (3,0) 却进了第 11 問）。
            #   goto_level 走触摸路线时传 press_a=False，绝不按 A。
            ds.press("x", wait=1.6)
            pressed = True
            continue
        time.sleep(1.2)
    return -1


# 选关网格「关卡格子」几何（2026-10-30 实测 t0.png 逐列/逐行扫描）：
#   5 行 × 10 列，列中心 x = 20 + 24c，行中心 y = 279 + 16r（下屏局部坐标）
CELL_X0, CELL_DX = 20, 24
CELL_Y0, CELL_DY = 279, 16


def _tap_cell(r, c, after=2.2):
    """触摸选关网格第 (r,c) 格（已解锁关直接进关）。

    ★必须**双触**：DeSmuME 下第一次 mousedown 只把触控笔移到位（游戏内光标跟着
      走但不触发按下），第二次同点按下才真正“点”。单触实测 tap(0,0) 得到的是
      “上一次光标所在关”（w0 实测 4~8 乱跳），双触才稳定。
    ★2026-10-30 标定（diag_nav2）验证：加长 tap1 停留/间隔（hold0.10/after0.8 +
      间隔 0.5s + tap2 hold0.14）可彻底消除「旧光标残留」跳关——tap(3,0)→91、
      tap(4,5)→106 各 3/3 一致。故改用此参数。
    """
    x, y = CELL_X0 + CELL_DX * c, CELL_Y0 + CELL_DY * r
    ds.tap_local(x, y, hold=0.10, after=0.8)   # tap1: 移笔（只移不触发）
    time.sleep(0.5)
    ds.tap_local(x, y, hold=0.14, after=after)  # tap2: 真正选格


# ---------- 选关导航（仿 Vol.11：滚到已知边缘 + 固定坐标点格，免 OCR） ----------
def _grid_img():
    """选关页 5×10 网格区域的局部图（用于判定滚动是否到边）。下屏局部坐标。"""
    a = np.asarray(ds.grab("").convert("RGB")).astype(int)
    return a[268:356, 4:248]


def _tap_arrow(down):
    """双击滚动箭头：第一次移笔（DeSmuME 触屏铁律，只移不触发），第二次才滚动。"""
    ax, ay = (ARROW_DOWN if down else ARROW_UP)
    ds.tap_local(ax, ay, hold=0.08, after=0.18)
    ds.tap_local(ax, ay, hold=0.10, after=0.34)


def scroll_select_edge(down=True):
    """把网格滚到边缘（双击箭头，可靠）：连续滚直到画面不再变化。

    ★修正：单触箭头时第一次触屏只移笔不滚动 ⇒ 图像「假不变」⇒ 误判到边、停在
      错误位置（实测 goto_level(91) 各轮进过 31/106/95，就是滚位乱跳）。改双击箭头，
      每轮稳定滚动 1 行，到边（钳位）再点才真不变 ⇒ 差值趋零退出。
    全清存档下整片绿，「绿行数」判据本就退化，故用图像差判边。
    """
    prev = _grid_img()
    for _ in range(20):
        _tap_arrow(down)
        cur = _grid_img()
        if int(np.abs(cur - prev).sum()) < 1500:
            return True
        prev = cur
    return False


def _find_cell_in_grid(g, n):
    """在 OCR 出的 5×10 关号矩阵里找关号 n 的 (r,c)；找不到返回 None。"""
    for r in range(len(g)):
        for c in range(len(g[0])):
            if g[r][c] == n:
                return r, c
    return None


def goto_level(n, max_rounds=8):
    """走到第 n 关并停在盘面（Vol.11 思路：滚到已知边缘 + 读屏定位 + A 进关）。

    ★v11.1（本次标定重写）：纯坐标点格在全清存档下因触摸箭头漂移 / 9-模板漏识
      会跳关（实测 goto_level(91) 6 轮进过 86/81/41/77/101/52）。改为：
      1) 滚到「已知边缘」——n≤50 滚顶（可见 1-50）、n>50 滚底（可见 61-110）；
         110 关 = 11 全局行，滚底后可见首行恒为第 6 行 = 61 問，窗口确定。
      2) OCR 读当前可见窗口，直接定位 n 的**精确格 (r,c)**（抗滚动漂移 / 坐标误差）；
         仅 96/106 的「9」模板偶漏识时退回坐标兜底（窗口确定 ⇒ 兜底也准）。
      3) 双触点格（选格）+ 按 A(x) 进关（选关页触屏只选不进，play_one 同款）；
      4) _ident_after_enter 读盘面自证关号，不符自动重滚重试。
    """
    pz = _SEQ[n - 1]
    rows_total = (len(_SEQ) + 9) // 10            # 110 关 = 11 全局行
    top_row = max(0, rows_total - N_VIS_ROWS)    # 滚到底后可见首行全局号（110关=6）
    if n <= 50:
        down = False
        g_row = (n - 1) // 10
        fb_r, fb_c = g_row, (n - 1) % 10
    else:
        down = True
        g_row = (n - 1) // 10
        fb_r, fb_c = g_row - top_row, (n - 1) % 10
    print(f"    [nav] 目标 {n} → 全局行 {g_row}, 滚{'底' if down else '顶'}, "
          f"坐标兜底 ({fb_r},{fb_c})", flush=True)
    for att in range(max_rounds):
        if not in_select_page(grab_np()):
            escape_to_select()
            time.sleep(1.0)
            if not in_select_page(grab_np()):
                return False
        scroll_select_edge(down=down)             # 滚到已知边缘（自终止，钳位不环绕）
        time.sleep(0.4)
        # 读屏定位精确格：OCR 找到 n 就用；漏识退回坐标兜底
        g = gridocr.read_grid(grab_np(), _TPL)
        rc = _find_cell_in_grid(g, n)
        if rc is not None:
            r, c = rc
        else:
            r, c = fb_r, fb_c
            print(f"    [nav] OCR 漏识 {n}，坐标兜底 ({r},{c})", flush=True)
        # 双触点格（选格）→ A 进关
        _tap_cell(r, c, after=2.2)
        time.sleep(0.3)
        ds.press("x", wait=1.4)
        # 校验进关关号
        k = -1
        for _try in range(8):
            a = grab_np()
            if in_play_page(a):
                # 已进关：识别关号，绝不触摸（盘面页触摸 = 点灯/开菜单，会把盘面搞坏）
                k = _ident_after_enter(pz, press_a=False, tries=4)
                if k == n:
                    break
                # 进错关 → 退回选关重选（避免停留盘面误点灯）
                escape_to_select()
                time.sleep(1.0)
                break
            time.sleep(0.8)
        if k == n:
            _CUR[0] = n
            return True
        print(f"    [nav] 第 {att + 1} 轮点格得 {k} ≠ {n} → 重滚", flush=True)
        escape_to_select()
        time.sleep(1.0)
    return False


# ---------- 盘面读取（按尺寸参数化） ----------
def expected_walls(pz):
    w = pz["w"]
    return [''.join('.' if pz["given"][y * w + x] == 45 else 'W' for x in range(w))
            for y in range(pz["h"])]


def board_rows(im, pz):
    """按下屏几何读 w×h 墙布局。"""
    g = GEO[(pz["w"], pz["h"])]
    a = np.asarray(im.convert("RGB")).astype(int) if not isinstance(im, np.ndarray) else im
    X0, Y0, P = g["X0"], g["Y0"], g["P"]
    out = []
    for r in range(pz["h"]):
        row = ""
        for c in range(pz["w"]):
            cx, cy = int(X0 + P * (c + 0.5)), int(Y0 + P * (r + 0.5))
            cell = a[cy - 5:cy + 6, cx - 5:cx + 6].reshape(-1, 3)
            blue = ((cell[:, 2] > 100) & (cell[:, 2] > cell[:, 0] + 35)).mean()
            row += "W" if blue > 0.35 else "."
        out.append(row)
    return out


# 关号闭环校验：按尺寸预建 eps 表
_SEQ = json.load(open(PUZZLES))[DIFF]
_EPS_BY_SIZE = {}
for i, p in enumerate(_SEQ):
    key = (p["w"], p["h"])
    if GEO.get(key) is not None:
        _EPS_BY_SIZE.setdefault(key, []).append((i + 1, expected_walls(p)))


def read_vis_walls(a, pz, sx, sy, ncols=VIS_W, nrows=VIS_H):
    """读视口窗口（盘面坐标 sx..sx+ncols, sy..sy+nrows）的墙布局。"""
    g = GEO[(pz["w"], pz["h"])]
    X0, Y0, P = g["X0"], g["Y0"], g["P"]
    out = []
    for r in range(nrows):
        row = ""
        for c in range(ncols):
            cx, cy = int(X0 + P * (c + 0.5)), int(Y0 + P * (r + 0.5))
            cell = a[cy - 5:cy + 6, cx - 5:cx + 6].reshape(-1, 3)
            blue = ((cell[:, 2] > 100) & (cell[:, 2] > cell[:, 0] + 35)).mean()
            row += "W" if blue > 0.35 else "."
        out.append(row)
    return out


def detect_level(im, pz):
    """由下屏盘面反查真实关号。大关 = 视口窗口滑动匹配。"""
    key = (pz["w"], pz["h"])
    a = np.asarray(im.convert("RGB")).astype(int) if not isinstance(im, np.ndarray) else im
    eps = _EPS_BY_SIZE[key]
    if GEO[key].get("big"):
        best = (0, 0)
        h, w = pz["h"], pz["w"]
        for sy in range(0, h - VIS_H + 1):
            for sx in range(0, w - VIS_W + 1):
                got = read_vis_walls(a, pz, sx, sy)
                for idx, exp in eps:
                    m = sum(x == y for r1, r2 in zip(got, exp) for x, y in zip(r1, r2))
                    if m > best[0]:
                        best = (m, idx)
        return best
    got = board_rows(im, pz)
    b = (0, 0)
    for idx, exp in eps:
        m = sum(x == y for r1, r2 in zip(got, exp) for x, y in zip(r1, r2))
        if m > b[0]:
            b = (m, idx)
    return b


def is_target_board(im, pz):
    """进关校验（大关快速路径）：目标关的任意视口窗口匹配 ≥95%。"""
    key = (pz["w"], pz["h"])
    a = np.asarray(im.convert("RGB")).astype(int) if not isinstance(im, np.ndarray) else im
    exp = expected_walls(pz)
    h, w = pz["h"], pz["w"]
    thr = int(0.95 * VIS_W * VIS_H)
    for sy in range(0, h - VIS_H + 1):
        for sx in range(0, w - VIS_W + 1):
            got = read_vis_walls(a, pz, sx, sy)
            m = sum(x == y for r1, r2 in zip(got, exp) for x, y in zip(r1, r2))
            if m >= thr:
                return True
    return False


def _lit_at(bx, by, pz):
    g = GEO[(pz["w"], pz["h"])]
    X0, Y0, P = g["X0"], g["Y0"], g["P"]
    cx, cy = int(X0 + P * (bx + 0.5)), int(Y0 + P * (by + 0.5))
    a = np.asarray(ds.grab("").convert("RGB")).astype(int)
    half = max(4, P // 3)
    cell = a[cy - half:cy + half + 1, cx - half:cx + half + 1].reshape(-1, 3)
    yellow = ((cell[:, 0] > 190) & (cell[:, 1] > 170) & (cell[:, 2] < 120)).sum()
    return yellow > 12


# ---------- 大盘点灯（18×10 / 24×14：确定性滚动 + tap 点灯） ----------
# ★★视口真模型（2026-10-30 cal_hold3 逐格映射实锤，推翻 10-29 深夜结论）：
#     可见 **10×10**；dc = clamp(cursor-5, 0, w-10)；dr = clamp(cursor-9, 0, h-10)。
#     旧「12 列 / cursor-11」模型全错（VCW 实为 10）——曾据此误诊「输入锁」，
#     exp_tap_v2 修正模型后 batch 0.08s/盏 15/15 零丢失，tap 路线平反。
#     归零（Up×(h+2)+Left×(w+2)，实测可靠）后记账精确（exp_dc2 对照帧验证）。
#   通关面板时序见 _clear_px 注释（等全局动画队列 ~0.3s/盏，终检前必须等面板）。

VCW = 10                                  # 视口完整可见列数（cal_hold3 实测）
VR_BY_SIZE = {(18, 10): 10, (24, 14): 10, (36, 20): 10}  # 视口完整可见行数


def _scr_walls(a, ncols=15, nrows=12):
    """读屏幕 16px 网格每格是否为墙（蓝色块）。"""
    out = []
    for r in range(nrows):
        row = ""
        for c in range(ncols):
            cx, cy = int(16 + 16 * (c + 0.5)), int(208 + 16 * (r + 0.5))
            if cy + 6 > a.shape[0]:
                row += "?"
                continue
            cell = a[cy - 5:cy + 6, cx - 5:cx + 6].reshape(-1, 3)
            blue = ((cell[:, 2] > 100) & (cell[:, 2] > cell[:, 0] + 35)).mean()
            row += "W" if blue > 0.35 else "."
        out.append(row)
    return out


def vp_score(a, pz, dc, dr, scr=None):
    """『屏幕墙图对齐全局偏移 (dc,dr)』的匹配分。返回 (m, tot)。"""
    exp = expected_walls(pz)
    w, h = pz["w"], pz["h"]
    if scr is None:
        scr = _scr_walls(a)
    m = tot = 0
    for r in range(len(scr)):
        for c in range(len(scr[0])):
            gy, gx = r + dr, c + dc
            if not (0 <= gy < h and 0 <= gx < w):
                continue
            ch = scr[r][c]
            if ch == "?":
                continue
            tot += 1
            m += (ch == exp[gy][gx])
    return m, tot


def _vp_best(a, pz, scr=None):
    """全窗搜索最佳视口偏移，返回 (ratio, dc, dr)。"""
    w, h = pz["w"], pz["h"]
    if scr is None:
        scr = _scr_walls(a)
    best = (-1.0, 0, 0)
    for dr2 in range(0, max(1, h - 9)):
        for dc2 in range(0, max(1, w - 11)):
            m2, t2 = vp_score(a, pz, dc2, dr2, scr)
            r2 = m2 / t2 if t2 else 0.0
            if r2 > best[0]:
                best = (r2, dc2, dr2)
    return best


def _scroll_to(pz, sr, sc):
    """顶死归零 → 实证映射滚到 (sr,sc) → 墙图验证，不过则补按/慢剂量重试。

    返回 True=验证到位；False=两轮未确认（映射继续，终检兜底）。
    """
    w, h = pz["w"], pz["h"]
    for att in range(2):
        wt, hd = (0.10, 0.04) if att == 0 else (0.30, 0.02)
        for _ in range(h + 2):
            ds.press("Up", wait=wt, hold=hd)
        for _ in range(w + 2):
            ds.press("Left", wait=wt, hold=hd)
        # 归零起点实测映射（Q31）：dc=clamp(cursor-5,0,w-12) ⇒ Right×(sc+5)；
        # 纵向外推（Q91 base 曲线）：dr=clamp(cursor-9,0,h-10) ⇒ Down×(sr+9)。
        # 键数上限：Right ≤ 11、Down ≤ h-1（光标出视口会触发 wrap 异常）。
        for _ in range(min(sc + 5, 11)):
            ds.press("Right", wait=wt, hold=hd)
        for _ in range(min(sr + 9, h - 1)):
            ds.press("Down", wait=wt, hold=hd)
        time.sleep(0.40)
        a = grab_np()
        scr = _scr_walls(a)
        m, tot = vp_score(a, pz, sc, sr, scr)
        if tot and m / tot >= 0.80:
            return True
        rt, bdc, bdr = _vp_best(a, pz, scr)
        if rt >= 0.80 and (bdc, bdr) != (sc, sr):
            # 增量补按（慢剂量单步）
            for _ in range(max(0, sc - bdc)):
                ds.press("Right", wait=0.30, hold=0.02)
            for _ in range(max(0, sr - bdr)):
                ds.press("Down", wait=0.30, hold=0.02)
            time.sleep(0.40)
            a = grab_np()
            m, tot = vp_score(a, pz, sc, sr)
            if tot and m / tot >= 0.80:
                return True
    print(f"    [scroll] 视口验证未过 (sc={sc} sr={sr})，按映射继续", flush=True)
    return False

def _viewport_offset(a, pz):
    """**下屏**视口 10×10 墙图案滑窗匹配 → 实测视口偏移 (dc, dr, score/100)。

    ★2026-10-30 Q32 实测：长走位方向键**间歇性被滚动动画吞掉**（0.30s/步
      也可能丢），光标记账与真实视口错位 ⇒ 全部检测/点击整体平移
      （(13,8) 窗口看到的是数字墙、tap 打在墙上无效）。走位后必须实测校验。
    ★几何：下屏视口 = (x0=16, y0=208绝对, P=16)×10×10（Q31 全程验证）；
      上屏是**全盘鸟瞰**（~11px/格 x0≈30 y0≈49），不能用于视口定位。
    墙判据（9×9 均值）：深蓝墙(34~57,98~105,148~167) = B>120 & G<140 & R<100；
      排除浅蓝照亮(G≈151~179)/暖黄/灯泡/黑格。
    """
    walls = expected_walls(pz)
    w, h = pz["w"], pz["h"]
    vw = np.zeros((10, 10), dtype=bool)
    for vr in range(10):
        for vc in range(10):
            # ★2026-10-30 Q73 几何定标（diag_geo 实测）：真格心(24+16vc,216+16vr)，
            #   数字在格心稀释蓝色 ⇒ 采 y=212（格心上方）+13×13 避数字。Q73 dc=0
            #   实测 100/100（旧 y=208/rb4 仅 76/100，dc=0/8 并列 margin=0 退化）。
            cx, cy = 24 + 16 * vc, 212 + 16 * vr
            if cy - 6 < 0 or cy + 7 > a.shape[0] or cx - 6 < 0 or cx + 7 > a.shape[1]:
                continue
            m = a[cy - 6:cy + 7, cx - 6:cx + 7].reshape(-1, 3).mean(axis=0)
            vw[vr, vc] = m[2] > 120 and m[1] < 140 and m[0] < 100
    scores = []
    for dc in range(max(w - 9, 1)):
        for dr in range(max(h - 9, 1)):
            sc = sum(1 for r in range(10) for c in range(10)
                     if (walls[dr + r][dc + c] == "W") == vw[r, c])
            scores.append((sc, dc, dr))
    scores.sort(reverse=True)
    best = scores[0]
    margin = best[0] - (scores[1][0] if len(scores) > 1 else 0)
    # margin = top1 - top2。★Q66 教训：盘面墙稀疏时匹配会退化（top1 恒 88 且
    #   补偿走位毫无响应），此时实测不可信 —— 调用方 margin<4 应改信记账。
    return best[1], best[2], best[0], margin


def vp_score_fixed(a, pz, dc, dr):
    """★2026-10-30 Q73 根因修复：固定偏移视口校验（替代 _viewport_offset 滑窗）。

    _viewport_offset / _vp_best 在稀疏墙盘面滑窗匹配退化（top1==top2，margin=0）
      → zero_cursor/goto_view 永远验证不过 → 反复归零死循环（Q73 卡死元凶）。
    本函数用 _viewport_offset 同款正确几何读 10×10 视口墙图，但**不滑窗**，
    只验证『我按 cur+滚动模型预测的偏移 (dc,dr) 是否正确』：
    正确偏移下，可见墙图与已知 puzzles 板在 (dc,dr) 处逐格一致（含空格），
    稀疏也不退化（空对空恒命中、墙对墙硬约束）。返回 (m, tot)。
    """
    walls = expected_walls(pz)
    w, h = pz["w"], pz["h"]
    vw = np.zeros((10, 10), dtype=bool)
    for vr in range(10):
        for vc in range(10):
            # ★2026-10-30 Q73 几何定标实测（diag_geo）：真格心 = (24+16vc, 216+16vr)，
            #   但数字画在格心会稀释蓝色 ⇒ 采 y=212（格心上方 4px）+ 13×13 避开数字，
            #   Q73 dc=0 实测 100/100（旧 y=208/rb4 仅 76/100 且 dc=0/8 并列退化）。
            cx, cy = 24 + 16 * vc, 212 + 16 * vr
            if cy - 6 < 0 or cy + 7 > a.shape[0] or cx - 6 < 0 or cx + 7 > a.shape[1]:
                continue
            mm = a[cy - 6:cy + 7, cx - 6:cx + 7].reshape(-1, 3).mean(axis=0)
            # ★2026-11-01 污染鲁棒（Q1 42 灯后 (0,0) 仅 68/100 的元凶）：
            #   深蓝真墙实测 B≈148~193、R≈45；而「被灯泡照亮格」B≈120、R≈89，
            #   旧阈 B>120 & R<100 把照亮格误判成墙 → 灯一多墙图崩坏 → 视口校验
            #   假失败 → 整圈重试。收紧到 B>135 & R<75：既排除照亮格(B120/R89)
            #   与灯泡(B53/R150)，又完整保留真墙(B≥148/R45)，污染下仍稳。
            vw[vr, vc] = mm[2] > 135 and mm[1] < 140 and mm[0] < 75
    m = tot = 0
    for vr in range(10):
        for vc in range(10):
            gy, gx = dr + vr, dc + vc
            if not (0 <= gy < h and 0 <= gx < w):
                continue
            tot += 1
            if (walls[gy][gx] == "W") == bool(vw[vr, vc]):
                m += 1
    return m, tot


def vp_robust(a, pz, dc, dr):
    """★2026-11-01 Q1 根因修复：**污染鲁棒**视口判据（替代 vp_score_fixed）。

    vp_score_fixed 把「被灯泡照亮格」当墙（实测照亮格 B≈120 与真墙 B≈150 同档），
    点灯越多墙图越崩 → 真视口(9,4) 100% 却被判 82/100 而假视口(9,0) 也 82/100，
    阈值 0.80 根本分不开 ⇒ 视口漂移(Up×4 全被吞)检测不到 → tap 打在墙上无效、
    永不通关，且每次校验失败都整圈归零（用户明确反对的浪费步数）。
    本函数**只统计无歧义格**：明确墙(B>135&R<75) 或 明确暗空(sum<120)；
    照亮/灯泡/动画中的格一律跳过不计分。实测污染下真视口 100% 而错视口 ≤80%，
    判别度充足。返回 (m, tot)。
    """
    wl = expected_walls(pz)
    w, h = pz["w"], pz["h"]
    m = tot = 0
    for vr in range(10):
        for vc in range(10):
            gy, gx = dr + vr, dc + vc
            if not (0 <= gy < h and 0 <= gx < w):
                continue
            cx, cy = 24 + 16 * vc, 212 + 16 * vr
            if cy - 6 < 0 or cy + 7 > a.shape[0] or cx - 6 < 0 or cx + 7 > a.shape[1]:
                continue
            mm = a[cy - 6:cy + 7, cx - 6:cx + 7].reshape(-1, 3).mean(axis=0)
            iswall = bool(mm[2] > 135 and mm[0] < 75)
            isdark = bool(mm.sum() < 120)
            if not iswall and not isdark:
                continue                      # 歧义（照亮/灯泡/动画）→ 不计分
            tot += 1
            if (wl[gy][gx] == "W") == iswall:
                m += 1
    return m, tot


def measure_vp(a, pz, dc, dr, R=4):
    """在 (dc,dr) 邻域 ±R 内找**实测**视口偏移（vp_robust 打分）。

    返回 (bdc, bdr, ratio, tot)。用于 goto_view 漂移后的**廉价微补**——
    不必整圈归零，按实测差值补几步即可。
    """
    w, h = pz["w"], pz["h"]
    best = (dc, dr, -1.0, 0)
    best_key = (-1.0, 0, 0)
    for c in range(max(0, dc - R), min(w - 10, dc + R) + 1):
        for d in range(max(0, dr - R), min(h - 10, dr + R) + 1):
            m, t = vp_robust(a, pz, c, d)
            # ★最低无歧义格数取 8（不是 20）：点灯越多，被照亮格越多（歧义→不计分），
            #   末段视口常常只剩 14~15 格无歧义。旧阈值 20 会把「14/14 = 100% 完美匹配」
            #   误判成不符 → 反复整圈归零（Q2 实测卡死在 归零未到位×3）。
            if t >= 8:
                r = m / t
                # ★2026-11-01：并列（同比率）取**无歧义格更多**者 —— 稀疏/点灯盘面
                #   常有多个偏移同分，tot 越大越可信，避免选到偶然凑上的错偏移。
                # ★★2026-11-04 Q43 修复：比率与 tot 都并列时（盘面存在重复图案，
                #   如 (0,0) 与 (9,0) 同为 71/71），取**离目标最近**者。旧规则严格
                #   大于 ⇒ 先遍历到的 (0,0) 永远胜出 ⇒ 真实视口 (9,0) 被判"不符"，
                #   goto_view 连转 8 轮 15~18s 才"信记账"，正是 Q43 慢与卡的主因。
                key = (r, t, -(abs(c - dc) + abs(d - dr)))
                if key > best_key:
                    best_key = key
                    best = (c, d, r, t)
    return best


def _has_bulb(a, bx, by, dc, dr):
    """该解灯位是否已有**真实灯泡**（亮黄(250,239,31)）。

    ★2026-10-30 Q80 实测根因（measure_q80：强制视口(0,0)后逐灯扫描质心）：
      灯泡图标绘制在单元格几何中心**下方 ~1~10px**（driftY 实测 +1/+8/+10），
      固定 9×9 在中心读对顶/底行漏检（读在图标上方黑边）→ 误判未亮 →
      tap_view 二次 tap 把已亮灯 toggle 灭（Q80 首跑 25 盏全挂根因）。
      改为读「中心偏下加高」框 [cy-3, cy+14]×[cx-8, cx+9]（覆盖图标偏移且
      不与下一行串扰：框底 cy+14 距下一格顶 cy+16 仍余 2px 间隙），按**亮黄
      像素计数**而非均值 → 图标落在框内任意位置都能命中。
      ★阈值 R>200 & G>195 & B<90 保留：灯泡 G=239、照亮暖黄 G=182 分离干净，
      杜绝把被照亮的灯位(暖黄)误判成已放灯而漏点（照亮格本就不在 bulbs 集合）。
    """
    vc, vr = bx - dc, by - dr
    cx, cy = int(16 + 16 * (vc + 0.5)), int(200 + 16 * (vr + 0.5))
    if cx + 9 > a.shape[1] or cy + 14 > a.shape[0] or vc < 0 or vr < 0:
        return True                              # 视口外无法验证 → 信任记账
    region = a[cy - 3:cy + 14, cx - 8:cx + 9].reshape(-1, 3)
    bulb = ((region[:, 0] > 200) & (region[:, 1] > 195) & (region[:, 2] < 90)).sum()
    return bulb > 15


def _cell_dark(a, bx, by, dc, dr):
    """该格是否仍为「未放灯黑格」（tap 未生效 / 需补点）。

    ★安全不变式：只对黑格 tap——黑格必无灯，tap 永远是安全放灯，从机制上
      杜绝 toggle 点灭（旧慢补盲点把已亮灯点灭的根因）。
      读与 _has_bulb 同款加高框，按非黑像素计数：亮灯(灯泡/照亮)格有大量非黑
      像素，未放灯黑格仅细网格线（阈值 >50 计入，需 <25 像素才算仍黑）。
    """
    vc, vr = bx - dc, by - dr
    cx, cy = int(16 + 16 * (vc + 0.5)), int(200 + 16 * (vr + 0.5))
    if cx + 9 > a.shape[1] or cy + 14 > a.shape[0] or vc < 0 or vr < 0:
        return False                             # 视口外无法验证 → 信任记账
    region = a[cy - 3:cy + 14, cx - 8:cx + 9].reshape(-1, 3)
    nonblack = ((region[:, 0] > 50) | (region[:, 1] > 50) | (region[:, 2] > 50)).sum()
    return nonblack < 25


def _bulb_present(a, bx, by, dc, dr):
    """兼容名：该解灯位是否已有灯泡（照亮≠灯泡，照亮格仍需 tap 放灯）。"""
    return _has_bulb(a, bx, by, dc, dr)


def light_big(pz):
    """大盘点灯终版 v2：**触屏直点 batch + 记账滚动**（2026-10-30）。

    ★★ v1/v1.1 的「输入锁」结论被推翻（用户真机实测直点无锁 + exp_tap_v2
      复核）：旧 tap 测试全部基于错误视口模型（VCW=12），点击坐标系统性
      错位被误诊为吞键。修正模型 + 记账归零后 exp_tap_v2 实测：
      单点 ✅ / batch 0.2s/盏 15/15 / batch 0.08s/盏 15/15 —— 零丢失。

    v2 算法：
      1. 归零光标（慢剂量 0.30s/步，零丢键已验证）→ 视口 dc=dr=0 记账确定；
      2. 滑动窗口遍历全部视口（步长 9 重叠 1 列/行）：
         18×10 → dc∈{0,8}；24×14 → dc∈{0,9,14}, dr∈{0,4}；
      3. 每视口：像素检查未亮灯 → tap_batch 连点（gap0.02/hold0.06 ≈0.08s/盏）
         → 逐灯确认 → 未亮者慢速补点（hold0.10/after0.30）×2 轮；
      4. 光标记账全程不动（tap 不改变光标/视口，exp_tap_v2 边缘灯全亮实证），
         无任何屏幕测量依赖。
    """
    w, h = pz["w"], pz["h"]
    t0 = time.time()
    n_tap = 0

    _burst = {"k": None, "n": 0}

    def step(key):
        # ★0.55s/步：0.30s 偶发被滚动动画吞键（Q32 实测记账 dc=8 vs 实测 dc=5）。
        # ★2026-10-31 实测：muzusaki 大盘上 9 连右按**确定性**丢键（dc=9 恒 84/100、
        #   dc=14 恒 72/100 → 每次 2 次整圈重试 64s，视频里还绕圈）。加长等待到 0.70
        #   无效 ⇒ 不是单步太快，而是**连续同向滚动**累积丢键。改"突发式"：每连按 4 步
        #   小憩 0.30s 打断连续滚动，实测吞键率应显著下降 → 减少/消除整圈重试。
        if _burst["k"] == key:
            _burst["n"] += 1
        else:
            _burst["k"] = key
            _burst["n"] = 1
        # ★2026-11-03 再提速（用户：剂量还不够快）：单键 0.50→0.34s；小憩 4→3 步、
        #   0.18→0.12s（更密更短地打断连续同向滚动，既提速又保不吞键）。goto_view 的
        #   实测校验环兜底漂移（微补几步即可），故单键可再压。
        ds.press(key, wait=0.30, hold=0.02)
        if _burst["n"] % 3 == 0:
            time.sleep(0.10)

    def tap_view(dc, dr, slow_retry=False):
        """点本视口 (dc,dr) 内**归属**于它的灯各一次。返回仍未亮的列表。

        ★2026-11-01 Q2 根因：旧版从 cur 记账反推 dc,dr，而 cur 在 goto_view 兜底
          （6 轮都不符、信记账）时并不等于 (dc+5,dr+5) ⇒ tap_view 用错视口做
          canon 过滤 → 该视口的灯被整片跳过（53 盏只 tap 44 盏，差 9 盏）。
          改为**显式传入**调度循环已校验过的 (dc,dr)，与 goto_view 的实测校验严格同源。
        """
        nonlocal n_tap
        a = grab_np()
        if _clear_px(a) > CLEAR_THR:
            return "CLEAR"                    # 面板已弹出：盲扫必误判全灭
        # （dc,dr 现由调度循环显式传入，与 goto_view 的 vp_robust 实测校验同源；
        #   不再从 cur 记账反推 —— 见本函数 docstring 的 Q2 根因说明。）
        mfix, tfix = vp_robust(a, pz, dc, dr)
        if tfix >= 8 and mfix / tfix < 0.80:
            print(f"    [tap] 警告: 视口({dc},{dr})稳健匹配仅 {mfix}/{tfix}，"
                  f"可能错位（仍按调度视口继续）", flush=True)
        pts, cells = [], []
        for (bx, by) in pz["bulbs"]:
            vc, vr = bx - dc, by - dr
            if not (0 <= vc < 10 and 0 <= vr < 10):
                continue
            # ★2026-11-01 Q2 根因：只 tap **归属本视口**的灯（canon），且已放过的跳过。
            if canon.get((bx, by), (dc, dr)) != (dc, dr):
                continue
            if (bx, by) in done:
                continue
            # ★不再按 _bulb_present 跳过（2026-11-01 Q2 实测根因）：
            #   被照亮格与真实灯泡像素几乎同色（照亮格 bulbpx 达 78~98，真灯泡 89），
            #   该判据会把「被照亮但尚未放灯」的格误判成已放 → **漏点**
            #   （Q2 共 53 盏却只 tap 了 44 盏，差 9 盏 → 永不通关）。
            #   改为：每盏灯在其归属视口**只 tap 一次**（done 保证），
            #   从机制上既杜绝漏点、也杜绝重复 tap 导致的 toggle 点灭。
            pts.append((int(16 + 16 * (vc + 0.5)), int(8 + 16 * (vr + 0.5))))
            cells.append((bx, by))
        if pts:
            if slow_retry:
                # ★2026-10-30 Q32 两次实测根因修复：
                #   ① tap 后仅等 0.25s 复查撞上放灯动画(~0.3s/盏) → 误判未亮
                #     → 再 tap 同格 = 放置又移除 ⇒ (13,8)/(16,2) 每轮恒定失败；
                #   ② 旧判据把被照亮白格判成灯泡 ⇒ 解灯位被照亮后永久跳过补点。
                #   新闭环：双帧确认无灯泡才 tap（防检测边缘误差 toggle）+
                #   tap 后等 0.65s 复查；若已脱离黑但暂未见灯泡则交终检复核，
                #   绝不盲发第二 tap（只对黑格二 tap，保「tap 必放灯」不变式）。
                # ★2026-11-01 Q1 (10,2) 根因重写：旧版对「被照亮但无灯」的格
                #   (_cell_dark=False) 在 tap 一次后即 break 交终检 → 终检再 tap 同格
                #   = toggle 点灭（tap=43 恒 >42 灯、恒差 (10,2) 不过关）。且 tap 后
                #   仅 0.55s 判 bulb、动画未落定即误判未亮。
                #   新闭环：**每次 tap 前**先判 bulb（已亮则绝不 tap）；
                #   tap 后等足 0.9s（放灯动画 ~0.3-0.8s）再回环重判；
                #   彻底删掉「非黑即放弃」分支 —— 被照亮格也要点、也要验到真灯泡为止。
                for (x, y), (bx, by) in zip(pts, cells):
                    lit = False
                    for _t in range(4):
                        a2 = grab_np()
                        if _clear_px(a2) > CLEAR_THR:
                            return "CLEAR"
                        if _bulb_present(a2, bx, by, dc, dr):
                            lit = True
                            break
                        # ★双帧确认（间隔 0.3s）确实没有灯泡才 tap —— 防单次假阴性
                        #   把已放好的灯 toggle 点灭（灭掉后格仍被照亮 ⇒ 更难发现）。
                        time.sleep(0.30)
                        a2b = grab_np()
                        if _clear_px(a2b) > CLEAR_THR:
                            return "CLEAR"
                        if _bulb_present(a2b, bx, by, dc, dr):
                            lit = True
                            break
                        ds.tap(x, y, hold=0.11, after=0.0)
                        n_tap += 1
                        time.sleep(0.90)
                    if not lit:
                        a_d = grab_np()
                        if _bulb_present(a_d, bx, by, dc, dr):
                            lit = True
                        else:
                            vc_d, vr_d = bx - dc, by - dr
                            cx_d, cy_d = int(16 + 16 * (vc_d + 0.5)), int(200 + 16 * (vr_d + 0.5))
                            cell_d = a_d[cy_d - 3:cy_d + 14, cx_d - 8:cx_d + 9].reshape(-1, 3).mean(axis=0)
                            print(f"    [DIAG slow] ({bx},{by}) pts=({x},{y}) dc,dr=({dc},{dr}) "
                                  f"cellmean={[round(float(v), 1) for v in cell_d]} "
                                  f"hasbulb={_has_bulb(a_d, bx, by, dc, dr)} "
                                  f"dark={_cell_dark(a_d, bx, by, dc, dr)}", flush=True)
            else:
                # ★2026-11-01 Q1 (10,2) 丢键修复：旧 gap=0.02/hold=0.06/after=0 连发
                #   过快（~80ms/点），与放灯队列(~0.3s/盏)抢道 → 偶发整点丢失（42 灯
                #   只落 41）。放慢到 ~0.30s/点（≈动画节拍）令每次触摸都被受理。
                # ★2026-11-01 提速：batch 0.15/0.10/0.05 → 0.12/0.09/0.04（仍留安全余量，防丢点）。
                ds.tap_batch(pts, gap=0.10, hold=0.07, after=0.03)
                n_tap += len(pts)
            # ★放灯动画在游戏内排队（每盏~0.3s），batch 后必须等队列消化完，
            #   否则 grab 误判未亮 → 慢补把已亮灯点熄（v2 首跑 17 盏未亮的根因）
            # ★2026-11-01 Q2 实测：0.8+0.25N 略短于队列真实耗时，紧接着就按方向键
            #   ⇒ 一次 5 连 Right 被吞掉 4 个（实测目标(14,0) 实际停在(10,0)，差 4 列）
            #   → tap 打偏到相邻格（stray 灯）→ 盘面被污染、永不通关。
            #   放灯动画 ~0.3s/盏，给足 0.35N + 1.2s 余量，确保队列排空后再走位。
            # ★2026-11-03 提速（用户：点完愣了好一会才移动）：固定排队等待 0.9+0.28N
            #   （≈2.9s/视口）改为**轮询等放灯队列排空**。放灯动画 ~0.3s/盏流水线处理，
            #   边放边等：发送耗时已让前几盏落定，末尾几盏只差 ~0.3s ⇒ 实际仅 ~0.3N，
            #   比固定值每视口短 ~1~2.5s。上限 0.5+0.36N 兜底（严格覆盖 0.3N，防丢键空等）。
            #   ⚠慢补分支已逐盏确认放好，poll 立即 break（无额外代价）。
            if pts:
                deadline = time.time() + 0.5 + 0.36 * len(pts)
                while time.time() < deadline:
                    a = grab_np()
                    if _clear_px(a) > CLEAR_THR:
                        return "CLEAR"        # 本批点亮最后一盏 → 面板已弹出
                    if all(_bulb_present(a, bx, by, dc, dr) for (bx, by) in cells):
                        break
                    time.sleep(0.10)
            a = grab_np()
            if _clear_px(a) > CLEAR_THR:
                return "CLEAR"
            for (bx, by) in cells:            # ★已 tap 过一次即封存，杜绝后续重复 tap
                done.add((bx, by))
        return [(bx, by) for (bx, by) in cells
                if not _bulb_present(a, bx, by, dc, dr)]

    # ---- 归零（见下方 zero_cursor()：盲按 + 实测校验 + 补按）----

    # ---- 滑动窗口遍历视口（步长 9，重叠 1）----
    dcs = list(range(0, max(w - 10, 0) + 1, 9))
    if dcs[-1] != w - 10:
        dcs.append(w - 10)
    drs = list(range(0, max(h - 10, 0) + 1, 9))
    if drs[-1] != h - 10:
        drs.append(h - 10)

    # ★2026-11-01 Q2 根因修复：**视口重叠 → 同一盏灯被两个视口各 tap 一次**。
    #   dcs=[0,9,14] 让 col9 同时落在 vp(0,*) 与 vp(9,*)；drs=[0,4] 让 row4-9 同理重叠。
    #   实测 Q2 只有 53 盏灯却 tap=88 → 35 盏被重复 tap = 放置又移除；移除后该格
    #   仍被邻灯照亮 ⇒ _has_bulb 假阳性 ⇒ 输出「全部确认」却永不通关。
    #   给每盏灯指定**唯一归属视口**（覆盖它的最大 dc/dr），只在该视口 tap；
    #   done 集合再兜一层：已确认放过的灯，任何后续视口/pass 都绝不再碰。
    def _canon(bx, by):
        c = max([d for d in dcs if d <= bx] or [0])
        r = max([d for d in drs if d <= by] or [0])
        return (c, r)

    canon = {tuple(b): _canon(*b) for b in pz["bulbs"]}   # bulbs 元素是 list，须转 tuple
    done = set()

    miss_all = set()

    cur = [0, 0]

    def zero_cursor():
        """归零视口到 (0,0)（位置无关，2026-10-30 Q73 根因修复）。

        ★旧归零 Up×(h+2)+Left×(w+2) 在「reset 后光标在棋盘 (0,0) 但视口停在
          (8,0)（光标在视口左界外）」时彻底失效：光标已在棋盘左/上界 → Left/Up
          根本不滚动视口 → 视口卡 (8,0)；叠加稀疏墙盘面 _viewport_offset 测量
          退化（margin=0），goto_view 按误测盲目补 Left 空转 → 永不通关。
        ★新逻辑「推到右下角再推回左上角」：先 Right(w)/Down(h) 把光标推入视口并
          把视口滚到最大 dc/dr，再 Left(w)/Up(h) —— 无论光标起点在哪，Left(w)
          必把光标推到棋盘 col0 并沿途把视口滚到 dc=0，Up(h) 同理归零 dr。
          位置无关，吞键可重试（≤3 轮，每轮复验）。
        """
        for attempt in range(3):
            for _ in range(w):
                ds.press("Right", wait=0.35, hold=0.02)
            for _ in range(h):
                ds.press("Down", wait=0.35, hold=0.02)
            for _ in range(w):
                ds.press("Left", wait=0.35, hold=0.02)
                for _ in range(h):
                    ds.press("Up", wait=0.35, hold=0.02)
                time.sleep(0.6)
                m0, t0 = vp_robust(grab_np(), pz, 0, 0)
            if t0 >= 8 and m0 / t0 >= 0.92:
                cur[0] = 0
                cur[1] = 0
                return True
            print(f"    [nav] 归零未到位(轮{attempt}): 稳健(0,0) {m0}/{t0} → 重推",
                  flush=True)
        m0, t0 = vp_robust(grab_np(), pz, 0, 0)
        cur[0] = 0
        cur[1] = 0
        if t0 >= 8 and m0 / t0 >= 0.92:
            return True
        print(f"    [nav] 归零最终未收敛(固定偏移 {m0}/{t0}) → 信记账(0,0)", flush=True)
        return False

    # ---- 归零（带实测校验，记账起点）----
    # ★★2026-10-31 提速（用户硬要求：不要浪费题面滚动步数，废除整圈滚动）：
    #   进关 reset 后视口通常已在 (0,0)，原 zero_cursor 整圈 76 次(~32s) 纯浪费，
    #   改为"廉价钉角" Left×10+Up×10（视口不动、无绕圈，多余键在边界 no-op）。
    #   ★★2026-11-04 再提速（用户硬要求：砍掉"光按光标、不点灯不滚动"的开场段）：
    #     实测进关/リトライ 后游戏**总把光标复位到 (0,0)**（bbox 恒 = 14,206,120px，
    #     Right×3+Down×2 后精确平移 (48,32) 已证），故连 20 次钉角也全是空按。
    #     改为**直读光标格位**，只按必要的 cx+cy 次（正常 0 次）；读不到光标
    #     （被过场遮挡等）回退钉角，视口不在 (0,0) 时回退整圈 zero_cursor。
    #     注意：原先这些按键客观上充当了入场 START 过场的等待（实测动画在 reset
    #     返回后 1.35s 结束，期间帧差分 ~1.6e6、之后恒 0）；按键砍掉后必须显式等，
    #     否则首屏点灯会被过场吞掉。play_one 已 sleep 0.3，此处补 1.15。
    #     ★实测反例（v8, 2026-11-04）：**只砍钉角**时 light_big=42s 有效；若连
    #     首视口的"居中(5,5)"一起砍（省 10 次按键），则后续每步起点都偏，去 (0,4)
    #     多走 5 步并连带 3 次 5~11s 重锚 ⇒ 反而退到 51s。故**居中必须保留**：
    #     它是后续滚动的锚点前置，不是空按。
    time.sleep(1.15)
    _m0, _t0 = vp_robust(grab_np(), pz, 0, 0)
    if _t0 >= 8 and _m0 / _t0 >= 0.92:
        _cc = _cursor_cell(grab_np())
        if _cc is not None:
            _cx, _cy = _cc
            for _ in range(_cx):
                ds.press("Left", wait=0.12, hold=0.02)
            for _ in range(_cy):
                ds.press("Up", wait=0.12, hold=0.02)
            if _cx or _cy:
                time.sleep(0.12)
            cur[0] = 0
            cur[1] = 0
            print(f"    [nav] 视口已在(0,0) ({_m0}/{_t0}) + 光标实测({_cx},{_cy})"
                  f" → 仅按 {_cx + _cy} 次归零（原固定 20 次）", flush=True)
        else:
            for _ in range(10):
                ds.press("Left", wait=0.12, hold=0.02)
            for _ in range(10):
                ds.press("Up", wait=0.12, hold=0.02)
            time.sleep(0.12)
            cur[0] = 0
            cur[1] = 0
            print(f"    [nav] 视口已在(0,0) ({_m0}/{_t0}) → 光标未辨，回退钉角",
                  flush=True)
    else:
        zero_cursor()

    def goto_view(dc, dr):
        """走到目标视口并**实测闭环校验**（墙图案滑窗匹配）。

        ★2026-10-30 Q80 根因修复：长走位方向键被滚动动画吞键 → 视口静态差 1-2 格，
          边缘灯泡（如 (16,8) 在 dc=8 视口 vc=8 末列）因 vc 超界被跳过、或打偏到
          相邻墙格，永不通关。原 3 轮补偿上限太低（高吞键率时补不够），且
          attempt==2 即 break 提前放弃。
          改为**实测差值闭环**：每轮读实测→按(目标-实测)补按方向键→重读实测，
          最多 14 轮直到实测==目标；补偿步数基于实测差值（非记账），归零重走
          无效（Q66 教训）已规避。tap_view 同步用实测偏移，双保险。
        """
        # ★2026-11-01 diag6 定标（**强制归零后**逐键曲线，唯一可信测量）：
        #   光标滚动锚点两轴均为 **5**（视口 10 格、光标居中：左/上各留 5 格）：
        #   Right×1..5→dc0、×6→dc1、×7→dc2…×12→dc7。故目标光标 = (dc+5, dr+5)，
        #   与 tap_view 的 dc=cur[0]-5 严格互逆。
        #   ★此前按 diag2/diag4 改成 7 是**错的**：那两次测量光标未归零（残留
        #     reset 后位置），把"光标起点偏移"误读成了锚点 → 目标光标系统性多走
        #     2 格 → 实测视口偏 2 格 → 固定偏移校验 65/100 → 反复整圈重试。
        """
        ★★2026-11-01 重写（Q1 实测定标，三个根因一次性修掉）：
        ① **换轴前必须等滚动动画落定**：Right×9 之后紧接着的 Up×4 会被**整段吞掉**
           （实测视口停在 dr=4 而非 dr=0）→ tap 全打在墙上无效、永不通关。
           故横向走完后 sleep 1.0s 再走纵向。
        ② **校验改用 vp_robust**（只统计无歧义格）：点灯后真视口 100% 而错视口 ≤80%，
           判别充足；旧 vp_score_fixed 真/假同为 82/100 → 阈值 0.80 真假都过 →
           漂移检测不到。
        ③ **不符时按实测差值微补几步**（廉价），不再整圈归零 —— 用户硬要求
           「不要浪费题面滚动步数 / 不要光标绕全场滚一整圈」。仅当邻域也测不准
           （r<0.92）才回退 zero_cursor（极罕见）。
        """
        # ★★2026-11-01 Q1 录制实测定标（干净盘 robust(14,4)=97/97 可达；锚点=5；
        #   Right×19→dc14 且 ×20/21 仍是 14 ⇒ 到边同向键幂等）。
        #   失败根因：点灯后**方向键被动画吞**，旧微补用「cur 记账 + 实测差值」相对
        #   驱动；上一视口把 cur 推到 21，本轮 attempt0 的 `while cur!=tx` 会朝**反方向**
        #   按 Left 把真实光标推离（dc14→dc12），随后补 Right 又被吞 → 6 轮原地空转。
        #   重写：①**每轮用实测偏移把 cur 重新锚定**（实测 bc ⇒ 光标≈bc+5），彻底
        #   消除陈旧记账；②只朝目标方向绝对驱动，绝不反向退键；③目标在边界
        #   (dc∈{0,w-10} / dr∈{0,h-10}) 时**多按 3 下同向键**——到边后是 no-op，
        #   幂等保证贴边；④末轮取实测最优邻域，确保不漏。
        tx, ty = min(dc + 5, w - 1), min(dr + 5, h - 1)

        def _drive_h(target):
            # ★2026-11-03 分段驱动：长连按(>5)段间让滚动动画落定(0.20s)。实测边界视口的
            #   1~2 格漂移是"确定性测量偏差"（改分段/静置均无法消除，见 v5/v6/v7 对照），
            #   故用较粗分段（少加静止），重试交校验环兜底。
            while cur[0] != target:
                n = target - cur[0]
                seg = 5 if abs(n) > 5 else abs(n)
                for _ in range(seg):
                    step("Right" if n > 0 else "Left")
                    cur[0] += 1 if n > 0 else -1
                if cur[0] != target:
                    time.sleep(0.20)

        def _drive_v(target):
            while cur[1] != target:
                n = target - cur[1]
                seg = 4 if abs(n) > 4 else abs(n)
                for _ in range(seg):
                    step("Down" if n > 0 else "Up")
                    cur[1] += 1 if n > 0 else -1
                if cur[1] != target:
                    time.sleep(0.20)

        def _edge_pin():
            """贴边幂等：目标在边界时多按几下同向键（到边即 no-op），保证到边界。"""
            hpin = 0
            if dc <= 0:
                hpin = -2
            elif dc >= w - 10:
                hpin = 2
            for _ in range(abs(hpin)):
                step("Right" if hpin > 0 else "Left")
            vpin = 0
            if dr <= 0:
                vpin = -2
            elif dr >= h - 10:
                vpin = 2
            for _ in range(abs(vpin)):
                step("Down" if vpin > 0 else "Up")

        # ★2026-11-03：tap_view 的 poll 已确保放灯队列排空，起始静置可短（0.10s）。
        # ★★2026-11-04 Q33/Q43 根因重写（"全部确认却不通关" + 导航空转）：
        #   旧版首轮用「视口分数 >= 92% 就当已到位、一次方向键都不按」的 fast-path。
        #   但该分数只统计"明确墙/明确空格"，盘面点亮越多这类格越少（Q43 末段
        #   只剩 23 个），而盘面常有重复图案 ⇒ **错视口也拿满分**：
        #     · Q33：视口仍在 (0,0)，判据 (0,4) 却给 58/59 = 98%；
        #     · Q43：视口仍在 (0,4)，判据 (9,4) 给 23/23（(0,4) 自己也是 23/23，
        #       并列无法区分，改"取离目标最近"又会把这两个 case 判反）。
        #   一旦误判到位 ⇒ 整轮灯打在错视口的格子上；tap_view 的复查用同一套
        #   错映射，自洽地报"全部确认 (tap=50/58)"，游戏却判未通关 ⇒ 无限重试
        #   到超时（Q33/Q43 各废 7~14 分钟）。
        #   现在改为**先驱动、后校验**：tap 之后已用 _cursor_cell 把光标实测值
        #   回写 cur，记账可信 ⇒ 按记账驱动到目标（真已在位则不按键、零开销），
        #   再抓帧校验。分数从此只用于"确认到位"，不再用于"跳过驱动"⇒ 误判
        #   从机制上消失，且不必依赖任何并列规则。
        time.sleep(0.10)
        a = grab_np()
        mv, tv = 0, 0
        for attempt in range(9):
            if attempt == 0:
                # 首轮：cur 已由上一次 tap 后的光标实测回写 ⇒ 直接增量驱动到目标
                _drive_h(tx); time.sleep(0.30)     # 换轴前等横向滚动落定
                _drive_v(ty); _edge_pin()
            else:
                # 后续：按**实测**偏移重锚 cur，只朝目标方向补（全盘搜索：
                #   视口可能一次偏到 9 格之外，±4 邻域看不到真实位置会误判）。
                bc, bd, r, _tt = measure_vp(a, pz, dc, dr, R=max(w, h))
                if (bc, bd) == (dc, dr) and r >= 0.92:
                    cur[0] = tx; cur[1] = ty
                    print(f"    [nav] ({dc},{dr}) 第{attempt}轮到位 {mv}/{tv}", flush=True)
                    return True
                if r < 0.60:
                    print(f"    [nav] ({dc},{dr}) 邻域测不准({r:.0%}) → 归零重驱动", flush=True)
                    zero_cursor(); cur[0] = 0; cur[1] = 0
                    _drive_h(tx); time.sleep(0.35); _drive_v(ty); _edge_pin()
                    time.sleep(0.30)
                    a = grab_np()
                    mv, tv = vp_robust(a, pz, dc, dr)
                    continue
                print(f"    [nav] 视口不符(轮{attempt}): 目标({dc},{dr}) 稳健 {mv}/{tv} "
                      f"实测({bc},{bd}) {r:.0%} → 重锚微补", flush=True)
                # ★把 cur 重锚到实测真值（不再累积错误记账）
                cur[0] = min(max(bc + 5, 0), w - 1)
                cur[1] = min(max(bd + 5, 0), h - 1)
                _drive_h(tx); time.sleep(0.35)
                _drive_v(ty); _edge_pin()
            time.sleep(0.26)                       # 滚动动画稳定后再抓帧判定
            a = grab_np()
            mv, tv = vp_robust(a, pz, dc, dr)
            if tv >= 8 and mv / tv >= 0.92:
                cur[0] = tx; cur[1] = ty
                if attempt:
                    print(f"    [nav] ({dc},{dr}) 第{attempt}轮到位 {mv}/{tv}", flush=True)
                else:
                    print(f"    [nav] ({dc},{dr}) 首轮驱动即到位 {mv}/{tv}", flush=True)
                return True
        print(f"    [nav] 视口校验未收敛(稳健 {mv}/{tv}) → 信记账({dc},{dr})", flush=True)
        return True

    # ★2026-11-02（用户硬要求：减少光标冗余步数）蛇形遍历视口：列主序 dr 0↔4 反复
    #   反向（纵向步数虚高），改为第偶数列正序、奇数列逆序 ⇒ 列间只换列不再上下回跳。
    vp_order = []
    for i, dc in enumerate(dcs):
        vp_order += [(dc, dr) for dr in (drs if i % 2 == 0 else reversed(drs))]
    tot_nav = tot_tap = 0.0
    for (dc, dr) in vp_order:
        _tn = time.time()
        _okv = goto_view(dc, dr)
        _navt = time.time() - _tn
        if not _okv:
            print("  [light_big] 视口校验连续失败", flush=True)
            return list(pz["bulbs"])  # 全部按未亮上报，交上层重试
        _tt = time.time()
        miss = tap_view(dc, dr)
        _tapt = time.time() - _tt
        tot_nav += _navt
        tot_tap += _tapt
        # ★★2026-11-04 Q43 根因修复（"全部确认却不通关"的真正来源）：
        #   **触摸点灯会把方向键光标带到被点的那一格**（实测点 (2,0) 后
        #   _cursor_cell=(2,0)，点 (6,10) 后光标即在该格）。而 goto_view 的
        #   增量驱动完全基于 cur 记账（假设光标停在视口中心 dc+5,dr+5）——
        #   tap 之后这个假设必然失真，于是下一个视口从错误起点驱动，视口偏
        #   1~9 格；轻则靠重锚救回（每次 2~8s），重则误判"已到位"根本不滚动
        #   → 整轮灯打在错位置、复查自洽报"全部确认"、游戏判未通关、
        #   无限重试到超时（Q33/Q43 各废 7~14 分钟）。
        #   此刻 (dc,dr) 刚被 goto_view 校验过 ⇒ 读到的光标是**真值**，
        #   直接回写 cur，让下一个视口从正确起点出发。成本：一次抓帧(~50ms)。
        _cc2 = _cursor_cell(grab_np())
        if _cc2 is not None:
            cur[0] = min(dc + _cc2[0], w - 1)
            cur[1] = min(dr + _cc2[1], h - 1)
        print(f"    [vp] ({dc},{dr}) nav={_navt:.1f}s tap={_tapt:.1f}s "
              f"(累计 nav={tot_nav:.0f}s tap={tot_tap:.0f}s)", flush=True)
        if miss == "CLEAR":
            print(f"  [light_big] 通关面板出现，提前收工 (tap={n_tap} "
                  f"{time.time() - t0:.0f}s)", flush=True)
            return None
        if miss:
            print(f"    [tap] 视口({dc},{dr}) 快批未亮 {miss} → 慢补", flush=True)
            miss = tap_view(dc, dr, slow_retry=True)
            if miss == "CLEAR":
                print(f"  [light_big] 通关面板出现（慢补中），提前收工 "
                      f"(tap={n_tap} {time.time() - t0:.0f}s)", flush=True)
                return None
            miss_all.update(miss)
        else:
            miss_all.difference_update()  # no-op, 保持语义清晰
    # ---- 等通关面板（★2026-10-30 连拍实测根因修复）----
    # 面板要等**全局**点灯动画队列排干（~0.3s/盏）才弹出（Q31 26盏=快批后~6.4s）。
    # 不等就终检 ⇒ 面板遮盘被误判全灭 → 慢补把面板点掉回选关页（三次假失败根因）。
    # 仅在全视口都确认点亮（miss_all 空）时等待，窗口按全局队列 0.35s/盏 + 余量。
    if not miss_all and wait_clear(min(25.0, 3.0 + 0.35 * len(pz["bulbs"]))):
        print(f"  [light_big] 通关面板确认，提前收工 (tap={n_tap} "
              f"{time.time() - t0:.0f}s)", flush=True)
        return None
    # ---- 终检：重扫全部视口 ----
    final_miss = set()
    for (dc, dr) in vp_order:
        # ★2026-11-04 Q87 根因修复：终检再遍历前先查通关面板。
        #   主遍历若因轮询时序把某盏灯误报「未亮」(miss_all 非空)，会进入本终检环；
        #   此时板面其实已全亮/已解，vp_robust 在「全亮板」上测不出无歧义格(返回0/0)，
        #   goto_view 随后在 zero_cursor 里反复重推永不收敛(每视口~237s) → 总时长拖爆超时。
        #   板一旦真解出，游戏会自动弹通关面板(与 wait_clear 无关)，故先查面板：
        #   已弹则直接收工(板在游戏内已解)，彻底绕开「全亮板测不准→自旋」死路。
        _fa = grab_np()
        if _clear_px(_fa) > CLEAR_THR:
            print(f"  [light_big] 终检发现通关面板，收工 (tap={n_tap} "
                  f"{time.time() - t0:.0f}s)", flush=True)
            return None
        if not goto_view(dc, dr):
            print("  [light_big] 终检视口校验失败", flush=True)
            return list(pz["bulbs"])
        r = tap_view(dc, dr, slow_retry=True)
        if r == "CLEAR":
            print(f"  [light_big] 通关面板出现，终检收工 (tap={n_tap} "
                  f"{time.time() - t0:.0f}s)", flush=True)
            return None
        final_miss.update(r)
    if final_miss:
        for (bx, by) in sorted(final_miss):
            dc2 = min(max(bx - 5, 0), w - 10); dr2 = min(max(by - 5, 0), h - 10)
            vc, vr = bx - dc2, by - dr2
            tx = int(16 + 16 * (vc + 0.5)); ty = int(16 + 16 * (vr + 0.5))
            a = np.asarray(ds.grab("").convert("RGB")).astype(int)
            cy = int(200 + 16 * (vr + 0.5)); cx = int(16 + 16 * (vc + 0.5))
            cell = a[cy - 3:cy + 14, cx - 8:cx + 9].reshape(-1, 3).mean(axis=0)
            print(f"    [DIAG] bulb({bx},{by}) dc,dr=({dc2},{dr2}) pts=({tx},{ty}) "
                  f"cellmean={[round(float(v),1) for v in cell]} "
                  f"hasbulb={_has_bulb(a,bx,by,dc2,dr2)} dark={_cell_dark(a,bx,by,dc2,dr2)}",
                  flush=True)
        print(f"  [light_big] 未确认灯 {sorted(final_miss)} (tap={n_tap} "
              f"{time.time() - t0:.0f}s)", flush=True)
    else:
        print(f"  [light_big] 全部确认 (tap={n_tap} {time.time() - t0:.0f}s)",
              flush=True)
    return sorted(final_miss) or None

CLEAR_THR = 3000


def _clear_px(a):
    """ndarray 帧下屏深蓝面板像素数（(49,82,123)±14，seg2 同判据）。

    ★2026-10-30 连拍实测（Q31 26 盏）：panel 在快批后 ~6.4s 才弹出
      （等全局点灯动画队列排干 ~0.3s/盏），弹出后稳定 5789~5888 > 3000；
      盘面/选关/标题/选项页实测 0~50。
    """
    seg = a[190:384, :, :].reshape(-1, 3)
    return int(((np.abs(seg[:, 0] - 49) < 14) & (np.abs(seg[:, 1] - 82) < 14)
                & (np.abs(seg[:, 2] - 123) < 14)).sum())


def is_clear_panel(im=None):
    if im is None:
        im = ds.grab("")
    a = (np.asarray(im.convert("RGB")).astype(int)
         if not isinstance(im, np.ndarray) else im)
    return _clear_px(a) > CLEAR_THR


def has_start_overlay(im=None):
    if im is None:
        im = ds.grab("")
    a = np.asarray(im.convert("RGB")).astype(int)
    seg = a[192:300, 0:200].reshape(-1, 3)
    orange = ((seg[:, 0] > 200) & (seg[:, 1] > 110) & (seg[:, 1] < 215)
              & (seg[:, 2] < 95)).sum()
    return orange > 800


def wait_select_page(timeout=12.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        im = ds.grab("")
        a = np.asarray(im.convert("RGB")).astype(int)
        if in_select_page(a):
            return True
        ds.press("x", wait=0.8)
    return False


def in_play_page(im=None):
    """盘面页判据：右侧菜单「解答確定」红粉块。

    ★2026-10-29 标定：盘面页该区红粉像素 ~522，预览页/选关页/选项页全为 0。
      用途：A 键被吞卡在预览页时的安全判据 —— 只在「非盘面页」才允许补按 A
      （在盘面页按 A 会 toggle 光标格，制造冲突灯）。
    """
    if im is None:
        im = grab_np()
    a = np.asarray(im.convert("RGB")).astype(int) if not isinstance(im, np.ndarray) else im
    seg = a[328:352, 198:256]
    red = ((seg[:, :, 0] > 120) & (seg[:, :, 0] - seg[:, :, 1] > 40)
           & (seg[:, :, 0] - seg[:, :, 2] > 30)).sum()
    return int(red) > 200


def board_yellow_count():
    """盘面区黄像素总数（>80 = 有残留灯/冲突，需要リトライ复位）。

    ★2026-10-29 修：START 覆盖层橙字 (R>200,G110-215) 与灯泡黄 (255,246,32)
      在旧判据下重叠，覆盖层淡出尾段会误报「残留」。现要求 G>225 严格黄
      （实测灯泡亮黄 G=246，覆盖层橙字 G<215），并等覆盖层彻底消失后复核。
    ★2026-10-29 晚：阈值 300→80，确保单野灯（yellow≈224）也能被捕获，
      避免残留漏检导致「黄检查只查亮没亮不查冲突」而永远未通关。
    """
    a = grab_np()
    sub = a[208:384, 8:196]
    R, G, B = sub[:, :, 0], sub[:, :, 1], sub[:, :, 2]
    return int(((R > 190) & (G > 225) & (B < 120)).sum())


def option_menu_open(im=None):
    """OPTION 菜单判据：右上「問題選択へ」蓝按钮（实测菜单上 963 / 其他页 ~0）。"""
    if im is None:
        im = grab_np()
    a = np.asarray(im.convert("RGB")).astype(int) if not isinstance(im, np.ndarray) else im
    seg = a[212:232, 160:252]
    return int(((seg[:, :, 2] > 120) & (seg[:, :, 2] > seg[:, :, 0] + 30)).sum()) > 400


def retry_dialog_open(im=None):
    """リトライ确认框判据：中下橙色大框（实测框上 883 / 菜单上 ~0）。"""
    if im is None:
        im = grab_np()
    a = np.asarray(im.convert("RGB")).astype(int) if not isinstance(im, np.ndarray) else im
    seg = a[235:335, 25:235]
    R, G, B = seg[:, :, 0], seg[:, :, 1], seg[:, :, 2]
    return int(((R > 190) & (G > 100) & (G < 220) & (B < 110)).sum()) > 500


def reset_level(max_try=3):
    """Start → リトライ(115,371) → はい(60,322) → 干净盘面 + 计时归零。

    ★2026-10-29 实测两坑：
      1. 游戏**按关记忆盘面**（中途退出重进不复位），残留冲突灯必致未通关；
      2. 盲发三连击会在菜单未弹出时把 tap 打进 OPTION 菜单（后续点灯全落空）。
    故每一步都带判据校验 + 重试。
    """
    for _ in range(max_try):
        ds.press("Return", wait=1.5)
        for _ in range(3):                    # 键被吞兜底
            if option_menu_open():
                break
            ds.press("Return", wait=1.5)
        ds.tap_local(115, 371, after=1.2)     # リトライ
        for _ in range(3):
            if retry_dialog_open():
                break
            ds.tap_local(115, 371, after=1.2)
        ds.tap_local(60, 322, after=1.8)      # はい（最初からプレイしますか？）
        for _ in range(4):
            if in_play_page():
                return True
            time.sleep(0.5)
    return in_play_page()


def wait_clear(timeout=12.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if is_clear_panel(ds.grab("")):
            return True
        time.sleep(0.35)
    return False


def escape_to_select():
    """Start 菜单 → 問題選択へ → はい → 回选关页。

    ★2026-10-28 修：已在选关页时**直接返回**（否则末尾的 x 会把选中关进关，
      实测 Q31 测试时因此连坐两次假失败）。菜单可能被吞键 ⇒ 最多试 4 轮。
    """
    for _ in range(4):
        if in_select_page():
            return True
        ds.press("Return", wait=1.5)
        ds.tap_local(197, 215, after=1.2)
        ds.press("x", wait=1.5)
    return wait_select_page(12.0)


def play_one(n, pz):
    if GEO.get((pz["w"], pz["h"])) is None:
        print(f"  [Q{n}] 尺寸 {pz['w']}x{pz['h']} 几何未标定，停止", flush=True)
        return False
    if not goto_level(n):
        print(f"  [Q{n}] goto 失败", flush=True)
        return False
    # 等盘面画出并校验是否目标关
    # ★2026-10-29 修：进关 A 键被吞会**卡在预览页**（底屏是关卡网格，
    #   被当盘面读出 m=56，重试多久都没用）⇒ 每 3 轮检查失败且不在盘面页
    #   时补按一次 A；在盘面页绝不按 A（会 toggle 光标格制造冲突灯）。
    big = GEO[(pz["w"], pz["h"])].get("big")
    # ★ 进关确认：goto_level 的首次 A 偶发被吞会卡在「预览页」（底屏是关卡网格而非盘面），
    #   此时 in_play_page 恒为 False；显式轮询「解答確定」红块、最长 10 次补按 A 直到真正进入盘面。
    #   （一旦在盘面页 in_play_page 为 True 立即停手，绝不在盘面页乱按 A 制造冲突灯。）
    for _ in range(10):
        if in_play_page():
            break
        ds.press("x", wait=1.5)
    thr = int(0.95 * pz["w"] * pz["h"]) if not big else int(0.95 * VIS_W * VIS_H)
    m = real = 0
    ok_board = False
    n_a = 0
    for i in range(18):
        im = ds.grab("")
        if big:
            ok_board = is_target_board(im, pz)
            m = 100 if ok_board else 0
            real = n if ok_board else -1
        else:
            m, real = detect_level(im, pz)
            ok_board = m >= thr
        if ok_board:
            break
        # 兜底：万一又退回预览页，每次都尝试补按 A（上限提高到 8）
        if not in_play_page(im) and n_a < 8:
            ds.press("x", wait=1.2)
            n_a += 1
    if m < 95:
        print(f"  [Q{n}] 盘面不可信 (m={m})", flush=True)
        return False
    if real != n:
        print(f"  [Q{n}] 进错关：实际是第 {real} 关", flush=True)
        return False
    for _ in range(10):
        if not has_start_overlay(im):
            break
        time.sleep(0.6)
        im = ds.grab("")
    # ★2026-10-29 修：复玩（重录）场景进关即显示**上次的完整解答**（27 灯全亮），
    #   START 覆盖层变暗使 board_yellow_count 低至 201→阈值 80 判据失效 → 不复位
    #   → light_big 在残留盘面上把已亮灯 toggle 熄灭（Q31 miss 恒 16/27 实锤）。
    #   重录全部为复玩 ⇒ 进关**无条件复位**，确保干净起点（成本 ~5s/关）。
    print(f"  [Q{n}] 进关复位 (yellow={board_yellow_count()})", flush=True)
    reset_level()
    # ★2026-11-03 提速：复位后 1.0→0.3s（此段计入过关计时）。
    time.sleep(0.3)
    # 逐盏点灯 + 校验
    dose = DOSE_BY_SIZE[(pz["w"], pz["h"])]
    big = GEO[(pz["w"], pz["h"])].get("big")

    def light_small():
        coords = [(int(GEO[(pz["w"], pz["h"])]["X0"] + 16 * (bx + 0.5)),
                   int(GEO[(pz["w"], pz["h"])]["Y0"] + 16 * (by + 0.5) - 192))
                  for (bx, by) in pz["bulbs"]]
        miss = []
        for i, (bx, by) in enumerate(pz["bulbs"]):
            # ★逐灯闭环：每灯最多 4 次 tap，每次 tap 后等 0.35s 点亮动画落定再校验，
            #   消除「(8,4) 偶发点不亮」类时序误判（校验过早 / tap 被吞兜底）。
            #   进关前先 _lit_at 校验，避免对已亮灯重复 tap 触发 toggle 熄灭。
            lit = False
            for _ in range(4):
                if _lit_at(bx, by, pz):
                    lit = True
                    break
                ds.tap(coords[i][0], coords[i][1],
                       hold=dose["hold"], after=0.08)
                time.sleep(0.35)
                if _lit_at(bx, by, pz):
                    lit = True
                    break
            if not lit:
                miss.append((bx, by))
        if miss:
            print(f"  [Q{n}] 仍有未亮灯 {miss}", flush=True)
        return miss or None

    def light_all():
        time.sleep(6.5)                       # 触摸解禁
        if big:
            return light_big(pz)
        return light_small()

    err = light_all()
    if err:
        print(f"  [Q{n}] 点灯异常 {err}", flush=True)
    time.sleep(0.6)
    cleared = wait_clear(12.0)
    if not cleared:
        # ★2026-10-29 新增：失败恢复 —— リトライ复位后完整重点（最多 2 轮）
        for rec in range(2):
            print(f"  [Q{n}] 未通关，リトライ复位重点 {rec + 1}/2", flush=True)
            reset_level()
            time.sleep(1.5)
            err = light_all()
            if err:
                print(f"  [Q{n}] 重点后仍有异常 {err}", flush=True)
                continue
            if wait_clear(12.0):
                cleared = True
                break
    if not cleared:
        print(f"  [Q{n}] 未通关", flush=True)
        return False
    # ★2026-10-30 根因修复（Q71 卡重试 4 次 FAIL 的元凶）：
    #   通关深蓝面板弹出后，按 x 实测只在「已解盘面页 ↔ 过渡屏」间打转，
    #   永远到不了选关页（实测 x 按 16 次仍是 play=True）→ play_one 误判 False
    #   → 编排器 4 次重试后 FAIL 停摆。正确回选关页路径是 escape_to_select
    #   （Return → 問題選択へ → はい）。故先 x 消通关面板，再 escape_to_select，
    #   最多 3 轮兜底（键偶发被吞时自动补）。
    time.sleep(1.5)
    ds.press("x", wait=1.0)                       # 消深蓝通关面板 → 已解盘面页
    for _ in range(3):
        if in_select_page(grab_np()):
            return True
        escape_to_select()
        time.sleep(0.6)
    return in_select_page(grab_np())


def main():
    raw_args = sys.argv[1:]
    do_tut = "--tutorial" in raw_args
    args = [a for a in raw_args if a != "--tutorial"]
    lo = int(args[0]) if len(args) >= 1 else 1
    hi = int(args[1]) if len(args) >= 2 else N_TOTAL
    seq = _SEQ
    if do_tut:
        # 录 muzusaki 前先打过入門 L1，抑制后续教程弹窗（详见 tutorial_prep 注释）
        print("[rec] 教程前置：先打入門 L1 ...", flush=True)
        tutorial_prep()
    if not in_select_page():
        # ★2026-10-30 修：旧版直接 return 1 ⇒ 编排器后续 chunk 全部空跑
        #   （C/D/E1/E2 无哨兵跳抓取）。改为先拉回选关页，拉不回才放弃。
        print("不在选关页 → escape_to_select 拉回", flush=True)
        try:
            escape_to_select()
        except Exception:
            pass
        if not in_select_page():
            print("仍不在选关页", flush=True)
            return 1
    # ★ yasashii：确保处于「やさしい」选关网格态（B→难度一览→点やさしい→x）
    if not goto_difficulty("やさしい"):
        print("!! 切换やさしい失败", flush=True)
        return 1
    try:
        open(SENTINEL, "w").close()
    except OSError:
        pass
    print(f"[rec] START @ select ({DIFF} Q{lo}-Q{hi}, tutorial={'Y' if do_tut else 'N'})", flush=True)
    time.sleep(0.8)
    ok_n = 0
    for n in range(lo, hi + 1):
        pz = seq[n - 1]
        ok = play_one(n, pz)
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
