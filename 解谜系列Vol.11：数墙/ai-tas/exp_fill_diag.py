#!/usr/bin/env python3
"""fill_wide 分阶段插桩实验：定位 81-100 丢击发生在哪一段。

流程（在干净盘面上）：
  1. enter_level(lvl) 干净进关
  2. 阶段A: scroll_to_oc_rect(0) → tap seg a → 沉降 → 统计段a命中/误涂
  3. 阶段B: scroll_to_oc_rect(8) → tap seg b → 沉降 → 统计段b命中/误涂
每阶段打印 oc、耗时、逐段统计。不自动 verify（保持现场）。
"""
import sys
import time

sys.path.insert(0, "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas")
import numpy as np
import ds
import mode2_fast as M

LEVEL = int(sys.argv[1]) if len(sys.argv) > 1 else 98
GAP = float(sys.argv[2]) if len(sys.argv) > 2 else 0.04
HOLD = float(sys.argv[3]) if len(sys.argv) > 3 else 0.06
AFTER = float(sys.argv[4]) if len(sys.argv) > 4 else 0.02
IDX = LEVEL - 1


def seg_stats(oc_view):
    """在视口 oc_view 下统计该段墙格: (n, black, white_miss, anim, wrong_black)"""
    p = M.PUZ[IDX]
    g = M.board_gray()
    n = b = w = a_ = wb = 0
    wrong = []
    for r in range(p["h"]):
        for c in range(p["w"]):
            vc = c - oc_view
            if vc < 0 or vc >= 10:
                continue
            wall = p["wall"][r * p["w"] + c] == 1
            stt = M.cell_state(g, r, vc)
            if not wall:
                if stt == "B":
                    wb += 1; wrong.append((r, c))
                continue
            n += 1
            if stt == "B":
                b += 1
            elif stt == "W":
                w += 1
            else:
                a_ += 1
    return n, b, w, a_, wb, wrong


def dump_map(oc_view):
    p = M.PUZ[IDX]
    g = M.board_gray()
    for r in range(p["h"]):
        row = ""
        for vc in range(10):
            c = oc_view + vc
            if c >= p["w"]:
                row += " "
                continue
            wall = p["wall"][r * p["w"] + c] == 1
            stt = M.cell_state(g, r, vc)
            if stt == "B":
                row += "B" if wall else "o"
            elif stt == "W":
                row += "W" if wall else "."
            else:
                row += "?"
        print(f"  r{r:02d} {row}", flush=True)


def main():
    print(f"=== fill 分段插桩 lvl{LEVEL} gap={GAP} hold={HOLD} after={AFTER} ===", flush=True)
    if not M.ensure_select():
        print("FAIL: cannot reach select", flush=True)
        return 1
    t0 = M.enter_level(LEVEL)
    if t0 is None:
        print("FAIL enter", flush=True)
        return 1
    time.sleep(max(0, M.UNLOCK - (time.time() - t0)))

    walls = M.walls_of(IDX)
    a = [(r, c) for r, c in walls if c < 10]
    b = [(r, c) for r, c in walls if c >= 10]
    print(f"墙格: 段a={len(a)} 段b={len(b)}", flush=True)

    # ---- 阶段A ----
    ok0 = M.scroll_to_oc_rect(0)
    oc = M.rect_oc()
    print(f"[A] scroll oc={oc} ok={ok0}", flush=True)
    n0, b0, w0, a0, wb0, _ = seg_stats(0)
    print(f"[A] 涂前: 段a黑={b0} 白={w0} 其他={a0}", flush=True)
    if b0 > 3:
        print("[A] 盘面不干净, 中止", flush=True)
        return 1
    tb = time.time()
    ds.tap_batch([M.cell_nds(r, c) for r, c in a], gap=GAP, hold=HOLD, after=AFTER)
    M.safe_mouseup()
    el = time.time() - tb
    print(f"[A] 连涂 {el:.2f}s ({el/len(a):.3f}s/格)", flush=True)
    time.sleep(1.6)
    oc_after = M.rect_oc()
    n, b1, w1, a1, wb1, wrong = seg_stats(0)
    print(f"[A] 涂后 oc={oc_after}: 命中={b1-b0}/{len(a)} ({100*(b1-b0)/len(a):.0f}%)"
          f" 白={w1} 动画={a1} 误涂非墙={wb1} {wrong[:6]}", flush=True)
    dump_map(0)

    # ---- 阶段B ----
    ok8 = M.scroll_to_oc_rect(8)
    oc = M.rect_oc()
    print(f"[B] scroll oc={oc} ok={ok8}", flush=True)
    if oc != 8:
        print("[B] 视口未到 8, 中止(不盲涂)", flush=True)
        return 1
    tb = time.time()
    ds.tap_batch([(24 + 16 * (c - 8), 24 + 16 * r) for r, c in b],
                 gap=GAP, hold=HOLD, after=AFTER)
    M.safe_mouseup()
    el = time.time() - tb
    print(f"[B] 连涂 {el:.2f}s ({el/len(b):.3f}s/格)", flush=True)
    time.sleep(1.6)
    n, b2, w2, a2, wb2, wrong = seg_stats(8)
    print(f"[B] 涂后: 命中={b2}/{len(b)} ({100*b2/len(b):.0f}%)"
          f" 白={w2} 动画={a2} 误涂非墙={wb2} {wrong[:6]}", flush=True)
    dump_map(8)
    print("=== 完 ===", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
