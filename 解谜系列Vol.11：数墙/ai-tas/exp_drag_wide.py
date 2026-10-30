#!/usr/bin/env python3
"""18×10 宽盘丢格机制判定 + 拖动连涂可行性（2026-10-25）

背景：现役 TAP_WIDE(0.04/0.06/0.02)=0.12s/格，肉眼可见比 10×10 的 TAP(0.07s) 慢 71%。
旧结论「宽盘要求 hold≥0.06」只在段a测过，段b从未以 0.07s 剂量验证。

两个待判命题：
  H1 丢格 = 游戏对宽盘每格判定耗时更长 → 连续连涂时 touch 被吞
      判据：每格独立点击（格间 sleep 0.8s）命中率应 ≈100%（游戏有充足时间）
  H2 按住拖过多格连涂可行 → 绕开每格独立判定，数量级提速
      判据：水平连续段拖动涂，命中率与 dwell 的关系

用法：python3 exp_drag_wide.py [lvl] [dwell1,dwell2,...]
"""
import sys
import time
import subprocess
from collections import defaultdict

sys.path.insert(0, "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas")
import ds
import mode2_fast as M

LVL = int(sys.argv[1]) if len(sys.argv) > 1 else 81
DWELLS = [float(x) for x in (sys.argv[2].split(",") if len(sys.argv) > 2 else ["0.06", "0.04"])]
IDX = LVL - 1
walls = M.walls_of(IDX)


def to_win(nx, ny):
    return (ds.WIN_X + nx, ds.WIN_Y + 192 + ny)


def enter():
    """干净进关 + 等解锁，返回 (段a墙格, 段b墙格)"""
    if not M.ensure_select():
        print("FAIL select", flush=True)
        return None
    t0 = M.enter_level(LVL)
    if t0 is None:
        print("FAIL enter", flush=True)
        return None
    time.sleep(max(0, M.UNLOCK - (time.time() - t0)))
    a = [(r, c) for r, c in walls if c < 10]
    b = [(r, c) for r, c in walls if c >= 10]
    return a, b


def hsegs(cells):
    """把墙格按行分组，找出所有水平连续段（长度>=2）"""
    rows = defaultdict(list)
    for r, c in cells:
        rows[r].append(c)
    out = []
    for r in sorted(rows):
        cs = sorted(rows[r])
        run = [cs[0]]
        for c in cs[1:]:
            if c == run[-1] + 1:
                run.append(c)
            else:
                if len(run) >= 2:
                    out.append((r, run))
                run = [c]
        if len(run) >= 2:
            out.append((r, run))
    return out


def stat_cells(cells):
    """统计给定全局坐标墙格的黑/白（当前视口内）"""
    g = M.board_gray()
    blk = wht = 0
    for r, c in cells:
        vc = c - M.rect_oc()
        if vc is None or vc < 0 or vc >= 10:
            continue
        st = M.cell_state(g, r, vc)
        if st == "B":
            blk += 1
        elif st == "W":
            wht += 1
    return blk, wht


# ============ H1：单格独立点击（格间长 sleep）============
def h1_test(a, n=20, dose=None, label=""):
    dose = dose or M.TAP
    print(f"\n=== H1 单格独立点击（格间 sleep 0.8s）{label} "
          f"gap={dose['gap']} hold={dose['hold']} after={dose['after']}，段a 前 {n} 格 ===", flush=True)
    sample = a[:n]
    blk = wht = 0
    for (r, c) in sample:
        ds.tap(*M.cell_nds(r, c), **dose)
        M.safe_mouseup()
        time.sleep(0.8)
        g = M.board_gray()
        st = M.cell_state(g, r, c)
        if st == "B":
            blk += 1
        elif st == "W":
            wht += 1
    print(f"  结果: 黑={blk} 白={wht} 命中率={100*blk/max(1,blk+wht):.0f}%", flush=True)
    return blk, wht


# ============ H2：拖动连涂（水平连续段）============
def h2_test(dwell, oc=0):
    segs = hsegs([(r, c) for r, c in walls if (c < 10 if oc == 0 else c >= 10)])
    total = sum(len(cs) for _, cs in segs)
    print(f"\n=== H2 拖动连涂 dwell={dwell} oc={oc}：{len(segs)} 段 / 共 {total} 格 ===", flush=True)
    args = []
    for (r, cs) in segs:
        pts = [M.cell_nds(r, c) for c in cs] if oc == 0 else \
              [(24 + 16 * (c - oc), 24 + 16 * r) for c in cs]
        sx, sy = to_win(*pts[0])
        args += ["mousemove", str(sx), str(sy), "mousedown", "1"]
        for nx, ny in pts[1:]:
            wx, wy = to_win(nx, ny)
            args += ["mousemove", str(wx), str(wy), "sleep", str(dwell)]
        args += ["mouseup", "1", "sleep", "0.15"]
    t0 = time.time()
    subprocess.run(["xdotool"] + args, env=ds.ENV)
    el = time.time() - t0
    time.sleep(1.2)
    cells = [(r, c) for (r, cs) in segs for c in cs]
    blk, wht = stat_cells(cells)
    tot = blk + wht
    print(f"  耗时 {el:.2f}s ({el/max(1,tot):.3f}s/格) 黑={blk} 白={wht} 命中率={100*blk/max(1,tot):.0f}%", flush=True)
    return blk, wht


if __name__ == "__main__":
    res = enter()
    if res is None:
        sys.exit(1)
    a, b = res
    print(f"lvl{LVL}: 段a={len(a)} 段b={len(b)} 墙={len(walls)}", flush=True)

    h1_test(a, 20, M.TAP, "← 10×10 同剂量")
    res = enter()
    if res is None:
        sys.exit(1)
    h1_test(res[0], 20, M.TAP_WIDE, "← 宽盘现役剂量")

    for d in DWELLS:
        res = enter()
        if res is None:
            break
        M.scroll_to_oc_rect(0)
        time.sleep(0.4)
        h2_test(d, 0)

    print("\n=== 完 ===", flush=True)
