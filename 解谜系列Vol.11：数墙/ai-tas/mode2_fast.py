#!/usr/bin/env python3
"""mode2(やさしい) 执行器 v1 —— 纯执行 puzzles.json 已知 wall 答案（零求解）。

几何（2026-10-23 实测标定，10x10 盘面全视口）：
  格心（下屏 NDS 局部坐标）= (24 + 16*c, 24 + 16*r)，pitch 16
  网格线在 16+16k（k=0..10），盘面占据局部 (16,16)-(176,176)
  线索数字 = 灰度 <130 的深色笔画；涂黑的墙格 ≈ (49,49,49)

计时模型（复刻入門定标，mode2 实测一致）：
  A 键进关 → 输入锁 ~4.5s（期间点击全被吞）→ 计时起点 ~8.8s
  → 4.6s 起连涂 → 54~65 格 × 0.07s ≈ 3.8~4.6s → 8.4~9.2s 涂完
  → 自动判定通关 → クリアタイム ≈ 4s

满星规则（用户确认）：难度 n 满星 = n+2 → やさしい(n=2) 满 4★。
70ms/格 连涂 → TIME 4s → 4★ = 满星，无需更快；xdotool 再快必丢击。

铁律：
  1. 墙格每格只点一次（重复点会 toggle 回白 —— 实测 gap<0.3s 的二次点击即清格）
  2. 校验只补「纯白」格（mean>200）；动画中的灰格不碰，避免 toggle 打转
  3. 不预扫、不碰非墙格
  4. 关卡记录只保留最好成绩 → 重复刷安全

用法: python3 mode2_fast.py <lo> <hi> [outdir]
"""
import json
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas")
import numpy as np
from PIL import Image

import ds
from state2 import detect as _detect

REPO = "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙"
# 难度参数化（2026-10-24）：V11_DIFF 环境变量切换难度，默认 やさしい 保持旧行为
DIFF = os.environ.get("V11_DIFF", "やさしい")
_OUT_BY_DIFF = {"入門": "mode1_tutorial", "やさしい": "mode2_easy",
                "ふつう": "mode3_medium", "むずかしい": "mode4_hard"}
MAX_BY_DIFF = {"入門": 3, "やさしい": 4, "ふつう": 5, "むずかしい": 6}  # 满星 = n+2
OUT = f"{REPO}/validation/{_OUT_BY_DIFF[DIFF]}"
PUZ = json.load(open(f"{REPO}/validation/puzzles.json"))[DIFF]

X0, Y0, P = 24, 24, 16          # 格心几何（NDS 下屏局部坐标）
UNLOCK = 4.6                    # 输入锁结束（A 后秒）
TAP = dict(gap=0.02, hold=0.04, after=0.01)   # ~0.07s/格
# 18×10 专用（2026-10-25 三轮剂量网格 30 档实测标定，lvl81 段a 55 格）：
#   两条硬约束 —— ① hold ≥ 0.055（按下时长不够不算一次涂格）
#                ② hold+after ≥ 0.08（松开后需静默期让游戏结算完这次点击）
#   实测 hold=0.04 无论 after 多大都不行（0.04+0.04 → 60%）；hold 加长也补不上 after 不足
#   （hold0.07+after0.005 → 80%，hold0.07+after0.01 → 95%）。
#   gap 0.04 → 0.02 完全无损（旧档 gap 是纯冗余，白扔 20% 时间）。
#   0.02/0.06/0.015 = 0.095s/格，整关实测 TIME 17s→13s 且 4★ 不掉。
TAP_WIDE = dict(gap=0.02, hold=0.06, after=0.015)   # 18×10 专用 ~0.095s/格
# 24×14 及以上（fill_huge）。2026-10-25 重标定：**旧「新剂量在 24×14 丢击 15%」结论作废**
# —— 那次用的是 18×10 的 hold=0.06。24×14 的 hold 底线更高：
#   ① hold ≥ 0.07（0.065 → 86~88%，0.07 → 95~96%）
#   ② gap  ≥ 0.02（0.015 → 84~86%，0.01 → 68%）
#   ③ after ≥ 0.02（0.01 → 82~88%）
#   0.02/0.07/0.02 = 0.11s/格，命中 95~96%（旧档 0.12/0.06/0.02 仅 93~95%）→ 更快且更准。
TAP_HUGE = dict(gap=0.02, hold=0.07, after=0.02)   # 24×14+ 专用 ~0.11s/格
# 36×20 专用（2026-10-25 lvl43 段(0,0) 52 格网格标定；2026-10-27 lvl41 全关复测）。
# 24×14 的剂量在这里**完全失效**：
#   0.11s/格 → 60%  0.12s/格(旧档) → 60~65%  0.13s/格 → 88%  0.14s/格 → 98%
# 剂量底线随盘面增大而抬高（静默期 hold+after：18×10 ≥0.08 / 24×14 ≥0.09 / 36×20 ≥0.10）
# —— 大盘渲染负载高，触摸采样跟不上，必须给更长的结算静默期。
#
# 2026-10-27 复测（lvl41 真实关卡 398 墙，limiter ON，每档 2~5 次，按 fill 桥钟实测）：
#   0.140  g.04 /h.07 /a.03   → 100% ×5   fill 均值 96.5s   （旧定案）
#   0.135  g.03 /h.07 /a.035  → 100% ×3   fill 均值 92.3s   （现定案，快 4.2s/关）
#   0.135  g.035/h.07 /a.03   → 100% ×3*  fill 92.8s        （*曾偶发一次 277.6s）
#   0.130  g.03 /h.07 /a.03   → 91%（漏 36）fill 250.5s
#   0.130  g.04 /h.07 /a.02   → 91%（漏 35）fill 228.3s
#   0.120  g.02 /h.07 /a.03   → 62%（漏 153）fill 302.9s
# ★ 硬边界在 0.130~0.135s 之间。低于边界不是"慢一点"，而是漏 9% 靠补点救回，
#   fill 反而涨 2.5 倍（补点 + 沉降重试才是真瓶颈，剂量本身不是）。
# ★ 真正的分界线是**静默期**：hold+after 0.100 余量薄（偶发掉帧即落进重试，慢 3 倍），
#   0.105 则稳定拿到 100%。故 gap 让位给 after，而不是反过来。
# ★ 0.15s/格 与 0.14s 同为 98~100%，属白扔时间；0.135s 是当前可稳定复现的最快档。
TAP_MEGA = dict(gap=0.03, hold=0.07, after=0.035)   # 36×20 专用 ~0.135s/格
VERIFY_TAP = dict(gap=0.06, hold=0.05, after=0.20)  # 补点慢速 0.31s/格
VERIFY_WIDE = dict(gap=0.06, hold=0.06, after=0.22)  # 18×10 补点/修复 0.34s/格(hold≥0.06)
# 24×14+ 每段点完的沉降。实测 0.4s 与 1.2s 命中率无差别（补点/读盘都发生在段后，
# 只要不早于最后一格的结算），但 0.4s×6 段比 1.2s×6 段省 4.8s。补点后仍用 1.2s。
SETTLE_HUGE = 0.45

