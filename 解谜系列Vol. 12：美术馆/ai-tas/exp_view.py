#!/usr/bin/env python3
"""诊断 18x10 大盘 sc>0 块视口定位失败的真实原因（v2）。

v1 失败原因：游戏按关记忆盘面，Q31 上次已解 → 进关即判通关 → 停在通关页，
方向键失效，三次 best_view 完全相同。

v2：进关后无条件 reset_level() 复位到初始盘（只有线索、无灯），确保在游玩页，
再对比两种按键剂量的滚动结果。
"""
import sys, time
sys.path.insert(0, ".")
import numpy as np
from PIL import Image
import play_akari_seg3 as P
import ds


def best_view(a, pz):
    w, h = pz["w"], pz["h"]
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


def enter_fresh(n, pz, tries=3):
    """进关并复位到初始盘面，返回是否成功停在游玩页。"""
    for k in range(tries):
        if not P.in_select_page():
            P.escape_to_select()
            time.sleep(1.0)
        P.goto_level(n)
        time.sleep(2.0)
        # 若落在通关页 / 选关页，按 x 回退再重来
        if not P.in_play_page():
            print(f"  尝试{k+1}: 未在游玩页，按 x 回退", flush=True)
            for _ in range(4):
                ds.press("x", wait=1.0)
                if P.in_play_page():
                    break
                if P.in_select_page():
                    break
            time.sleep(1.0)
            continue
        # 在游玩页：无条件复位（清掉上次残留解）
        print(f"  尝试{k+1}: 在游玩页，reset_level", flush=True)
        P.reset_level()
        time.sleep(2.0)
        if P.in_play_page():
            return True
    return False


def main():
    n = 31
    pz = P._SEQ[n - 1]
    print(f"=== Q{n} size={pz['w']}x{pz['h']} bulbs={len(pz['bulbs'])} ===", flush=True)

    if not P.in_select_page():
        P.escape_to_select()
        time.sleep(1.0)
    print("起点 in_select_page =", P.in_select_page(), flush=True)

    if not enter_fresh(n, pz):
        print("!! 无法进入干净的游玩页", flush=True)
        return 1

    a = P.grab_np()
    print(f"[复位后] yellow={P.board_yellow_count()} best_view={best_view(a, pz)[:3]}", flush=True)
    Image.fromarray(a.astype("uint8")).save("/tmp/exp2_init.png")

    print("\n--- 实验1: wait=0.10 hold=0.04 → sc=8 ---", flush=True)
    t0 = time.time(); scroll(0.10, 0.04, 0, 8, pz)
    print(f"  按键耗时 {time.time()-t0:.1f}s in_play={P.in_play_page()}", flush=True)
    time.sleep(0.4)
    a = P.grab_np()
    print(f"  best_view={best_view(a, pz)[:3]}", flush=True)
    Image.fromarray(a.astype("uint8")).save("/tmp/exp2_fast_s8.png")

    print("\n--- 实验2: wait=0.30 hold=0.02 → sc=0 复位 ---", flush=True)
    t0 = time.time(); scroll(0.30, 0.02, 0, 0, pz)
    print(f"  按键耗时 {time.time()-t0:.1f}s", flush=True)
    time.sleep(0.4)
    a = P.grab_np()
    print(f"  best_view={best_view(a, pz)[:3]}", flush=True)

    print("\n--- 实验3: wait=0.30 hold=0.02 → sc=8 ---", flush=True)
    t0 = time.time(); scroll(0.30, 0.02, 0, 8, pz)
    print(f"  按键耗时 {time.time()-t0:.1f}s", flush=True)
    time.sleep(0.4)
    a = P.grab_np()
    print(f"  best_view={best_view(a, pz)[:3]}", flush=True)
    Image.fromarray(a.astype("uint8")).save("/tmp/exp2_slow_s8.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
