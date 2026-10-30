#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探针：确认 ふつう 第1关是否有教程。
只进第1关并采样状态，不填格、不录屏。打印 ENTER STATE 与后续几帧状态轨迹。
"""
import os
import sys
import time

os.environ["V11_DIFF"] = "ふつう"
HERE = "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas"
sys.path.insert(0, HERE)
import ds
import mode2_fast as M

M.OUT = "/tmp/seg3_clear"
os.makedirs(M.OUT, exist_ok=True)

print("=== probe: ふつう 第1关 教程检查 ===", flush=True)
print("ensure_select:", M.ensure_select(), flush=True)
print("is_select_diff(ふつう):", M.is_select_diff("ふつう"), flush=True)
M.goto_level_cell(1)
ds.press("x", wait=0.3, hold=0.05)
st = M.poll(("play", "tut", "clear"), timeout=8)
print("LVL1 ENTER STATE:", st, flush=True)
traj = []
for i in range(8):
    traj.append(M.state())
    time.sleep(1.0)
print("LVL1 post-enter trajectory:", traj, flush=True)
# 回选关，避免破坏存档
M.clear_to_select() if hasattr(M, "clear_to_select") else None
for _ in range(10):
    if M.state() == "select":
        break
    ds.press("x", wait=0.5, hold=0.05)
    time.sleep(0.3)
print("END state:", M.state(), flush=True)
print("PROBE_DONE", flush=True)