# 上屏红框几何（play_level 按盘宽设定；默认 = 18×10 档）
# 统一模型（2026-10-25 标定）：小地图每格 7px，红框 84×84 = 视口 10 + 两侧各 1 列边距
#   box_left = 盘左线 - 14 + 7·oc ；box_top = 盘顶线 - 14 + 7·or
#   24×14: 盘左线 x=47（居中留边）→ x_left = 33 + 7·oc，y_top = 41 + 7·or；oc_max=14, or_max=4
#   36×20: 盘左线 x=8（横贯全屏）→ x_left = -6 + 7·oc，y_top = 29 + 7·or；oc_max=26, or_max=10
#     ★ oc=0 时框左缘(x=-6)/or=0 时框顶缘(y=29) 出屏/出扫描窗被裁 → rect_oc/rect_or 需双边求解
_RECT_X0, _RECT_SX = 13, 11.0
_RECT_Y0, _RECT_SY = 41, 7.0
_RECT_W36 = False          # 36 宽盘：红框边缘会被屏边裁掉，读数走双边分支


def state():
    return _detect(ds.grab(None))


def poll(want, timeout=8.0, iv=0.12):
    t0 = time.time()
    st = state()
    while time.time() - t0 < timeout:
        if st in want:
            return st
        time.sleep(iv)
        st = state()
    return st


def cell_nds(r, c):
    return (X0 + P * c, Y0 + P * r)


def walls_of(idx):
    p = PUZ[idx]
    return [(r, c) for r in range(p["h"]) for c in range(p["w"]) if p["wall"][r * p["w"] + c]]


def safe_mouseup():
    subprocess.run(["xdotool", "mouseup", "1"], env=ds.ENV)


# ---------- 盘面读取 ----------
def board_gray():
    return np.asarray(ds.grab(None).convert("L"), dtype=float)[192:]


def cell_state(g, r, c):
    """'B' 黑(已涂) / 'W' 纯白 / 'A' 动画中灰。"""
    cx, cy = X0 + P * c, Y0 + P * r
    m = g[cy - 6:cy + 6, cx - 6:cx + 6].mean()
    if m < 130:
        return "B"
    if m > 200:
        return "W"
    return "A"


def white_misses(g, walls):
    return [w for w in walls if cell_state(g, *w) == "W"]


def clue_match(idx, vis_cols=10, vis_rows=10):
    """进关后校验：视口线索布局 vs puzzles.json[idx]。返回匹配度 (ok, total)。
    行列都截到视口可见 10 —— 24×14 盘面 r>=10 的格子在屏幕外，不可参校。"""
    p = PUZ[idx]
    w = min(p["w"], vis_cols)
    hr = min(p["h"], vis_rows)
    clue = [[p["clue"][r * p["w"] + c] for c in range(w)] for r in range(hr)]
    g = board_gray()
    ok = tot = 0
    for r in range(hr):
        for c in range(w):
            cx, cy = X0 + P * c, Y0 + P * r
            has = (g[cy - 6:cy + 6, cx - 6:cx + 6] < 130).sum() > 10
            ok += has == (clue[r][c] > 0)
            tot += 1
    return ok, tot


# ---------- 填充 ----------
def burst_fill(idx, skip=None):
    """连涂全部墙格一次；skip=探针格（wait_unlocked 已涂黑，排除避免 toggle）。
    返回是否已自动通关（快路径不校验）。"""
    walls = [w for w in walls_of(idx) if w != skip]
    ds.tap_batch([cell_nds(r, c) for r, c in walls], **TAP)
    safe_mouseup()
    return wait_clear(2.0)          # 快路径：无丢击则游戏自动判定通关


# 18×10 与 10×10 用同一套 16px 视口几何（2026-10-23 干净盘面实测 100/100 确认）。
# 视口固定 10 列，18 宽盘面需横滚：oc ∈ [0, 8]。
def clue_match_at(idx, oc, vis_cols=10):
    """校验视口偏移 oc 时的线索布局（仅对未涂区域有效）。"""
    p = PUZ[idx]
    g = board_gray()
    ok = tot = 0
    for r in range(p["h"]):
        for vc in range(vis_cols):
            c = oc + vc
            if c >= p["w"]:
                break
            cx, cy = X0 + P * vc, Y0 + P * r
            has = (g[cy - 5:cy + 6, cx - 5:cx + 6] < 130).sum() > 12
            ok += has == (p["clue"][r * p["w"] + c] > 0)
            tot += 1
    return ok, tot


def w_best_offset(idx):
    """扫 oc 取线索匹配最高者。"""
    best, bestv = 0, -1
    for oc in range(0, max(0, PUZ[idx]["w"] - 10) + 1):
        ok, _ = clue_match_at(idx, oc)
        if ok > bestv:
            bestv, best = ok, oc
    return best, bestv


def w_scroll_to(idx, target):
    """滚到目标偏移（每键 1 列），带匹配度校正；仅用于未涂盘面。"""
    for _ in range(14):
        oc, sc = w_best_offset(idx)
        if oc == target and sc >= 90:
            return True
        if oc < target:
            ds.press("Right", wait=0.26, hold=0.05)
        elif oc > target:
            ds.press("Left", wait=0.26, hold=0.05)
        else:
            ds.press("Left", wait=0.26, hold=0.05)
            ds.press("Right", wait=0.26, hold=0.05)
        time.sleep(0.35)
    oc, sc = w_best_offset(idx)
    print(f"  [wscroll] want {target} got {oc} ({sc})", flush=True)
    return oc == target


def home_wide(idx=None):
    """18×10 归位 oc=0。"""
    if idx is None:
        for _ in range(12):
            ds.press("Left", wait=0.22, hold=0.05)
        time.sleep(0.5)
        return True
    return w_scroll_to(idx, 0)


def best_offset(idx):
    """按「已涂黑格 vs 墙格」图案反解视口偏移（全盘已按答案涂时最可靠）。"""
    p = PUZ[idx]
    g = board_gray()
    best, bestv = 0, -1
    for oc in range(0, max(0, p["w"] - 10) + 1):
        sc = 0
        for r in range(p["h"]):
            for vc in range(10):
                c = oc + vc
                if c >= p["w"]:
                    continue
                want = p["wall"][r * p["w"] + c] == 1
                sc += (cell_state(g, r, vc) == "B") == want
        if sc > bestv:
            bestv, best = sc, oc
    return best, bestv


