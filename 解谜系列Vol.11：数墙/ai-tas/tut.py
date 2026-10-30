#!/usr/bin/env python3
"""入門（チュートリアル）模式自动化 —— 跟随闪烁格引导完成教学关。

机制（2026-10-25 实测标定）：
  * 盘面：格 24px，行列随步骤变（实测 4x6 / 6x6），棕色木纹边框，
    几何动态探测（左右棕色框带定 x 范围，上下框带定 y 范围）。
  * 闪烁：周期 ~1s，半透明高亮 + 量化标签：
        白格+棕橙高亮 -> {W,O}  目标(动作待定: 涂黑/打□/信息步)
        白格+暗闪     -> {W,K}  目标(涂黑)
        白格+品红闪   -> {W,M}  信息步(按 R)
        黑格+白闪     -> {K,W}  目标(单击 -> □)
        黑格+橙闪     -> {K,O}  上下文(不点)
        线索格(有数字字形)闪烁 -> 跳过
  * 动作升级（每轮后验证）：单击涂黑 -> 未推进且闪烁集不变则再单击(转□)
        -> 仍未推进按 R(Ⓡ 進む)。闪烁集变化 = 分步目标出现，继续点。
  * 推进判定：上屏文字指纹变化。
  * 涂格循环：白 ->(点)-> 黑 ->(点)-> □ ->(点)-> 白。
"""
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds

CELL = 24
N_FRAMES, FRAME_IV = 14, 0.2      # 闪烁检测抓帧（2.8s > 最大实测周期 1.25s）


# ---------- 基础 ----------
def grab_np():
    return np.asarray(ds.grab(None).convert("RGB")).astype(int)


def group(v, gap=2):
    out = []
    for x in v:
        if out and x - out[-1][-1] <= gap:
            out[-1].append(x)
        else:
            out.append([x])
    return [int(np.mean(g)) for g in out]


def is_brown(px):
    r, g, b = px
    return 70 <= r <= 195 and 45 <= g <= 165 and b < 125 and r > b + 25


# ---------- 棋盘几何 ----------
def _dark_mask(band):
    """格线/木框颜色掩码。

    实测标定（2026-10-25）：
      格线   (139,123,106)/(139,131,123)  2-3px, 贯穿盘面
      木框   (115,98,90)/(131,115,106)    盘面四边, 比格线宽
    排除: 墙纸(197-213 浅蓝灰) 白格(246) 黑格(41) 橙闪(255,205,148)
          白マス印格(172,156,148) 数字字形(稀疏, 单列计数低)
    """
    R, G, B = band[:, :, 0], band[:, :, 1], band[:, :, 2]
    return ((R >= 100) & (R <= 160) & (G >= 88) & (G <= 145) &
            (B >= 72) & (B <= 135) & (R > B + 10) & (R >= G - 5))


def _arith_run(centers, step=CELL, tol=3):
    """最长近似等距(step)串 -> (start, end, n) 或 None。"""
    if not centers:
        return None
    best = None
    for i, a in enumerate(centers):
        run = [a]
        for b in centers[i + 1:]:
            if abs((b - run[-1]) - step) <= tol:
                run.append(b)
            elif b - run[-1] > step + tol:
                break
        if best is None or len(run) > len(best):
            best = run
    if best is None or len(best) < 3:
        return None
    return (best[0], best[-1], len(best))


def _frame_bands(band, th):
    """木框四带 -> (xL, xR, yT, yB) 簇中心或 None。"""
    dark = _dark_mask(band)
    colcnt = dark.sum(axis=0)
    rowcnt = dark.sum(axis=1)
    vc = group([x for x in range(band.shape[1]) if colcnt[x] > th], gap=3)
    hc = group([y for y in range(band.shape[0]) if rowcnt[y] > th], gap=3)
    if len(vc) < 2 or len(hc) < 2:
        return None
    return (vc[0], vc[-1], hc[0], hc[-1])


