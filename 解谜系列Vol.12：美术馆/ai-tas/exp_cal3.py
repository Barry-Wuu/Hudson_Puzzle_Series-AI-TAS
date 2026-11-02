#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""归零起点滚动映射标定：顶死后逐次 Right/Down，实测 (dc,dr)。"""
import sys
import time

from PIL import Image

import ds
import play_akari_seg3 as P
import state2


def ensure_select():
    for _ in range(10):
        im = P.grab_np()
        img = Image.fromarray(im.astype("uint8"))
        st = state2.detect(img)
        if st == "select" and P.cursor_cell() is not None:
            return True
        if st == "play" or P.in_play_page(im):
            P.escape_to_select()
            time.sleep(1.4)
            continue
        ds.press("x", wait=1.0)
        time.sleep(0.6)
    return False


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 31
    pz = P._SEQ[n - 1]
    w, h = pz["w"], pz["h"]
    print(f"=== 归零映射标定 Q{n} ({w}x{h}) ===", flush=True)
    if not ensure_select():
        print("!! 无选关页"); return 1
    if not P.goto_level(n):
        print("!! goto 失败"); return 1
    time.sleep(1.6)
    if not P.in_play_page():
        for _ in range(6):
            ds.press("x", wait=1.0)
            if P.in_play_page():
                break
    P.reset_level()
    time.sleep(4.0)

    def home():
        for _ in range(h + 2):
            ds.press("Up", wait=0.10, hold=0.04)
        for _ in range(w + 2):
            ds.press("Left", wait=0.10, hold=0.04)
        time.sleep(0.45)

    def off(tag):
        a = P.grab_np()
        scr = P._scr_walls(a)
        m, tot = P.vp_score(a, pz, 0, 0, scr)
        rt, bdc, bdr = P._vp_best(a, pz, scr)
        print(f"  [{tag}] 目标(0,0)分={m/tot*100:.1f}%  best=({bdc},{bdr}) {rt*100:.1f}%", flush=True)
        return bdc, bdr

    home()
    off("home")

    print("-- 归零后 Right 逐次 --", flush=True)
    home()
    for k in range(1, 15):
        ds.press("Right", wait=0.10, hold=0.04)
        time.sleep(0.22)
        a = P.grab_np()
        scr = P._scr_walls(a)
        rt, bdc, bdr = P._vp_best(a, pz, scr)
        m0, t0 = P.vp_score(a, pz, 0, 0, scr)
        print(f"  R{k}: best=({bdc},{bdr}) {rt*100:.1f}%  (0,0)分={m0/t0*100:.1f}%", flush=True)

    print("-- 归零后 Down 逐次 --", flush=True)
    home()
    for k in range(1, 13):
        ds.press("Down", wait=0.10, hold=0.04)
        time.sleep(0.22)
        a = P.grab_np()
        scr = P._scr_walls(a)
        rt, bdc, bdr = P._vp_best(a, pz, scr)
        print(f"  D{k}: best=({bdc},{bdr}) {rt*100:.1f}%", flush=True)

    P.escape_to_select()
    print("=== DONE ===", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
