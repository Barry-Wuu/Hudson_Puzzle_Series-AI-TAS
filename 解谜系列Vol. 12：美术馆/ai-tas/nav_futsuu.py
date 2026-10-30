#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""冷启动导航：title -> 本編 -> slot -> diff -> ふつう 选关页。"""
import sys
import time

from PIL import Image

import ds
import play_akari_seg3 as P
import state2


def det():
    return state2.detect(Image.fromarray(P.grab_np().astype("uint8")))


def nav(max_step=24):
    for step in range(max_step):
        st = det()
        print(f"[{step}] state={st}", flush=True)
        if st == "select":
            cc = P.cursor_cell()
            print("  选关页就绪 cursor=", cc, flush=True)
            return True
        if st == "title":
            ds.tap(128, 40, after=1.6)          # 本編を始める
        elif st == "slot":
            ds.tap(128, 60, after=1.0)          # 槽 1
            ds.press("x", wait=1.2)             # はい
        elif st == "diff":
            ds.tap(128, 108, after=1.2)         # ふつう
        elif st == "tut":
            ds.press("x", wait=1.0)
        elif st == "menu":
            ds.press("x", wait=1.0)
        elif st == "play":
            P.escape_to_select()
            time.sleep(1.2)
        else:
            ds.press("x", wait=0.9)
        time.sleep(0.8)
    return False


if __name__ == "__main__":
    ok = nav()
    print("NAV_OK" if ok else "NAV_FAIL")
    if ok:
        im = P.grab_np()
        Image.fromarray(im.astype("uint8")).save("/tmp/nav_ok.png")
    sys.exit(0 if ok else 1)