def rect_oc():
    """读上屏红色取景框反解视口偏移 oc（与盘面状态无关，最可靠）。

    几何见文件头统一模型。36 宽盘（_RECT_W36）特殊：
      框左缘 x=7·oc-6（oc=0 时 x=-6 出屏被裁），右缘 x=7·oc+78（oc=26 时 x=260 出屏）
      → 中间 oc 两条边都在：取左边线；只剩一条线时按位置判定是左缘还是右缘。
      实测锚点：oc=0 单线 x=78（右缘）；oc=8 双线 (50,134)；oc=26 单线 x=176（左缘）。
    """
    a = np.asarray(ds.grab(None).convert("RGB")).astype(int)
    R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    red = (R > 190) & (G < 110) & (B < 110)
    red[:40, :] = False
    red[170:, :] = False
    cc = red.sum(axis=0)
    xs = [x for x in range(256) if cc[x] > 60]
    if not xs:
        return None
    if _RECT_W36:
        if len(xs) >= 2:
            return int(round((xs[0] + 6) / 7.0))          # 左边线
        x = xs[0]
        if x <= 120:
            return int(round((x - 78) / 7.0))             # 右边线（oc 小端）
        return int(round((x + 6) / 7.0))                  # 左边线（右缘出屏，oc 大端）
    return int(round((min(xs) - _RECT_X0) / _RECT_SX))


def rect_or():
    """读上屏红框 y 反解纵向偏移 or（仅 h>10 的盘面有意义）。

    36 宽盘：顶缘 y=7·or+29（or=0 时 y=29 < 扫描窗 40 被裁），底缘 y=7·or+113
    （or≥9 时 y>170 被裁）→ 双边求解，单线按位置判定。
    """
    a = np.asarray(ds.grab(None).convert("RGB")).astype(int)
    R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    red = (R > 190) & (G < 110) & (B < 110)
    red[:40, :] = False
    red[170:, :] = False
    rr = red.sum(axis=1)
    ys = [y for y in range(40, 170) if rr[y] > 60]
    if not ys:
        return None
    if _RECT_W36:
        if len(ys) >= 2:
            return int(round((ys[0] - 29) / 7.0))         # 顶边线
        y = ys[0]
        if y >= 113:
            return int(round((y - 113) / 7.0))            # 底边线（or 小端）
        return int(round((y - 29) / 7.0))                 # 顶边线（底缘出窗，or 大端）
    return int(round((min(ys) - _RECT_Y0) / _RECT_SY))


def scroll_to_oc_rect(target, max_press=26):
    """用 D-pad 把视口滚到目标 oc（红框校验）。触屏点击不会滚屏，只有方向键会。"""
    for _ in range(max_press):
        oc = rect_oc()
        if oc == target:
            return True
        if oc is None:
            break
        if oc < target:
            ds.press("Right", wait=0.24, hold=0.05)
        else:
            ds.press("Left", wait=0.24, hold=0.05)
    oc = rect_oc()
    print(f"  [rectscroll] want {target} got {oc}", flush=True)
    return oc == target


# チェック左侧滚动条上的黄色 ▶（下屏局部坐标）。
# ★ 正确用法是「按住不放」连续滚动(~0.03s/列)，单点只滚 1 列。
# （滚动条上无 ◀——顶/底黄条是滑块端帽；向左滚回落 D-pad Left。）
ARROW_R = (187, 95)


def hold_scroll(target, per_col=0.055, init=0.10):
    """按住黄▶**不放**，连续滚动到 target（2026-10-24 实测定案）。

    按住期间游戏连续滚动，松开即停 —— 这才是「闪现到右半边」的正确操作，
    不是连点。实测速率 ~0.03s/列：
        按住 0.2s → oc 0→6
        按住 0.4s → oc 0→8（18×10 最右视口，即一次按住直达）
    对比三种滚动（oc 0→8）：
        D-pad 连按      ~3.2s
        黄▶ 单点连击     ~1.3s   (0.16s/列，本文件上一版)
        黄▶ 按住        ~0.4s   ← 最快，且大盘面省得更多（越往后越明显）

    ★ 按住的终点恒为「最右视口」(w-10)，不会越过上限，故 fill 段 b
      （target = 最右）按住即到位，不存在过冲风险。
    ★ 向左滚回落 D-pad（滚动条上无 ◀，顶/底黄条只是滑块端帽）。
    """
    for _ in range(3):
        oc = rect_oc()
        if oc is None:
            return False
        if oc == target:
            return True
        if oc > target:                      # 需要左滚 → 无黄箭头，回落 D-pad
            return scroll_to_oc_rect(target)
        hold = init + (target - oc) * per_col
        sx, sy = ds.WIN_X + ARROW_R[0], ds.WIN_Y + 192 + ARROW_R[1]
        ds.ensure_window()
        subprocess.run(["xdotool", "mousemove", str(sx), str(sy),
                        "mousedown", "1", "sleep", str(hold), "mouseup", "1"],
                       env=ds.ENV)
        time.sleep(0.25)
        if rect_oc() == target:
            return True
    print(f"  [holdscroll] want {target} got {rect_oc()} -> dpad 补", flush=True)
    return scroll_to_oc_rect(target)


# ---------- 大盘面快速滚屏（2026-10-25 lvl1 24×14 实测标定） ----------
# 旧 goto_pos 靠 _blind 盲按：左滚要 9+oc_max+3 = 26 次连按（~4.7s/次），
# 纵向也要 9+or_max+3 次。实测**按住方向键不放可以连续滚**：
#     hold Left 1.5s  → oc 14→0（~0.10s/列，含启动 ~0.16s）
#     hold Down 1.2s  → or 0→4（钳位，多按无害）
# 右滚用黄▶按住：oc ≈ (t - 0.05) / 0.0325（0.20s→5、0.30s→8、0.40s→11、0.50s→14）
# 24×14 单关 goto 总耗时 21.9s → 7.3s（−66%）。
def _hold_key(key, sec):
    ds.ensure_window()
    subprocess.run(["xdotool", "keydown", key, "sleep", f"{sec:.3f}", "keyup", key],
                   env=ds.ENV)
    time.sleep(0.18)


def _hold_arrow_r(sec):
    sx, sy = ds.WIN_X + ARROW_R[0], ds.WIN_Y + 192 + ARROW_R[1]
    ds.ensure_window()
    subprocess.run(["xdotool", "mousemove", str(sx), str(sy),
                    "mousedown", "1", "sleep", f"{sec:.3f}", "mouseup", "1"], env=ds.ENV)
    time.sleep(0.18)


