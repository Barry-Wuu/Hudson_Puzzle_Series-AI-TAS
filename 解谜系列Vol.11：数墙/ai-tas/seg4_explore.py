#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""seg4 准备探索：切到 むずかしい -> 进第1关 -> 打开オプション -> 原分辨率截 BGM 行，
定位 1/2/3 按钮的 x 中心（用于 BGM3 切换）。不改任何设置。"""
import os
import sys
import time

os.environ.setdefault("V11_DIFF", "むずかしい")
HERE = "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas"
sys.path.insert(0, HERE)
import ds
import mode2_fast as M
import numpy as np
from PIL import Image

M.OUT = "/tmp/seg4_prep"
os.makedirs(M.OUT, exist_ok=True)

OPT_X = 215
OPT_YS = (372, 374, 378, 382, 368)


def open_option():
    for y in OPT_YS:
        ds.tap_local(OPT_X, y, after=1.0)
        if M.state() == "option":
            return True
    return False


def main():
    print("=== seg4 explore (むずかしい) ===", flush=True)
    if not M.ensure_select():
        print("ensure_select FAIL", flush=True)
        return 1
    print("is_futsuu?", M.is_select_diff("むずかしい"), flush=True)
    M.goto_level_cell(1)
    ds.press("x", wait=0.3, hold=0.05)
    for _ in range(10):
        st = M.poll(("play", "tut", "clear"), timeout=8)
        if st == "play":
            break
        ds.press("x", wait=0.5, hold=0.05)
        time.sleep(0.3)
    print("enter state:", M.state(), flush=True)
    if not open_option():
        print("open option FAIL", flush=True)
        return 1
    im = ds.grab(None)
    im.save(f"{M.OUT}/option_full.png")
    print("option state:", M.state(), flush=True)
    # 裁剪 BGM 行（原图大致 y 250..280）
    crop = im.crop((0, 245, 256, 285)).convert("RGB")
    crop.save(f"{M.OUT}/bgm_row.png")
    arr = np.asarray(crop).astype(int)
    R, G, B = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
    cyan = (B > 160) & (G > 140) & (R < 130)
    dark = (R < 110) & (G < 110) & (B < 110)
    def centers(mask):
        cols = np.where(mask.sum(axis=0) > 5)[0]
        if len(cols) == 0:
            return []
        cl = []
        for x in cols:
            if cl and x - cl[-1][-1] <= 8:
                cl[-1].append(x)
            else:
                cl.append([x])
        return [int(np.mean(c)) for c in cl]
    print("cyan centers (selected):", centers(cyan), flush=True)
    print("dark centers (other digits):", centers(dark), flush=True)
    print("DONE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