def detect_grid(f, verbose=False):
    """探测棋盘几何 -> (x0, y0, cols, rows) 或 None。

    主信号 = 木框四带(深棕, 阈值 80→60→40 回退) 定盘面范围;
    精修 = 框内 (189,189,189) 格线混色柱(墙纸在框外, 框内仅格线呈此色)
    的等距串; 外边界线可能被黑格描边遮黑, 用框带外推校验。
    """
    band = f[192:]
    h, w = band.shape[:2]
    fb = None
    for th in (80, 60, 40):
        fb = _frame_bands(band, th)
        if fb:
            break
    if not fb:
        if verbose:
            print("  grid: no frame bands")
        return None
    xL, xR, yT, yB = fb
    x0f, x1f = xL + 3, xR - 3
    y0f, y1f = yT + 3, yB - 3
    colsf = round((x1f - x0f) / CELL)
    rowsf = round((y1f - y0f) / CELL)
    if not (2 <= colsf <= 8 and 2 <= rowsf <= 8):
        if verbose:
            print(f"  grid: bad frame size cols={colsf} rows={rowsf}")
        return None
    # 框内 (189) 格线混色掩码
    R, G, B = band[:, :, 0], band[:, :, 1], band[:, :, 2]
    m189 = (abs(R - 189) < 10) & (abs(G - 189) < 10) & (abs(B - 189) < 10)
    x_lo, x_hi = int(xL) + 2, int(xR) - 2
    y_lo, y_hi = int(yT) + 2, int(yB) - 2
    sub = m189[y_lo:y_hi + 1, x_lo:x_hi + 1]
    colcnt = sub.sum(axis=0)
    rowcnt = sub.sum(axis=1)
    vx = group([x_lo + i for i in range(sub.shape[1]) if colcnt[i] > 40], gap=3)
    hy = group([y_lo + i for i in range(sub.shape[0]) if rowcnt[i] > 40], gap=3)
    vr = _arith_run(vx)
    hr = _arith_run(hy)

    def refine(run, lo_frame, hi_frame, nf):
        """等距串 + 框带范围 -> (start, n)。外边界线被遮时用框带外推。"""
        if not run:
            return lo_frame, nf
        s, e, _n = run
        if abs(s - lo_frame) <= 6:
            start = s
        elif abs(s - CELL - lo_frame) <= 6:
            start = s - CELL
        else:
            start = lo_frame
        if abs(e - hi_frame) <= 6:
            end = e
        elif abs(e + CELL - hi_frame) <= 6:
            end = e + CELL
        else:
            end = hi_frame
        return start, round((end - start) / CELL)

    x0, cols = refine(vr, x0f, x1f, colsf)
    y0b, rows = refine(hr, y0f, y1f, rowsf)
    y0 = y0b + 192
    if not (2 <= cols <= 8 and 2 <= rows <= 8):
        if verbose:
            print(f"  grid: bad size cols={cols} rows={rows} vx={vx} hy={hy}")
        return None
    if not (16 <= x0 <= 210 and 195 <= y0 <= 260 and
            x0 + CELL * cols <= 252 and y0 + CELL * rows <= 382):
        if verbose:
            print(f"  grid: out of range x0={x0} y0={y0} cols={cols} rows={rows}")
        return None
    if verbose:
        print(f"  grid: x0={x0} y0={y0} cols={cols} rows={rows} "
              f"(frame x[{xL},{xR}] y[{yT},{yB}] vx={vx} hy={hy})")
    return (x0, y0, cols, rows)


# ---------- 格子状态 ----------
def label_of(m):
    """格均色 -> 量化标签 W/K/O/M/?。"""
    r, g, b = m
    if r > 225 and g > 225 and b > 225:
        return "W"
    if r < 115 and g < 115 and b < 115:
        return "K"
    if r > 185 and r > g + 35 and g < 205:
        return "O"
    if r > 225 and b > 195 and g < 145:
        return "M"
    return "?"


def cell_win(f, grid, r, c):
    x0, y0, cols, rows = grid
    return f[y0 + CELL * r + 4:y0 + CELL * r + 20,
             x0 + CELL * c + 4:x0 + CELL * c + 20]


def cell_mean(f, grid, r, c):
    return cell_win(f, grid, r, c).reshape(-1, 3).mean(axis=0)


