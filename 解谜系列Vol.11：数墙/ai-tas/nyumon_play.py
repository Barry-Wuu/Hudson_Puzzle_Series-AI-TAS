#!/usr/bin/env python3
"""入門 play 阶段: 读盘 + 数墙求解 + 涂格。

2026-10-25 实测标定:
  * 盘面在底屏, 几何由 tut.detect_grid 动态探测(盘面会随步骤移动)。
  * 格 24px; 线索格 = 奶油底(255,205,148) + 深色数字(字形像素级一致,
    模板 tpl_digits/{v}.png 精确匹配); 黑格 mean<115; 其余(白/白マス印/□)记 W。
  * 默认工具即涂黑: 点白格 -> 黑(第 3 步引导点击实测)。
  * 规则 = 标准数墙: 每线索格岛 = 连通白格且大小=线索值; 每岛恰含 1 线索;
    海(黑)连通; 无 2x2 黑。当前黑格作为固定约束(中途局面续解)。
  * 首次输入常被吞 -> 涂后必须回读校验, 未涂到就重点(最多 4 轮)。
"""
import os
import sys
import time

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds
import state2
import tut

HERE = os.path.dirname(os.path.abspath(__file__))
TPL_DIR = os.path.join(HERE, "tpl_digits")

_TPLS = None


def _load_templates():
    global _TPLS
    if _TPLS is None:
        _TPLS = {}
        for fn in sorted(os.listdir(TPL_DIR)):
            if fn.endswith(".png"):
                v = int(fn[:-4])
                _TPLS[v] = np.asarray(
                    Image.open(os.path.join(TPL_DIR, fn)).convert("L")) > 127
    return _TPLS


