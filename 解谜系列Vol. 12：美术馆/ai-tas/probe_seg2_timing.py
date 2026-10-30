#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Seg2 精确时序探测：
  A. 盘面动画完成时刻（墙布局首次 100/100 匹配）—— 录制不能切进动画
  B. 触摸解禁时刻（点灯真正生效的最早 wait）
逐帧采样，输出时间轴。
"""
import json
import os
import time

import numpy as np

import ds

PUZZLES = os.path.join(os.path.dirname(__file__), "..", "validation", "puzzles.json")
X0, Y0, P = 16, 208, 16
HALF = 5
SEL_ROW_Y = [278, 294, 310, 326]


def exp_walls(pz):
    return ["".join("." if pz["given"][y * pz["w"] + x] == 45 else "W"
                    for x in range(pz["w"])) for y in range(pz["h"])]


def match(a, exp, w, h):
    m = 0
    for r in range(h):
        for c in range(w):
            cx, cy = int(X0 + P * (c + 0.5)), int(Y0 + P * (r + 0.5))
            cell = a[cy - HALF:cy + HALF, cx - HALF:cx + HALF].reshape(-1, 3)
            blue = ((cell[:, 2] > 100) & (cell[:, 2] > cell[:, 0] + 35)).mean()
            m += 1 if (blue > 0.35) == (exp[r][c] == "W") else 0
    return m


def tap_level(n):
    row, col = (n - 1) // 10, (n - 1) % 10
    ds.tap_local(19 + 24 * col, SEL_ROW_Y[row], after=1.5)


def back_to_select():
    for _ in range(2):
        ds.press("Return", wait=1.6)
        ds.tap_local(197, 215, after=1.6)
        ds.press("x", wait=1.6)
        time.sleep(0.6)
        a = np.asarray(ds.grab("").convert("RGB")).astype(int)
        R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
        m = (B > 110) & (G > 80) & (R < 90)
        m[:265, :] = False
        if m.sum() > 800:
            return True
    return False


def main():
    d = json.load(open(PUZZLES))
    pz = d["やさしい"][0]
    exp = exp_walls(pz)
    w, h = pz["w"], pz["h"]
    pts = [(int(X0 + P * (x + 0.5)), int(Y0 + P * (y + 0.5) - 192))
           for (x, y) in pz["bulbs"]]

    print("=== A. 盘面动画时间轴（进关后逐 0.4s 采样墙匹配）===")
    for trial in range(2):
        tap_level(1)
        t0 = time.time()
        ds.press("x", hold=0.14, wait=0.0)
        seq = []
        for i in range(26):
            a = np.asarray(ds.grab("").convert("RGB")).astype(int)
            m = match(a, exp, w, h)
            seq.append((round(time.time() - t0, 2), m))
            time.sleep(0.4)
        print(f"trial{trial}: " + " ".join(f"{t}s={m}" for t, m in seq))
        back_to_select()

    print("\n=== B. 触摸解禁（进关后等 wait 再点灯，看暗格是否降到 0）===")
    for wait in (1.0, 1.5, 2.0, 2.5, 3.0):
        # 确保从选关页进关
        for _ in range(3):
            tap_level(1)
            ds.press("x", hold=0.14, wait=wait)
            a = np.asarray(ds.grab("").convert("RGB")).astype(int)
            if match(a, exp, w, h) >= w * h - 2:
                break
            back_to_select()
        else:
            print(f"wait={wait}: 进关失败")
            continue
        dk0 = int(((a[Y0:Y0 + h * P, X0:X0 + w * P, 0] < 60) &
                   (a[Y0:Y0 + h * P, X0:X0 + w * P, 1] < 60) &
                   (a[Y0:Y0 + h * P, X0:X0 + w * P, 2] < 60)).sum())
        ds.tap_batch(pts, gap=0.04, hold=0.10, after=0.10)
        time.sleep(1.2)
        a2 = np.asarray(ds.grab(f"uk_{wait}").convert("RGB")).astype(int)
        reg = a2[Y0:Y0 + h * P, X0:X0 + w * P]
        dk1 = int(((reg[:, :, 0] < 60) & (reg[:, :, 1] < 60) & (reg[:, :, 2] < 60)).sum())
        print(f"wait={wait}s: 暗格 {dk0}→{dk1}  {'★通关' if dk1 < 120 else '✗未生效'}")
        back_to_select()


if __name__ == "__main__":
    main()
