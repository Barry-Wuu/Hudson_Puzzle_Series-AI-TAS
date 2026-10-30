#!/usr/bin/env python3
"""Vol.12 单关返回时序探针：从当前选关页进 Q20（已清），点灯通关，
随后精确测量返回选关页所需的 x 次数与时机。仅用于调参，不改存档逻辑。"""
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import ds

PUZZLES = os.path.join(os.path.dirname(__file__), "..", "validation", "puzzles.json")
X0, Y0, P = 24, 216, 24


def bulb_points(pz):
    return [(int(X0 + P * (x + 0.5)), int(Y0 + P * (y + 0.5) - 192)) for (x, y) in pz["bulbs"]]


def board_dark_count(im):
    a = np.asarray(im.convert("RGB")).astype(int)
    reg = a[Y0:Y0 + 6 * P, X0:X0 + 6 * P]
    return int(((reg[:, :, 0] < 60) & (reg[:, :, 1] < 60) & (reg[:, :, 2] < 60)).sum())


def is_select(im):
    """单帧判定是否在选关页（不 sleep）。"""
    a = np.asarray(im.convert("RGB")).astype(int)
    rows_ok = 0
    for y in (290, 310):
        m = (a[y][:, 2] > 90) & (a[y][:, 0] < 90) & (a[y][:, 1] > 70)
        runs, s = 0, None
        for i, v in enumerate(m):
            if v and s is None:
                s = i
            if not v and s is not None:
                if i - s > 12:
                    runs += 1
                s = None
        if s is not None and 255 - s > 12:
            runs += 1
        if runs >= 9:
            rows_ok += 1
    return rows_ok >= 1


def main():
    data = json.load(open(PUZZLES))
    pz = data["入門"][19]  # Q20
    print("Q20 灯数=", len(pz["bulbs"]), flush=True)
    from play_akari import goto, wait_select
    if not wait_select(5):
        print("不在选关页，goto(20)…", flush=True)
        if goto(20) != 20:
            print("FAIL nav", flush=True)
            return
    else:
        goto(20)
    print("进关…", flush=True)
    ds.press("x", wait=1.0)
    time.sleep(1.0)
    ds.tap_batch(bulb_points(pz), gap=0.02, hold=0.06, after=0.04)
    t0 = time.time()
    cleared = False
    while time.time() - t0 < 4:
        time.sleep(0.3)
        if board_dark_count(ds.grab("")) < 120:
            cleared = True
            break
    print("cleared=", cleared, "t_clear=%.2fs" % (time.time() - t0), flush=True)
    time.sleep(3.0)
    print("--- 返回探针：先按 1 次 x ---", flush=True)
    t_start = time.time()
    ds.press("x", wait=0.4)
    last = None
    for i in range(50):
        el = time.time() - t_start
        sel = is_select(ds.grab(""))
        if sel != last:
            print("[%.2fs] select=%s" % (el, sel), flush=True)
            last = sel
        if sel and i > 1:
            print("=> 1次x 即可回选关页，耗时 %.2fs" % el, flush=True)
            return
        time.sleep(0.25)
    print("[12.5s] 仍非选关页，补按第2次 x", flush=True)
    ds.press("x", wait=0.4)
    for i in range(40):
        el = time.time() - t_start
        sel = is_select(ds.grab(""))
        if sel and i > 1:
            print("=> 2次x 回选关页，累计 %.2fs" % el, flush=True)
            return
        time.sleep(0.25)
    print("[EOF] 仍未到选关页", flush=True)


if __name__ == "__main__":
    main()
