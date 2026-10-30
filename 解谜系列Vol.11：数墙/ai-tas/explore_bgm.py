#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探索：定位 数墙 选项菜单里的 BGM 曲目切换项。
流程：ensure_select(ふつう) -> 选关页截图 -> 进第1关 -> play 截图 ->
按 Return 开选项菜单 -> 截图 -> 逐次 Down 截图，映射菜单项。
截图存 /tmp/bgm_explore/NN.png。
"""
import os
import sys
import time

os.environ["V11_DIFF"] = "ふつう"
HERE = "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas"
sys.path.insert(0, HERE)
import ds
import mode2_fast as M

OUT = "/tmp/bgm_explore"
os.makedirs(OUT, exist_ok=True)


def shot(n, tag=""):
    im = ds.grab(None)
    im.save(os.path.join(OUT, f"{n:02d}.png"))
    print(f"shot {n:02d} state={M.state()} {tag}", flush=True)


print("=== explore bgm ===", flush=True)
print("ensure_select:", M.ensure_select(), flush=True)
shot(1, "select")
M.goto_level_cell(1)
ds.press("x", wait=0.3, hold=0.05)
for _ in range(6):
    st = M.poll(("play", "tut", "clear"), timeout=8)
    if st == "play":
        break
    ds.press("x", wait=0.4, hold=0.05)
    time.sleep(0.3)
shot(2, "play")
ds.press("Return", wait=1.0, hold=0.05)   # 开选项/暂停菜单
shot(3, "option")
for i in range(1, 7):
    ds.press("Down", wait=0.8, hold=0.05)
    shot(3 + i, f"option_down{i}")
print("DONE", flush=True)