def goto_pos_fast(idx, tor, toc):
    """同 goto_pos，但全部用「按住连续滚」+ 精确时长，自带过冲回修。

    前提：调用方已按盘宽设好 _RECT_X0/_RECT_SX（play_level 负责）。
    """
    for _ in range(4):
        oc = rect_oc()
        if oc is None:
            time.sleep(0.35); continue
        if oc > toc:                                    # 左滚（无触屏控件，只能 D-pad）
            if _RECT_W36:
                # 36 宽：光标先走 ~9 列行程(~1.1s)才推边，预留足量（钳位保底）
                _hold_key("Left", 1.2 + (oc - toc) * 0.13)
            else:
                _hold_key("Left", min(1.8, 0.16 + (oc - toc) * 0.13))
            oc2 = rect_oc()
            if oc2 is None or oc2 > toc:
                continue
        if oc < toc:                                    # 右滚（按住黄▶）
            if _RECT_W36:
                _hold_arrow_r(0.04 + (toc - oc) * 0.0375)   # 36宽实测 0.3s=8列
            else:
                _hold_arrow_r(min(1.0, 0.06 + (toc - oc) * 0.0325))
            oc2 = rect_oc()
            if oc2 is not None and oc2 > toc:           # 过冲一列 → 左滚微调
                _hold_key("Left", 0.16 + (oc2 - toc) * 0.13)
        o = rect_or()
        if o is None:
            time.sleep(0.35); continue
        if o != tor:
            if _RECT_W36:
                # 36 宽纵向：光标行程 ~1.1s + 推边 0.22s/行（or 0→10 实测 4.5s）
                _hold_key("Down" if o < tor else "Up", 1.15 + abs(tor - o) * 0.22)
            else:
                _hold_key("Down" if o < tor else "Up", 0.9 + abs(tor - o) * 0.10)
        if rect_oc() == toc and rect_or() == tor:
            return True
    print(f"  [goto_fast] want ({tor},{toc}) got oc={rect_oc()} or={rect_or()}", flush=True)
    return False


def fill_wide(idx, skip=None):
    """18×10 两段连涂：先 oc=0 涂 c0-9，再按住黄▶闪现到 oc=8 涂 c10-17。

    关键实测（2026-10-23 插桩 + 2026-10-25 三轮剂量网格 30 档重标定）：
      - 触屏点击**不会**触发滚屏，连涂期间视口零漂移（rect_oc 前后一致）
      - 坐标零错位（非墙误涂恒为 0）——旧结论「连涂中途错位」是误判
      - 真根因 = **18×10 盘面要求 hold ≥0.055s** 才识别一次涂格：
        旧记「hold=0.04 丢 30~50%」实测复现（0.04+0.01 仅 38~47%），
        但真因不是「周期」而是**两条独立约束**：
          ① hold ≥ 0.055      按下时长不够 → 不算一次涂格（大 after 补不回）
          ② hold+after ≥ 0.08 松开后需静默期 → 游戏结算完才认这次点击
        （hold0.07+after0.005 → 80%，hold0.07+after0.01 → 95%）
        → TAP_WIDE = 0.02/0.06/0.015 = 0.095s/格，整关 TIME 17s→13s，4★ 不掉
      - 拖动连涂实测仅 34% 命中 → 排除拖动方案
      - 段间滚动必须校验 rect_oc==target 才涂（滚动失败还盲涂 = 涂错列 → 误涂+toggle 乱）
      - 每段涂完原地补漏（同视口 W 墙格重点），把事后巡检压力降到最低
      - ★ 补点后必须沉降 ~1.2s：补点点击的 toggle 未结算就滚屏 → 该格仍算未涂
        → 游戏记为改答案（曾误判为掉星，2026-10-25）
    """
    walls = walls_of(idx)
    a = [(r, c) for r, c in walls if c < 10 and (r, c) != skip]
    b = [(r, c) for r, c in walls if c >= 10]
    for oc, seg in ((0, a), (8, b)):
        if not hold_scroll(oc):
            print(f"  [fill_wide] scroll oc{oc} FAIL -> 跳过该段", flush=True)
            continue
        ds.tap_batch([cell_nds(r, c) if oc == 0 else (24 + 16 * (c - 8), 24 + 16 * r)
                      for r, c in seg], **TAP_WIDE)
        safe_mouseup()
        time.sleep(1.2)                      # 涂批沉降,避免动画灰被误读
        g = board_gray()
        miss = [(r, c) for (r, c) in seg if cell_state(g, r, c - oc) == "W"]
        if miss:
            print(f"  [fill_wide] oc{oc} topup={len(miss)}", flush=True)
            ds.tap_batch([(24 + 16 * (c - oc), 24 + 16 * r) for r, c in miss],
                         **VERIFY_WIDE)
            safe_mouseup()
            time.sleep(1.2)      # ★ 补点后必须沉降：toggle 未结算就滚屏 → 该格仍算未涂
    # 判定动画期间红框会消失(rect_oc=None),给足 4s 让通关横幅出现,
    # 避免多绕一轮 verify(实测判定约在末次点击后 2~4s)
    return wait_clear(4.0)


def verify_wide(idx):
    """18×10 修复巡检（2026-10-23 重写,toggle 安全）：

    每轮对 oc=0 / oc=8 两个视口各扫一遍:
      墙白 → 点黑;  非墙黑 → 点白   （两种修复都是朝答案方向的 toggle）
    黑墙/白非墙绝不碰 → 无论盘面多乱都单调收敛,不会越修越乱。

    定位用 rect_oc()（读上屏红色取景框,与盘面涂色状态无关）。
    旧版用 best_offset(按已涂图案反解视口)在脏盘上会猜错视口 →
    在错误列上补点 → 制造非墙误涂 + 「卡死 N 格补不上」（实测根源）。
    """
    p = PUZ[idx]
    walls = {(r, c) for r in range(p["h"]) for c in range(p["w"])
             if p["wall"][r * p["w"] + c]}
    for k in range(4):
        if state() == "clear":
            return True
        time.sleep(0.9)
        fixed = 0
        for target_oc in (8, 0):         # 先查 8（fill 结束就在 8,干净关零滚动）
            if not hold_scroll(target_oc):
                print(f"  [vwide k{k}] scroll oc{target_oc} FAIL", flush=True)
                continue
            g = board_gray()
            pts = []
            for r in range(p["h"]):
                for vc in range(10):
                    c = target_oc + vc
                    if c >= p["w"]:
                        continue
                    wall = (r, c) in walls
                    stt = cell_state(g, r, vc)
                    if (wall and stt == "W") or (not wall and stt == "B"):
                        pts.append((24 + 16 * vc, 24 + 16 * r))
            if pts:
                print(f"  [vwide k{k}] oc{target_oc} fix={len(pts)}", flush=True)
                ds.tap_batch(pts, **VERIFY_WIDE)
                safe_mouseup()
                fixed += len(pts)
        if fixed == 0:
            return wait_clear(6.0)
    return wait_clear(5.0)


