#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""seg3 开录前 BGM2 设置（每段执行，不录制）。

已实测：BGM 设置不随 SIGTERM 退出持久化（SRAM 不刷盘），故每段开录前重切一次。
流程：ensure_select(V11_DIFF) -> 进第1关 -> 右侧菜单 -> オプション -> 点 BGM「2」
      -> 校验高亮 -> 問題選択へ -> はい -> 回选关页 -> 写 /tmp/v11_bgm_ready
失败则不写哨兵并 exit 1（rec_seg3.sh 据此中止该段，防 BGM1 开录）。
"""
import os
import sys
import time

import numpy as np

os.environ.setdefault("V11_DIFF", "ふつう")
HERE = "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas"
sys.path.insert(0, HERE)
import ds
import mode2_fast as M

M.OUT = "/tmp/seg3_clear"
os.makedirs(M.OUT, exist_ok=True)

OPT_X = 215           # 右侧菜单「オプション」x
OPT_YS = (372, 374, 378, 382, 368)
BGM2_XY = (178, 263)  # オプション菜单里 BGM 行「2」
BGM2_BOX = (168, 252, 192, 276)   # 「2」按钮判定区域
SENTINEL = "/tmp/v11_bgm_ready"


def shot(n, tag=""):
    im = ds.grab(None)
    im.save(f"/tmp/seg3_clear/bgm_setup_{n:02d}.png")
    print(f"  [bgm] shot{n:02d} state={M.state()} {tag}", flush=True)


def bgm2_selected():
    im = ds.grab(None).crop(BGM2_BOX).convert("L")
    return float(np.asarray(im).astype(int).mean()) > 125


def confirm_bgm2(max_checks=4):
    """limiter ON 下高亮渲染有延迟：点完先重查几次，别急着重点。"""
    for _ in range(max_checks):
        if bgm2_selected():
            return True
        time.sleep(0.6)
    return bgm2_selected()


def open_option():
    for y in OPT_YS:
        ds.tap_local(OPT_X, y, after=1.0)
        if M.state() == "option":
            return True
    return False


def enter_first_level():
    if not M.ensure_select():
        return False
    M.goto_level_cell(1)
    ds.press("x", wait=0.3, hold=0.05)
    for _ in range(10):
        st = M.poll(("play", "tut", "clear"), timeout=8)
        if st == "play":
            return True
        if st == "tut":
            # 教程不应出现（全局 done）；若出现按 x 推进
            ds.press("x", wait=0.5, hold=0.05)
            time.sleep(0.3)
            continue
        ds.press("x", wait=0.5, hold=0.05)
        time.sleep(0.3)
    return M.state() == "play"


def back_to_select():
    """問題選択へ -> はい -> 等回选关页。"""
    ds.tap_local(200, 214, after=1.2)   # 問題選択へ
    ds.press("x", wait=1.2, hold=0.05)  # A = はい（确认框）
    for _ in range(14):
        st = M.state()
        if st == "select":
            return True
        ds.press("x", wait=0.8, hold=0.05)
        time.sleep(0.4)
    return M.state() == "select"


def main():
    print("=== bgm2 setup ===", flush=True)
    for attempt in range(3):
        print(f"--- attempt {attempt+1} ---", flush=True)
        if not enter_first_level():
            print("  [bgm] enter lvl1 fail", flush=True)
            continue
        shot(1, "in lvl1")
        if not open_option():
            print("  [bgm] open option fail", flush=True)
            # 兜底：回选关页重试
            for _ in range(8):
                if M.state() == "select":
                    break
                ds.press("x", wait=0.6, hold=0.05)
                time.sleep(0.3)
            continue
        shot(2, "option open")
        for t in range(3):
            ds.tap_local(*BGM2_XY, after=0.8)
            if confirm_bgm2():
                break
            print(f"  [bgm] tap2 not confirmed (try {t+1})", flush=True)
        shot(3, "after tap BGM2")
        if not bgm2_selected():
            print("  [bgm] BGM2 select fail", flush=True)
            back_to_select()
            continue
        print("  [bgm] BGM2 confirmed", flush=True)
        if back_to_select():
            print("  [bgm] back to select OK", flush=True)
            open(SENTINEL, "w").close()
            print("BGM2_SETUP_OK", flush=True)
            return 0
        print("  [bgm] back_to_select fail", flush=True)
    print("BGM2_SETUP_FAIL", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