def has_glyph(f, grid, r, c):
    """格内有数字字形（暗像素 bbox 高>=8 视为字形；□标记是 ~5x5 方块）。"""
    win = cell_win(f, grid, r, c)
    dark = win.sum(axis=2) < 250
    if dark.sum() < 12:
        return False
    ys, xs = np.where(dark)
    bh, bw = ys.max() - ys.min() + 1, xs.max() - xs.min() + 1
    return bh >= 8 or bw >= 9


# ---------- 闪烁检测 ----------
def detect_blink(grid, n=N_FRAMES, iv=FRAME_IV, verbose=False):
    """抓 n 帧 -> { (r,c): kind }。
    kind: 'W_O' 白格橙闪 / 'W_K' 白格暗闪 / 'W_M' 白格品红 /
          'B_W' 黑格白闪 / 'B_O' 黑格橙闪(上下文)"""
    frames = []
    for _ in range(n):
        frames.append(grab_np())
        time.sleep(iv)
    out = {}
    for r in range(grid[3]):
        for c in range(grid[2]):
            labels = [label_of(cell_mean(f, grid, r, c)) for f in frames]
            labs = set(labels) - {"?"}
            if len(labs) < 2:
                continue
            if has_glyph(frames[0], grid, r, c):
                continue                      # 线索格闪烁 -> 跳过
            if labs == {"W", "O"}:
                out[(r, c)] = "W_O"
            elif labs == {"W", "K"}:
                out[(r, c)] = "W_K"
            elif labs == {"W", "M"}:
                out[(r, c)] = "W_M"
            elif labs == {"K", "W"}:
                out[(r, c)] = "B_W"
            elif labs == {"K", "O"}:
                out[(r, c)] = "B_O"
            else:
                out[(r, c)] = "other:" + ",".join(sorted(labs))
    if verbose:
        for k, v in sorted(out.items()):
            print(f"    blink {k}: {v}")
    return out, frames


def upper_fp(f):
    return f[30:150, 14:242].tobytes()


def tap_cell(grid, r, c):
    x0, y0, cols, rows = grid
    ds.tap(x0 + CELL * c + 12, y0 + CELL * r + 12 - 192,
           hold=0.06, after=0.10, gap=0.02)


def targets_of(blinks):
    """可点击目标（排除上下文与信息步）。"""
    return [(rc, k) for rc, k in blinks.items() if k in ("W_O", "W_K", "B_W")]


# ---------- 单步驱动 ----------
def do_step(grid, fp0, max_rounds=10, verbose=False):
    """处理当前教学步骤。返回 True=已推进(文字变化)。"""
    for rd in range(max_rounds):
        blinks, _ = detect_blink(grid, verbose=verbose)
        tars = targets_of(blinks)
        info_only = bool(blinks) and not tars and all(
            k == "W_M" for k in blinks.values())
        if not tars:
            # 无点击目标: 信息步或空步 -> 按 R
            ds.press("w", wait=0.3, hold=0.06)
            if upper_fp(grab_np()) != fp0:
                return True
            continue
        # 第一轮动作: 单击（涂黑 / 黑->□）
        for rc, k in tars:
            tap_cell(grid, *rc)
        time.sleep(0.3)
        if upper_fp(grab_np()) != fp0:
            return True
        # 未推进: 重查闪烁
        blinks2, _ = detect_blink(grid)
        tars2 = targets_of(blinks2)
        if set(tars2) != set(tars):
            continue                      # 闪烁集变化(分步目标) -> 继续
        # 闪烁集不变: 升级动作 —— 再单击（白->黑->□）
        for rc, k in tars:
            tap_cell(grid, *rc)
        time.sleep(0.3)
        if upper_fp(grab_np()) != fp0:
            return True
        blinks3, _ = detect_blink(grid)
        tars3 = targets_of(blinks3)
        if set(tars3) != set(tars):
            continue
        # 再升级: 按 R
        ds.press("w", wait=0.3, hold=0.06)
        if upper_fp(grab_np()) != fp0:
            return True
    return False


def upper_text_changed(f, fp0):
    return upper_fp(f) != fp0