# ---------- 24×14 大盘面（视口 10×10，横 hold_scroll + 纵 D-pad 双向滚动） ----------
def _chunks(n, view=10):
    """把 [0,n) 切成 ≤view 的连续填充分区 [(s,e)]。"""
    out, s = [], 0
    while s < n:
        out.append((s, min(n, s + view)))
        s += view
    return out


def _offset_for(s, e, n, view=10):
    """覆盖分区 [s,e) 的视口偏移：∈[e-view, s]∩[0, n-view]，取最小（省得左滚）。"""
    return min(s, max(0, n - view))


def cell_nds_at(r, c, orr, oc):
    """全局格 (r,c) 在视口偏移 (or,oc) 下的下屏局部坐标。"""
    return (24 + 16 * (c - oc), 24 + 16 * (r - orr))


def _blind(key, n, wait=0.13):
    """盲按 n 次（光标推边机制下，多余按键被视口钳位吞掉，无害）。"""
    for _ in range(n):
        ds.press(key, wait=wait, hold=0.05)


def goto_pos(idx, tor, toc):
    """把视口滚到 (or, oc)。

    2026-10-24 lvl71 实测（24×14）：
      - D-pad 滚屏是「光标推边」机制：按键先移光标，顶到视口边缘才推视口
        （Down×5 光标走 5 行视口不动，第 6 次起视口才滚，or 到 4 后钳位不再动）
      - 触屏黄▶按住可右滚任意距离（单点会跳 1~2 列，不可靠）
      - 左滚没有触屏控件，只能 D-pad；oc>toc 的中间目标也只有钳位一条路
    因此只走可靠路径：
      横向: oc>toc → 盲按 Left 钳位到 0（光标绕行最坏 9+9+oc_max 按全覆盖）
             oc<toc → hold_scroll 直接右滚（自带红框校验，失败可重试）
      纵向: 盲按 Up/Down 钳位到 0 / or_max（tor 只允许这两个锚点）
    """
    p = PUZ[idx]
    or_max = max(0, p["h"] - 10)
    oc_max = max(0, p["w"] - 10)
    for _ in range(4):
        oc = rect_oc()
        if oc is None:
            time.sleep(0.5)
            continue
        if oc > toc:
            _blind("Left", 9 + oc_max + 3)          # 左滚唯一可靠路径 = 钳位到 0
            oc = rect_oc()
            if oc is None or oc != 0:
                continue
        if oc < toc and not hold_scroll(toc):
            time.sleep(0.4)
            continue
        o = rect_or()
        if o is None:
            time.sleep(0.5)
            continue
        if o != tor:
            _blind("Up" if o > tor else "Down", 9 + or_max + 3)
            time.sleep(0.3)
        if rect_oc() == toc and rect_or() == tor:
            return True
    print(f"  [goto_pos] want ({tor},{toc}) got oc={rect_oc()} or={rect_or()}", flush=True)
    return False


def _huge_positions(p):
    """蛇形遍历位次 [(or,oc)]：行外列内，偶数行从左到右、奇数行从右到左。"""
    out = []
    for ri, (rs, re) in enumerate(_chunks(p["h"])):
        cols = _chunks(p["w"]) if ri % 2 == 0 else list(reversed(_chunks(p["w"])))
        for (cs, ce) in cols:
            out.append((_offset_for(rs, re, p["h"]), _offset_for(cs, ce, p["w"])))
    return out


def fill_huge(idx, skip=None):
    """24×14 及以上多段连涂（2026-10-25 重写：列优先锯齿 + 按住滚屏）。

    相比旧「行优先蛇形」的关键差别：
      旧顺序 行0: oc 0→10→14（右滚，便宜）→ 行1: oc 14→10→0（**每段都左滚**，4.7~8.4s/段）
      新顺序 列优先锯齿：oc 只增不减（0→10→14 后不再回头），行块在奇数列反向
              → 全程零左滚，goto 总耗时 21.9s → 7.3s（lvl1 24×14 实测）

    分区互不重叠 → 每墙格全程只点一次（toggle 铁律）。
    """
    p = PUZ[idx]
    walls = walls_of(idx)
    dose = TAP_MEGA if p["w"] > 30 else TAP_HUGE      # 36 宽盘剂量更慢（见 TAP_MEGA 注释）
    for ci, (cs, ce) in enumerate(_chunks(p["w"])):
        oc = _offset_for(cs, ce, p["w"])
        rows = _chunks(p["h"]) if ci % 2 == 0 else list(reversed(_chunks(p["h"])))
        for (rs, re) in rows:
            orr = _offset_for(rs, re, p["h"])
            seg = [(r, c) for (r, c) in walls if rs <= r < re and cs <= c < ce and (r, c) != skip]
            if not seg:
                continue
            if not goto_pos_fast(idx, orr, oc):
                print(f"  [fill_huge] goto ({orr},{oc}) FAIL -> 跳过该段", flush=True)
                continue
            ds.tap_batch([cell_nds_at(r, c, orr, oc) for r, c in seg], **dose)
            safe_mouseup()
            time.sleep(SETTLE_HUGE)
            g = board_gray()
            miss = [(r, c) for (r, c) in seg
                    if cell_state(g, r - orr, c - oc) == "W"]
            if miss:
                print(f"  [fill_huge] ({orr},{oc}) topup={len(miss)}", flush=True)
                ds.tap_batch([cell_nds_at(r, c, orr, oc) for r, c in miss], **VERIFY_WIDE)
                safe_mouseup()
                time.sleep(1.2)      # ★ 补点后沉降：toggle 未结算就滚屏 → 该格仍算未涂
    # 判定动画期间红框会消失(rect=None)，给足 6s 让通关横幅出现
    return wait_clear(6.0)


