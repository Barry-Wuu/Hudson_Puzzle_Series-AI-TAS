#!/usr/bin/env python3
"""exp_wide_fast.py —— 18×10 丢击率剂量-反应实验（只测段 a，58 格，不动段 b）。

对干净盘面用指定 (gap, hold, after) 连涂段 a，沉降后统计命中率：
  用法: python3 exp_wide_fast.py <lvl> [gap] [hold] [after]
  默认参数 = mode2_fast TAP (0.02/0.04/0.01, 周期 0.07s)

背景结论（2026-10-23 实测）：
  - 视口在连涂期间零漂移（rect_oc 前后一致），触屏点击不触发滚屏
  - 坐标零错位（非墙误涂恒为 0），丢的点击是「凭空消失」
  - 周期 0.07s → 丢 30~50%；旧慢管线周期 0.52s → 丢 0%（100/100 关）
  - 本实验找出 18×10 盘面「零丢击最小周期」
"""
import sys
import time

sys.path.insert(0, "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas")
import ds
import mode2_fast as M

LEVEL = int(sys.argv[1]) if len(sys.argv) > 1 else 98
GAP = float(sys.argv[2]) if len(sys.argv) > 2 else 0.02
HOLD = float(sys.argv[3]) if len(sys.argv) > 3 else 0.04
AFTER = float(sys.argv[4]) if len(sys.argv) > 4 else 0.01
IDX = LEVEL - 1
CYCLE = GAP + HOLD + AFTER


def board_b_count(idx, oc=0, vis=10):
    p = M.PUZ[idx]
    g = M.board_gray()
    n = b = a = 0
    for r in range(p["h"]):
        for vc in range(vis):
            c = oc + vc
            if c >= p["w"]:
                continue
            if p["wall"][r * p["w"] + c] != 1:
                continue
            n += 1
            st = M.cell_state(g, r, vc)
            if st == "B":
                b += 1
            elif st == "A":
                a += 1
    return n, b, a


def main():
    print(f"=== 剂量实验 lvl{LEVEL} gap={GAP} hold={HOLD} after={AFTER}"
          f" 周期={CYCLE:.2f}s ===", flush=True)
    if not M.ensure_select():
        print("FAIL: cannot reach select", flush=True)
        return 1
    t0 = M.enter_level(LEVEL)
    if t0 is None:
        print("FAIL enter", flush=True)
        return 1
    time.sleep(max(0, M.UNLOCK - (time.time() - t0)))

    n, b0, _ = board_b_count(IDX, 0)
    if b0 > 5:
        print(f"盘面脏(黑{b0}) → リタイア重开", flush=True)
        ds.press("Return", wait=1.5, hold=0.08)
        ds.tap(120, 180, after=1.2)
        ds.press("x", wait=3.0, hold=0.08)
        time.sleep(2.5)
        M.scroll_to_oc_rect(0)
        n, b0, _ = board_b_count(IDX, 0)
    print(f"段a墙数={n} 涂前黑={b0}", flush=True)

    walls = M.walls_of(IDX)
    seg_a = [(r, c) for r, c in walls if c < 10]

    M.scroll_to_oc_rect(0)
    tb = time.time()
    ds.tap_batch([M.cell_nds(r, c) for r, c in seg_a], gap=GAP, hold=HOLD, after=AFTER)
    M.safe_mouseup()
    el = time.time() - tb
    print(f"连涂 {el:.2f}s（实测 {el/len(seg_a):.3f}s/格）", flush=True)

    time.sleep(1.5)
    _, b1, a1 = board_b_count(IDX, 0)
    hit = b1 - b0
    print(f">>> 周期{CYCLE:.2f}s: 涂了{hit}/{len(seg_a)} 命中率={100*hit/len(seg_a):.0f}%"
          f" 动画中={a1}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