def _glyph_mask(win):
    """格内数字字形 bbox 掩码; 无字形/仅□标记返回 None。

    边缘连通过滤: 格线深色木纹段刮进窗口时必与窗口边相连, 数字字形
    居中且不触边 -> 去掉边连通分量即得干净字形(抗 ±3px 定位抖动)。
    """
    dark = win.sum(axis=2) < 250
    if dark.sum() < 12:
        return None
    h, w = dark.shape
    # 从窗口四边洪水填充, 标记边连通暗像素
    edge = np.zeros_like(dark)
    st = []
    for x in range(w):
        for y in (0, h - 1):
            if dark[y, x] and not edge[y, x]:
                edge[y, x] = True
                st.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if dark[y, x] and not edge[y, x]:
                edge[y, x] = True
                st.append((y, x))
    while st:
        y, x = st.pop()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and dark[ny, nx] and not edge[ny, nx]:
                edge[ny, nx] = True
                st.append((ny, nx))
    core = dark & ~edge
    if core.sum() < 12:
        return None
    ys, xs = np.where(core)
    bh, bw = ys.max() - ys.min() + 1, xs.max() - xs.min() + 1
    if bh < 8 and bw < 9:
        return None                      # □ 标记(5x5)非数字
    return core[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def _match_digit(gm):
    """精确模板匹配 -> 值; 未知返回 None。"""
    tpls = _load_templates()
    for v, t in tpls.items():
        if t.shape == gm.shape and (t == gm).all():
            return v
    # 容错: 缩放到同尺寸比一致性(防锯齿/抖动)
    best, bestv = 0.75, None
    gh, gw = gm.shape
    for v, t in tpls.items():
        ti = np.asarray(Image.fromarray((t * 255).astype("uint8")).resize(
            (gw, gh))) > 127
        agree = (ti == gm).mean()
        if agree > best:
            best, bestv = agree, v
    return bestv


# ---------- 读盘 ----------
def read_board(f=None, verbose=False):
    """-> dict(grid, clues, blacks, whites, marks, rows, cols) 或 None。

    字形窗 20x20(offset +2..+22): 容纳 ±3px 定位误差 + 字形光晕,
    边缘连通过滤掉刮进的格线/框暗带(数字居中不触边)。
    黑白均值窗 16x16(offset +4..+20): 避开格线。
    """
    if f is None:
        f = tut.grab_np()
    grid = tut.detect_grid(f)
    if not grid:
        return None
    x0, y0, cols, rows = grid
    clues, blacks, whites, marks = {}, set(), set(), set()
    for r in range(rows):
        for c in range(cols):
            win = f[y0 + 24 * r + 2:y0 + 24 * r + 22,
                    x0 + 24 * c + 2:x0 + 24 * c + 22]
            inner = f[y0 + 24 * r + 4:y0 + 24 * r + 20,
                      x0 + 24 * c + 4:x0 + 24 * c + 20]
            m = inner.reshape(-1, 3).mean(axis=0)
            if m[0] < 115 and m[1] < 115 and m[2] < 115:
                blacks.add((r, c))
                continue
            gm = _glyph_mask(win)
            if gm is not None:
                v = _match_digit(gm)
                if v is None:
                    if verbose:
                        print(f"    unknown glyph at ({r},{c}) shape={gm.shape}")
                    Image.fromarray((gm * 255).astype("uint8")).save(
                        f"/tmp/tut_unk_{r}_{c}.png")
                clues[(r, c)] = v
            elif m[0] > 225 and m[1] > 225 and m[2] > 225:
                whites.add((r, c))
            else:
                marks.add((r, c))          # 白マス印/□ -> 视作白
    if verbose:
        print(f"  board: grid={grid} clues={clues} "
              f"blacks={sorted(blacks)} marks={sorted(marks)}")
    return dict(grid=grid, clues=clues, blacks=blacks,
                whites=whites | marks, marks=marks, rows=rows, cols=cols)


def show(b):
    g = [["." for _ in range(b["cols"])] for _ in range(b["rows"])]
    for (r, c), v in b["clues"].items():
        g[r][c] = str(v) if v else "?"
    for (r, c) in b["blacks"]:
        g[r][c] = "#"
    for (r, c) in b["marks"]:
        g[r][c] = "m"
    for row in g:
        print("".join(row))


# ---------- 求解 ----------
def _islands(rc, size, rows, cols, blocked):
    """所有包含 rc 的 size 格 4-连通集, 不含 blocked。"""
    seen, out = set(), []

    def grow(cur):
        if len(cur) == size:
            fs = frozenset(cur)
            if fs not in seen:
                seen.add(fs)
                out.append(fs)
            return
        frontier = set()
        for (r, c) in cur:
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nr, nc = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols and \
                        (nr, nc) not in cur and (nr, nc) not in blocked:
                    frontier.add((nr, nc))
        for cell in sorted(frontier):
            grow(cur | {cell})

    grow({rc})
    return out


def solve(clues, fixed_b, rows, cols):
    """数墙精确求解 -> 黑格集合; 无解返回 None。"""
    if any(v is None for v in clues.values()):
        return None
    clue_cells = set(clues)
    shapes = []
    for rc, sz in clues.items():
        blocked = fixed_b | (clue_cells - {rc})
        sh = _islands(rc, sz, rows, cols, blocked)
        if not sh:
            return None
        shapes.append((rc, sz, sh))
    order = sorted(range(len(shapes)), key=lambda i: len(shapes[i][2]))
    all_cells = {(r, c) for r in range(rows) for c in range(cols)}

    def bt(k, used):
        if k == len(order):
            blacks = all_cells - used
            if not fixed_b <= blacks:
                return None
            for r in range(rows - 1):
                for c in range(cols - 1):
                    if all((r + dr, c + dc) in blacks
                           for dr in (0, 1) for dc in (0, 1)):
                        return None
            if blacks:
                st, seen = [next(iter(blacks))], {next(iter(blacks))}
                while st:
                    r, c = st.pop()
                    for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nb = (r + dr, c + dc)
                        if nb in blacks and nb not in seen:
                            seen.add(nb)
                            st.append(nb)
                if seen != blacks:
                    return None
            return blacks
        rc, sz, sh = shapes[order[k]]
        for isl in sh:
            if used & isl:
                continue
            # 岛间不可四连通(否则并成含 2 线索的大岛); 对角相邻合法
            touch = False
            for (r, c) in isl:
                for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    if (r + dr, c + dc) in used:
                        touch = True
                        break
                if touch:
                    break
            if touch:
                continue
            res = bt(k + 1, used | isl)
            if res is not None:
                return res
        return None

    return bt(0, frozenset())


# ---------- 涂格 ----------
def cell_nds(grid, r, c):
    x0, y0 = grid[0], grid[1]
    return (x0 + 24 * c + 12, y0 + 24 * r + 12 - 192)


def apply_solution(sol_blacks, max_rounds=4, verbose=False):
    """把盘面整成解: 涂黑缺格、擦除多格。play 阶段点击即切换(黑<->白)。

    关键同步修复（2026-10-25 收紧后实踩）：desmume 吞点击 + 涂格有渲染延迟，
    若每轮发完落子立刻回读，会把「动画未登记」误判成「没涂」→ 重复点击把格子
    白↔黑来回切，需 4-5 轮才收敛。改为：一轮把该轮落子全发完 -> 等 0.6s 让真实
    帧登记完 -> 再回读校验。通常 1-2 轮收敛、无来回切。落子 after=0.20/hold=0.06。
    """
    for rd in range(max_rounds):
        # 通关动画会改变盘面渲染（回读误判根源）——每轮先判 clear
        if state2.detect(ds.grab(None)) == "clear":
            return True
        b = read_board()
        if not b:
            time.sleep(0.3)
            continue
        erase = [cell for cell in b["blacks"] if cell not in sol_blacks]
        todo = [cell for cell in sol_blacks if cell not in b["blacks"]]
        if not todo and not erase:
            return True
        if verbose:
            print(f"    round {rd}: paint {len(todo)} erase {len(erase)}")
        for (r, c) in erase:
            ds.tap(*cell_nds(b["grid"], r, c), hold=0.06, after=0.20, gap=0.02)
        for (r, c) in todo:
            ds.tap(*cell_nds(b["grid"], r, c), hold=0.06, after=0.20, gap=0.02)
        # 等真实帧把本轮点击全部登记完，再回读（避免动画期误判 -> 重复点击）
        time.sleep(0.6)
    # 终判：通关动画期读盘会误判，故 state==clear 直接算成功
    if state2.detect(ds.grab(None)) == "clear":
        return True
    b = read_board()
    if not b:
        return False
    return not [cell for cell in sol_blacks if cell not in b["blacks"]] and \
        not [cell for cell in b["blacks"] if cell not in sol_blacks]


def play_once(verbose=True):
    """读盘 -> 求解 -> 涂格。返回 (ok, board, solution)。"""
    # 盘面稳定性防护（2026-10-25 lvl7 实踩）：START/滑入动画期间右下半盘面
    # 未绘制（marks 15+），此时读到的 clues 不完整 -> 按残缺线索求解涂格 =
    # 涂错 24 格脏盘死循环。marks > 8 视为无效读盘，等待重读。
    b = None
    for try_i in range(8):
        b = read_board(verbose=verbose and try_i == 0)
        if not b:
            time.sleep(0.4)
            continue
        if len(b["marks"]) <= 8:
            break
        if verbose:
            print(f"  board unstable (marks={len(b['marks'])}), wait")
        time.sleep(0.5)
    if not b:
        print("  no board")
        return False, None, None
    if len(b["marks"]) > 8:
        print(f"  board still unstable (marks={len(b['marks'])}), abort")
        return False, b, None
    show(b)
    if any(v is None for v in b["clues"].values()):
        print("  unknown clue digit, abort")
        return False, b, None
    sol = solve(b["clues"], b["blacks"], b["rows"], b["cols"])
    if sol is None:
        print("  NO SOLUTION with current blacks fixed")
        sol2 = solve(b["clues"], set(), b["rows"], b["cols"])
        if sol2 is None:
            print("  NO SOLUTION at all")
            return False, b, None
        print(f"  solution ignoring fixed blacks: {len(sol2)} blacks "
              f"(current wrong: {sorted(b['blacks'] - sol2)})")
        sol = sol2
    if verbose:
        print(f"  solution: {len(sol)} blacks")
    ok = apply_solution(sol, verbose=verbose)
    return ok, b, sol


if __name__ == "__main__":
    ok, b, sol = play_once()
    print("play_once ->", ok)