def verify_huge(idx):
    """24×14 修复巡检（toggle 安全，同 verify_wide 思路）：
    每轮蛇形扫全部位次：墙白 → 点黑；非墙黑 → 点白。"""
    p = PUZ[idx]
    walls = {(r, c) for r in range(p["h"]) for c in range(p["w"])
             if p["wall"][r * p["w"] + c]}
    for k in range(4):
        if state() == "clear":
            return True
        time.sleep(0.9)
        fixed = 0
        for (tor, toc) in _huge_positions(p):
            if state() == "clear":          # 判定动画中红框消失，先判通关省得空转
                return True
            if not goto_pos(idx, tor, toc):
                print(f"  [vhuge k{k}] goto ({tor},{toc}) FAIL", flush=True)
                continue
            g = board_gray()
            pts = []
            for r in range(tor, min(tor + 10, p["h"])):
                for c in range(toc, min(toc + 10, p["w"])):
                    wall = (r, c) in walls
                    stt = cell_state(g, r - tor, c - toc)
                    if (wall and stt == "W") or (not wall and stt == "B"):
                        pts.append(cell_nds_at(r, c, tor, toc))
            if pts:
                print(f"  [vhuge k{k}] ({tor},{toc}) fix={len(pts)}", flush=True)
                ds.tap_batch(pts, **VERIFY_WIDE)
                safe_mouseup()
                fixed += len(pts)
        if fixed == 0:
            return wait_clear(6.0)
    return wait_clear(5.0)


def verify_fill(idx):
    """慢路径：扫描纯白墙格补点（只补纯白，动画灰格不碰）。返回是否全黑。"""
    walls = walls_of(idx)
    for k in range(4):
        if state() == "clear":
            return True
        time.sleep(0.9)
        g = board_gray()
        miss = white_misses(g, walls)
        if not miss:
            return True
        print(f"  [verify k{k}] miss={len(miss)}", flush=True)
        for (r, c) in miss:
            ds.tap(*cell_nds(r, c), **VERIFY_TAP)
        safe_mouseup()
    g = board_gray()
    return not white_misses(g, walls)


def wait_clear(timeout=8.0, iv=0.1):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if state() == "clear":
            return True
        time.sleep(iv)
    return False


def has_time_band(im):
    """通关页 TIME 横幅（深蓝 49,82,115）；用于识别证据页是否被弹窗遮住。"""
    a = np.asarray(im.convert("RGB")).astype(int)
    R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    reg = (abs(R[245:320, 30:225] - 49) < 15) & (abs(G[245:320, 30:225] - 82) < 15) \
        & (abs(B[245:320, 30:225] - 115) < 22)
    return int(reg.sum()) > 1800


# ---------- 星级（通关页：星槽数 = 难度 n+2，金星从左往右填，未得为暗蓝） ----------
def stars_gold(im):
    """数通关页金星颗数。

    ★ 2026-10-25 修：旧窗口 x=85..195 把最左一颗星切掉了（真实星区 x=69..185）。
    6 槽布局（むずかしい）星带更宽、整体左移，旧窗口恒少读 1 颗
    ——l001 肉眼 6 金星被读成 5，导致「むずかしい 满星 6★」永远判不过。
    实测三种槽位布局的星带 x 范围：4 槽 90..165 / 5 槽 80..175 / 6 槽 69..185。
    统一窗口 x=60..200 全部覆盖，且不与「クリアタイム」黄字（y<290）相交。
    """
    a = np.asarray(im.convert("RGB")).astype(int)
    R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    gold = (R > 200) & (G > 120) & (B < 150) & (G > R * 0.45) & (G < R * 0.95)
    prof = gold[294:320, 60:200].sum(axis=0)
    xs = np.where(prof > 0)[0]
    if len(xs) == 0:
        return 0
    groups = []
    s = p = xs[0]
    for x in xs[1:]:
        if x - p > 3:
            groups.append((s, p)); s = x
        p = x
    groups.append((s, p))
    return len(groups)


# ---------- 导航 ----------
def _digits_below(y0, y1, x0=8, x1=248):
    g = np.asarray(ds.grab(None).convert("L"), dtype=float)
    return int((g[y0:y1, x0:x1] > 200).sum())


def is_nyumon_diff():
    """难度页当前是否选中 入門（上屏只有 2 行网格数字）。"""
    return _digits_below(128, 162) < 150


DIFF_DOWN = {"入門": 0, "やさしい": 1, "ふつう": 2, "むずかしい": 3}

# 选关页难度横幅模板匹配（2026-10-24 修 ensure_select 难度漂移 bug）
# 背景：原 ensure_select 只在 diff 页才切难度；若已停在 select 页（如ふつう战役后
# 遗留），直接放行 → 进错难度关卡 → clue_match 74/100 连续失败（lvl81 剂量实验实踩）。
# 横幅在下屏局部 y206-230；顶部 y206-210 有流动高光带（持续动画），模板区取下 y210-230。
_BANNER = (28, 210, 200, 230)
_TPL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tpl_banners")
_TPL_EN = {"入門": "nyumon", "やさしい": "yasashii", "ふつう": "futsuu", "むずかしい": "muzuka"}


def is_select_diff(name=DIFF):
    """选关页横幅模板匹配：当前是否已在 name 难度（跨类 L1≥58k / 同类≈0，阈值 20k）。"""
    try:
        cur = np.asarray(ds.grab(None).crop(_BANNER).convert("L")).astype(int)
        tpl = np.asarray(Image.open(os.path.join(_TPL_DIR, f"{_TPL_EN[name]}.png"))
                         .convert("L")).astype(int)
        return int(np.abs(cur - tpl).sum()) < 20000
    except Exception:
        return False


def select_diff():
    """难度页：Up 环绕到 入門，再按 DIFF Down N 次到目标难度，A 确认。"""
    for _ in range(5):
        if is_nyumon_diff():
            break
        ds.press("Up", wait=0.6, hold=0.05)
    for _ in range(DIFF_DOWN[DIFF]):
        ds.press("Down", wait=0.6, hold=0.05)
    ds.press("x", wait=1.8, hold=0.05)


def ensure_select():
    """从任意页面回到 目标难度(DIFF) 选关页。

    2026-10-24 修：select 分支加难度校验（is_select_diff 模板匹配）。
    原来只要停在 select 页就放行 —— 上个战役的难度会残留（如ふつう跑完 100/100
    后停在ふつう选关页），导致以默认 DIFF=やさしい 进错难度的关卡
    （lvl81 剂量实验实踩：clue_match 74/100 五连败）。不匹配则按 B(z) 回
    diff 页重走 select_diff() 切到目标难度。
    """
    for _ in range(18):
        st = state()
        if st == "select":
            if is_select_diff(DIFF):
                return True
            ds.press("z", wait=1.2, hold=0.05)   # B = 戻る → diff 页重走 select_diff
        if st == "clear":
            ds.tap(128, 108, after=1.5)
        elif st == "play":
            ds.press("Return", wait=1.2, hold=0.05)   # → option
        elif st == "option":
            ds.tap(205, 24, after=0.8); ds.press("x", wait=1.5, hold=0.05)
        elif st == "slot":
            # 「セーブしています…」屏（自动过）与「GREAT!! 問題が増えました」解锁弹窗
            # 都落到 slot 兜底。存档屏按 x 无害；弹窗需 x(A) 确认。2026-10-23 修：
            # 原来只 sleep(2.0) → 弹窗永远退不出 → lvl18「cannot reach select」。
            ds.press("x", wait=1.0, hold=0.05)
            time.sleep(1.5)
        elif st == "menu":
            ds.tap(170, 83, after=1.5)
        elif st == "diff":
            select_diff()
        elif st == "title":
            # 「本編を始める」按钮（2026-10-24 冷启动实测：截图 y214-249 → 局部 40；
            #   旧 y=68 落在按钮下方空隙，冷启动永远点不进去）
            ds.tap(128, 40, after=1.0)
        else:
            ds.press("z", wait=1.0, hold=0.05)
        time.sleep(0.2)
    return False


