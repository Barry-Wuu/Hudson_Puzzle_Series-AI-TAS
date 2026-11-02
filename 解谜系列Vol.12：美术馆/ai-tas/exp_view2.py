#!/usr/bin/env python3
"""验证「滚动/点灯后等待不足」是否是 sc>0 块误判的根因。

假设：
  1. _scroll_viewport 后只 sleep 0.30 → 滚动动画未落定 → 墙匹配 41-48 → 误判失败重滚
  2. 本块终检紧跟最后一次 tap 无等待 → 点亮动画未完成 → 全判「未确认灯」

验证：滚到 sc=8 后分段等待测墙匹配；点灯后分段等待测灯。
"""
import sys, time
sys.path.insert(0, ".")
import numpy as np
from PIL import Image
import play_akari_seg3 as P
import ds


def best_view(a, pz):
    w = pz["w"]
    exp = P.expected_walls(pz)
    cand = []
    for sc in range(0, w - P.VIS_W + 1):
        got = P.read_vis_walls(a, pz, sc, 0)
        m = sum(got[i][j] == exp[i][sc + j]
                for i in range(P.VIS_H) for j in range(P.VIS_W))
        cand.append((m, sc))
    cand.sort(reverse=True)
    return cand


def scroll(waith, hold, sr, sc, pz):
    w, h = pz["w"], pz["h"]
    for _ in range(h):
        ds.press("Up", wait=waith, hold=hold)
    for _ in range(w):
        ds.press("Left", wait=waith, hold=hold)
    for _ in range(min(sr + 5, h - 1)):
        ds.press("Down", wait=waith, hold=hold)
    for _ in range(min(sc + 5, w - 1)):
        ds.press("Right", wait=waith, hold=hold)


def yellow_at(a, bx, by, sc0, sr0=0):
    vc, vr = bx - sc0, by - sr0
    cx, cy = int(16 + 16 * (vc + 0.5)), int(208 + 16 * (vr + 0.5))
    cell = a[cy - 4:cy + 5, cx - 4:cx + 5].reshape(-1, 3)
    return ((cell[:, 0] > 190) & (cell[:, 1] > 170) & (cell[:, 2] < 120)).sum()


def main():
    n = 31
    pz = P._SEQ[n - 1]
    w, h = pz["w"], pz["h"]
    print(f"=== Q{n} {w}x{h} bulbs={len(pz['bulbs'])} ===", flush=True)

    if not P.in_select_page():
        P.escape_to_select(); time.sleep(1.0)
    P.goto_level(n); time.sleep(2.0)
    if not P.in_play_page():
        for _ in range(5):
            ds.press("x", wait=1.0)
            if P.in_play_page():
                break
        time.sleep(1.0)
    if not P.in_play_page():
        print("!! 未进游玩页", flush=True); return 1
    P.reset_level(); time.sleep(2.0)
    print(f"复位后 yellow={P.board_yellow_count()}", flush=True)

    print("\n--- 滚到 sc=8（慢剂量）后的墙匹配随等待变化 ---", flush=True)
    t0 = time.time()
    scroll(0.30, 0.02, 0, 8, pz)
    print(f"  按键耗时 {time.time()-t0:.1f}s", flush=True)
    acc = 0.0
    for tw in [0.30, 0.60, 1.20, 2.00]:
        time.sleep(tw - acc); acc = tw
        a = P.grab_np()
        bv = best_view(a, pz)
        print(f"  等待≈{tw:.2f}s  best={bv[0]} 次={bv[1]}", flush=True)
    a = P.grab_np()
    Image.fromarray(a.astype("uint8")).save("/tmp/exp3_s8_settled.png")

    print("\n--- 按视口=8 坐标点灯，终检随等待变化 ---", flush=True)
    sc = 8
    targets = [(bx, by) for (bx, by) in pz["bulbs"] if sc <= bx < sc + 10]
    print(f"  targets={len(targets)}", flush=True)
    t0 = time.time()
    for (bx, by) in targets:
        ds.tap(int(16 + 16 * ((bx - sc) + 0.5)),
               int(208 + 16 * (by + 0.5) - 192),
               hold=0.10, after=0.06)
    print(f"  点灯耗时 {time.time()-t0:.1f}s", flush=True)

    a0 = P.grab_np()
    ms = [t for t in targets if yellow_at(a0, t[0], t[1], sc) <= 12]
    print(f"  [立即终检]     未确认 {len(ms)}/{len(targets)}", flush=True)

    acc = 0.0
    for tw in [0.3, 0.6, 1.0, 1.5]:
        time.sleep(tw - acc); acc = tw
        a = P.grab_np()
        ms = [t for t in targets if yellow_at(a, t[0], t[1], sc) <= 12]
        print(f"  [等待≈{tw:.1f}s] 未确认 {len(ms)}/{len(targets)}", flush=True)
        if tw == 1.5:
            Image.fromarray(a.astype("uint8")).save("/tmp/exp3_after_taps.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
