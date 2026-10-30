#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Seg2 触摸解禁时刻精确测量。

★ 之前混淆了两个量（必须分开测）：
  1. **灯格是否被接受**（灯所在的格从黑变亮）→ 反映触摸是否解禁
  2. **全盘暗格数**（光照扩散后的未照亮格）→ 反映光照动画进度 & 通关判定
之前 wait=1.0 时暗格完全没降（灯也没亮），
wait=3.0 时暗格降 81%（部分灯被接受）。
本探针：进关后**每隔 0.4s 点一颗灯**，每点完立刻读该灯格亮度，
从而直接标定「触摸解禁时刻」。
"""
import json
import os
import time

import numpy as np

import ds

PUZZLES = os.path.join(os.path.dirname(__file__), "..", "validation", "puzzles.json")
X0, Y0, P = 16, 208, 16
SEL_ROW_Y = [278, 294, 310, 326]


def exp_walls(pz):
    return ["".join("." if pz["given"][y * pz["w"] + x] == 45 else "W"
                    for x in range(pz["w"])) for y in range(pz["h"])]


def match(a, exp, w, h):
    m = 0
    for r in range(h):
        for c in range(w):
            cx, cy = int(X0 + P * (c + 0.5)), int(Y0 + P * (r + 0.5))
            cell = a[cy - 5:cy + 5, cx - 5:cx + 5].reshape(-1, 3)
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


def bulb_bright(a, nx, ny):
    """该格（NDS坐标）是否已点亮（亮度高）。"""
    cy = ny + 192
    reg = a[cy - 6:cy + 6, nx - 6:nx + 6]
    return float(reg.mean())


def main():
    d = json.load(open(PUZZLES))
    pz = d["やさしい"][0]
    exp = exp_walls(pz)
    w, h = pz["w"], pz["h"]
    pts = [(int(X0 + P * (x + 0.5)), int(Y0 + P * (y + 0.5) - 192))
           for (x, y) in pz["bulbs"]]

    for trial in range(2):
        # 确保在选关页
        for _ in range(3):
            tap_level(1)
            ds.press("x", hold=0.14, wait=0.3)
            a = np.asarray(ds.grab("").convert("RGB")).astype(int)
            if match(a, exp, w, h) >= w * h - 2:
                break
            back_to_select()
        else:
            print("进关失败")
            return
        t0 = time.time()
        print(f"--- trial{trial}: 逐灯点，每 0.4s 一颗 ---")
        for i, (nx, ny) in enumerate(pts):
            # 等到该点
            while time.time() - t0 < i * 0.4:
                time.sleep(0.05)
            b0 = bulb_bright(a, nx, ny)
            ds.tap(nx, ny, hold=0.10, after=0.06, gap=0.04)
            time.sleep(0.25)
            a = np.asarray(ds.grab("").convert("RGB")).astype(int)
            b1 = bulb_bright(a, nx, ny)
            print(f"  t={time.time()-t0:5.2f}s 灯{i+1:2d} ({nx},{ny}) "
                  f"亮度 {b0:6.1f}→{b1:6.1f} {'★生效' if b1 > b0 + 15 else '✗'}")
        time.sleep(1.5)
        a = np.asarray(ds.grab(f"tt{trial}").convert("RGB")).astype(int)
        reg = a[Y0:Y0 + h * P, X0:X0 + w * P]
        dk = int(((reg[:, :, 0] < 60) & (reg[:, :, 1] < 60) & (reg[:, :, 2] < 60)).sum())
        print(f"  全盘暗格 = {dk}  {'★通关' if dk < 120 else ''}")
        back_to_select()


if __name__ == "__main__":
    main()