def _green_rows():
    """读选关网格 5 行的「已通关(绿)」行数，用于判定滚动窗口位置。"""
    a = np.asarray(ds.grab(None).convert("RGB")).astype(int)
    R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    green = (R < 140) & (G > 100) & (G > R + 50) & (B < 130)
    n = 0
    for r in range(5):
        y = 280 + 16 * r
        cnt = 0
        for c in range(10):
            x = 19 + 24 * c
            if green[y - 5:y + 6, x - 8:x + 9].mean() > 0.5:
                cnt += 1
        if cnt >= 8:
            n += 1
    return n


def scroll_select_top():
    """▲ 连点到绿色行数不再变化（= 到顶）。"""
    last = -1
    for _ in range(10):
        ds.tap(234, 72, after=0.75)
        g = _green_rows()
        if g == last:
            return g
        last = g
    return last


def scroll_select_bottom():
    """▼ 连点到绿色行数不再变化（= 到底）。返回最后绿行数。"""
    last = -1
    for _ in range(10):
        ds.tap(234, 172, after=0.75)
        g = _green_rows()
        if g == last:
            return g
        last = g
    return last


def _grid_img():
    """选关页 5 行网格区域的灰度图（用于判断滚动是否还有变化）。"""
    a = np.asarray(ds.grab(None).convert("L")).astype(int)
    return a[270:356, 0:256]


def scroll_select_edge(down=True):
    """把网格滚到边缘：连续点 ▲/▼ 直到画面不再变化（2026-10-23 修）。

    早期用「绿色行数」判位置，但当进度足够高时多个偏移都是 5 行全绿 →
    判据失效（实测停在 offset 20）。改用「图像不再变化」= 到边。
    """
    arrow_y = 172 if down else 72
    prev = _grid_img()
    for _ in range(14):
        ds.tap(234, arrow_y, after=0.7)
        cur = _grid_img()
        if int(np.abs(cur - prev).sum()) < 2000:
            return True
        prev = cur
    return False


def goto_level_cell(lvl):
    """滚动选关网格到包含 lvl 的窗口并 tap 选格（2026-10-23 实测）。

    选关页 = 10 列×rows_total 行的滚动窗口，一屏 5 行（50 关）；
    右侧 ▲/▼ 触摸箭头每次滚动 10 关（1 行），坐标 ▲=(234,72) ▼=(234,172)。

    ★ 2026-10-25 修：旧式 row=(lvl-51)//10 隐含「100 关=10 行」假设，
      むずかしい只有 80 关=8 行——滚到底可见首行是全局第 3 行（第 31 关），
      旧式点 (0,0) 实际选中第 31 问（diag 截图「第 031 問 24×14」实锤）。
      100 关模式下 (lvl-51)//10 恰好 ≡ (lvl-1)//10-5，所以前两个难度没暴露。
    """
    rows_total = (len(PUZ) + 9) // 10            # 网格总行数（80 关=8 行）
    top_row = max(0, rows_total - 5)             # 滚到底后可见首行（100 关=5、80 关=3）
    if lvl <= 50:
        scroll_select_edge(down=False)
        row, col = (lvl - 1) // 10, (lvl - 1) % 10
    else:
        scroll_select_edge(down=True)
        row, col = (lvl - 1) // 10 - top_row, (lvl - 1) % 10
    wy = 280 + 16 * row
    wx = 19 + 24 * col
    ds.tap(wx, wy - 192, after=0.5)              # 单击选中


def enter_level(lvl):
    """从选关页进入指定关（1-100，51+ 自动翻第 2 页）。返回 t0 或 None。"""
    for att in range(5):
        if not ensure_select():
            print(f"  [enter {lvl}] cannot reach select", flush=True)
            return None
        goto_level_cell(lvl)
        ds.press("x", wait=0.2, hold=0.05)        # A 进入
        t0 = time.time()
        st = poll(("play", "tut"), timeout=6)
        if st in ("play", "tut"):
            for settle in range(7):          # 等盘面滑入动画沉降后再校验
                time.sleep(0.7)
                ok, tot = clue_match(lvl - 1)
                if ok >= tot - 2:
                    return t0
            p = PUZ[lvl - 1]
            if p["w"] > 10 or p["h"] > 10:
                # 大盘面：视口可能继承上次滚动位置 → 盲归位后重校验一次
                ds.press_n("Left", 16, 0.22)
                ds.press_n("Up", 8, 0.22)
                time.sleep(0.6)
                ok, tot = clue_match(lvl - 1)
                if ok >= tot - 2:
                    return t0
            print(f"  [enter {lvl}] clue mismatch {ok}/{tot}, retry", flush=True)
        else:
            print(f"  [enter {lvl}] att{att} state={st}", flush=True)
    return None


# ---------- 单关主流程 ----------
def wait_unlocked(idx, probe, max_wait=9.0):
    """主动探测输入锁解除（替代盲等 UNLOCK）：在已知墙格 probe(须位于默认视口 oc=0 内)
    上点 TAP_WIDE，0.22s 后读回——变黑=游戏已接受输入，立即返回 probe 格坐标，
    **该格保持涂黑，fill 时排除**（2026-10-24 修：旧版「还原为白」会让探针格进入
    持久拒涂状态——实测还原后该格白→黑失效（等 1.5s 也不行），burst 必 miss 该格，
    lvl80 实测 TIME 4s→8s；且还原点击与 burst 间隔还踩 0.3s toggle 铁律线）。
    锁未解时点为空操作（格仍白），无害；循环至解锁或超时。"""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        if state() != "play":
            time.sleep(0.2); continue
        ds.tap(*cell_nds(*probe), **TAP_WIDE)
        safe_mouseup()
        time.sleep(0.22)
        if cell_state(board_gray(), probe[0], probe[1]) == "B":
            return probe
        time.sleep(0.28)
    return None


