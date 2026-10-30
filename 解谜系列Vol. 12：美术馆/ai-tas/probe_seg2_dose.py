#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Seg2（やさしい 10×10）剂量探测 v2：严谨版。

v1 的问题：进关失败时抓到的是**预览区**（墙匹配 24/100），数据被污染。
v2 改进：
  * 进关后先校验墙匹配 == 100，不合格则重进（最多 3 次）；
  * 通关判据用「暗格数」（像入門），不用亮度累加；
  * 每档独立从选关页进入。
"""
import json
import os
import sys
import time

import numpy as np

import ds

PUZZLES = os.path.join(os.path.dirname(__file__), "..", "validation", "puzzles.json")
X0, Y0, P = 16, 208, 16
HALF = 5
SEL_ROW_Y = [278, 294, 310, 326]
SEL_COL_X0 = 19
SEL_COL_DX = 24


def exp_walls(pz):
    return ["".join("." if pz["given"][y * pz["w"] + x] == 45 else "W"
                    for x in range(pz["w"])) for y in range(pz["h"])]


def got_walls(a, w, h):
    out = []
    for r in range(h):
        row = ""
        for c in range(w):
            cx, cy = int(X0 + P * (c + 0.5)), int(Y0 + P * (r + 0.5))
            cell = a[cy - HALF:cy + HALF, cx - HALF:cx + HALF].reshape(-1, 3)
            blue = ((cell[:, 2] > 100) & (cell[:, 2] > cell[:, 0] + 35)).mean()
            row += "W" if blue > 0.35 else "."
        out.append(row)
    return out


def match(a, exp, w, h):
    g = got_walls(a, w, h)
    return sum(x == y for r1, r2 in zip(g, exp) for x, y in zip(r1, r2))


def dark_count(a, w, h):
    reg = a[Y0:Y0 + h * P, X0:X0 + w * P]
    return int(((reg[:, :, 0] < 60) & (reg[:, :, 1] < 60) & (reg[:, :, 2] < 60)).sum())


def bulb_pts(pz):
    return [(int(X0 + P * (x + 0.5)), int(Y0 + P * (y + 0.5) - 192))
            for (x, y) in pz["bulbs"]]


def tap_level(n):
    row, col = (n - 1) // 10, (n - 1) % 10
    if row >= len(SEL_ROW_Y):
        return False
    ds.tap_local(SEL_COL_X0 + SEL_COL_DX * col, SEL_ROW_Y[row], after=1.8)
    return True


def back_to_select():
    """从关卡内退回 やさしい 选关页。"""
    for _ in range(2):
        ds.press("Return", wait=1.6)
        ds.tap_local(197, 215, after=1.6)
        ds.press("x", wait=1.6)
        time.sleep(0.8)
        a = np.asarray(ds.grab("").convert("RGB")).astype(int)
        # 选关页特征：下半部有青色数字格
        R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
        m = (B > 110) & (G > 80) & (R < 90)
        m[:265, :] = False
        if m.sum() > 800:
            return True
    return False


def enter_confirmed(n, exp, w, h, wait, tries=3):
    """进关并确认墙布局匹配。返回 (ok, 墙匹配数)。"""
    for t in range(tries):
        tap_level(n)
        ds.press("x", wait=wait)
        a = np.asarray(ds.grab(f"e_{n}_{t}").convert("RGB")).astype(int)
        m = match(a, exp, w, h)
        if m >= w * h - 2:
            return True, m
        print(f"    (重进 {t+1}: 墙匹配 {m}/{w*h})")
        back_to_select()
    return False, m


def main():
    d = json.load(open(PUZZLES))
    pz = d["やさしい"][0]
    exp = exp_walls(pz)
    w, h = pz["w"], pz["h"]
    pts = bulb_pts(pz)
    print(f"Q1 {w}x{h} 灯数 {len(pts)}  暗格基线待测")

    mode = sys.argv[1] if len(sys.argv) > 1 else "after"
    WAIT = 7.0

    if mode == "after":
        for after in (0.06, 0.10, 0.14, 0.18, 0.22, 0.26):
            ok, m = enter_confirmed(1, exp, w, h, WAIT)
            if not ok:
                print(f"after={after}: 进关失败，跳过")
                continue
            a0 = np.asarray(ds.grab("").convert("RGB")).astype(int)
            dk0 = dark_count(a0, w, h)
            ds.tap_batch(pts, gap=0.04, hold=0.10, after=after)
            time.sleep(1.5)
            a1 = np.asarray(ds.grab(f"lit_{after}").convert("RGB")).astype(int)
            dk1 = dark_count(a1, w, h)
            print(f"after={after}: 墙{m}/{w*h} 暗格 {dk0}→{dk1}  "
                  f"{'★通关' if dk1 < 120 else ''}")
            back_to_select()

    elif mode == "unlock":
        for wait in (2.0, 3.0, 4.0, 5.0, 6.0):
            ok, m = enter_confirmed(1, exp, w, h, wait)
            if not ok:
                print(f"wait={wait}: 进关失败")
                continue
            a0 = np.asarray(ds.grab("").convert("RGB")).astype(int)
            dk0 = dark_count(a0, w, h)
            ds.tap_batch(pts, gap=0.04, hold=0.10, after=0.26)
            time.sleep(1.5)
            a1 = np.asarray(ds.grab(f"u_{wait}").convert("RGB")).astype(int)
            dk1 = dark_count(a1, w, h)
            print(f"wait={wait}s: 墙{m}/{w*h} 暗格 {dk0}→{dk1}  "
                  f"{'★通关' if dk1 < 120 else ''}")
            back_to_select()

    elif mode == "hold":
        for hold in (0.06, 0.10, 0.14, 0.20):
            ok, m = enter_confirmed(1, exp, w, h, WAIT)
            if not ok:
                print(f"hold={hold}: 进关失败")
                continue
            a0 = np.asarray(ds.grab("").convert("RGB")).astype(int)
            dk0 = dark_count(a0, w, h)
            ds.tap_batch(pts, gap=0.04, hold=hold, after=0.26)
            time.sleep(1.5)
            a1 = np.asarray(ds.grab(f"h_{hold}").convert("RGB")).astype(int)
            dk1 = dark_count(a1, w, h)
            print(f"hold={hold}: 暗格 {dk0}→{dk1}  {'★通关' if dk1 < 120 else ''}")
            back_to_select()


if __name__ == "__main__":
    main()