def play_level(lvl, t0):
    global _RECT_X0, _RECT_SX, _RECT_Y0, _RECT_SY, _RECT_W36
    idx = lvl - 1
    p = PUZ[idx]
    wide = p["w"] > 10
    huge = p["h"] > 10            # 24×14 及以上（需要纵向滚动）
    if huge:
        if p["w"] > 30:
            # 36 宽（2026-10-25 lvl41 实测标定）：盘横贯全屏，框边会被屏边裁掉
            _RECT_X0, _RECT_SX = -6, 7.0
            _RECT_Y0, _RECT_SY = 29, 7.0
            _RECT_W36 = True
        else:
            _RECT_X0, _RECT_SX = 33, 7.0      # 24 宽小地图实测标定（lvl71 逐列点测）
            _RECT_W36 = False
    else:
        _RECT_X0, _RECT_SX = 13, 11.0
        _RECT_W36 = False
    # 解锁探针必须落在默认视口 oc=0/or=0 可见范围内
    probe = next(((r, c) for (r, c) in walls_of(idx) if c < 10 and r < 10), None)
    tu = time.time()
    skipped = None
    if probe is not None:
        res = wait_unlocked(idx, probe)      # 成功→返回探针格(已涂黑),失败→None
        if res:
            skipped = res
        else:
            time.sleep(2.0)                 # 异常兜底：仍未解锁则给 2s 固定缓冲
    else:
        time.sleep(UNLOCK)
    print(f"  [lvl{lvl}] unlock_probe {time.time()-tu:.2f}s skip={skipped}", flush=True)
    if huge:
        do_fill, do_verify = (lambda: fill_huge(idx, skip=skipped)), (lambda: verify_huge(idx))
    else:
        do_fill = (lambda: fill_wide(idx, skip=skipped)) if wide else (lambda: burst_fill(idx, skip=skipped))
        do_verify = (lambda: verify_wide(idx)) if wide else (lambda: verify_fill(idx))
    tb = time.time()
    cleared = do_fill()
    print(f"  [lvl{lvl}] burst {time.time()-tb:.2f}s cleared={cleared}", flush=True)
    if not cleared:
        if not do_verify() or not wait_clear(8.0):
            print(f"  [retry] lvl{lvl} verify again", flush=True)
            st = state()
            if st == "play":
                ds.tap(8, 100, after=0.5)    # 点盘面左缘空白唤醒（原(128,24)会误涂 r0 格）
                time.sleep(0.5)
                cleared = do_verify()        # 只修复不重涂:脏盘整体重涂会 toggle 大乱(实测)
            if not cleared and not wait_clear(8.0):
                return False, -1
    # ★ 2026-10-25 修：旧固定 sleep(2.5) 会截到「金星还在逐颗点亮」的过程帧。
    # 实测金星点亮节奏约 0.5s/颗（+0.5s=1,+1.0s=2,+1.5s=3,+2.0s=4...），
    # 6 槽布局（むずかしい）要点满 6 颗需 ~3.0s > 2.5s
    # → 凡是 fill 一次过（无修复轮、不额外等）的关全部早截成 5★，
    #   而走了修复轮的关因多耗时间反而全亮 —— 曾误读成「星数与时间无关」。
    # ★★ 2026-10-25 二修：「连续两次读数相同就 break」仍会早停 —— 截屏抖动下
    #   两次读数可能落在同一颗星的点亮间隔内（实测 1:30 的关分别截成 2★/5★/6★，
    #   同时长星数各异 = 纯截图时机问题，游戏不扣星）。break 前强制至少等 3.6s，
    #   保证 6 颗全部点亮完毕。
    im = None
    prev = -1
    t_poll = time.time()
    t_end = t_poll + 9.0
    while time.time() < t_end:
        time.sleep(0.45)
        im = ds.grab(f"clear_l{lvl:03d}")
        if not has_time_band(im):
            continue
        n = stars_gold(im)
        if n == prev and n > 0 and time.time() - t_poll > 3.6:
            break                        # 动画已停（且至少等满 6 颗点亮时间）
        prev = n
    if not has_time_band(im):
        # 解锁弹窗/存档屏可能盖住通关页 → 按 x 关掉后重抓（防止证据被污染）
        ds.press("x", wait=1.5, hold=0.05)
        time.sleep(1.5)
        im = ds.grab(f"clear_l{lvl:03d}")
    n = stars_gold(im)
    shutil.copy(f"/root/.codebuddy/artifact/vol11/clear_l{lvl:03d}.png",
                f"{OUT}/l{lvl:03d}_clear.png")
    print(f"  lvl{lvl:03d} cleared gold_stars={n}", flush=True)
    return True, n


def main():
    lo = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    hi = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    if len(sys.argv) > 3:
        global OUT
        OUT = sys.argv[3]
    print(f"=== mode2 fast v1: lvl {lo}..{hi} -> {OUT}", flush=True)
    if not ensure_select():
        print(f"FAIL: cannot reach {DIFF} select page", flush=True)
        return 1
    if DIFF != "やさしい":
        # ensure_select 只认「在选关页」，不区分难度 → 当前可能停在别的难度页。
        # 选关页「戻る」(60,175) → 难度页 → select_diff() 重选（幂等，已在目标难度也无害）。
        ds.tap(60, 175, after=1.0)
        select_diff()
        time.sleep(0.5)
        if state() != "select":
            print(f"FAIL: cannot switch difficulty to {DIFF}", flush=True)
            ds.grab("fail_diff_switch")
            return 1
    results = []
    for lvl in range(lo, hi + 1):
        t0 = enter_level(lvl)
        if t0 is None:
            print(f"FAIL enter lvl{lvl}", flush=True)
            ds.grab(f"fail_enter_l{lvl:03d}")
            break
        tl = time.time()
        ok, n = play_level(lvl, t0)
        print(f"  [lvl{lvl}] WALL {time.time()-tl:.2f}s ok={ok} stars={n}", flush=True)
        results.append((lvl, ok, n))
        if not ok:
            print(f"FAIL solve lvl{lvl}", flush=True)
            ds.grab(f"fail_solve_l{lvl:03d}")
            break
    print("=== summary ===", flush=True)
    for lvl, ok, n in results:
        print(f"{'OK ' if ok else '   '} lvl{lvl:03d} ok={ok} gold_stars={n}", flush=True)
    # 满星规则（2026-10-23 用户确认）：难度 n（入門=1/やさしい=2/ふつう=3/むずかしい=4）
    # 的满星 = n+2 → やさしい 满 4★、ふつう 满 5★（むずかしい=6 未实机验证）。
    MAX_STARS = MAX_BY_DIFF[DIFF]
    good = sum(1 for _, ok, n in results if ok and n >= MAX_STARS)
    print(f"{MAX_STARS}-star(max): {good}/{len(results)}", flush=True)
    return 0 if good == len(results) and len(results) == hi - lo + 1 else 1


if __name__ == "__main__":
    sys.exit(main())
