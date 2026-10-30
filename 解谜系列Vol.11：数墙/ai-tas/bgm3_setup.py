#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""seg4 开录前 BGM3 设置（每段执行，不录制）。むずかしい 用 BGM3。

按钮标定（2026-10-26 6x 放大实测，むずかしい オプション菜单 BGM 行 y≈263）：
  OFF≈132 / 1≈155 / 2≈180 / 3≈205，间距 25px。
  「3」点 (205,263)，高亮判定框 (193,252)-(217,276)（同 bgm2 的亮度>125 判据）。

流程：ensure_select(むずかしい) -> 进第1关 -> 右侧菜单 -> オプション -> 点 BGM「3」
      -> 校验高亮 -> 問題選択へ -> はい -> 回选关页 -> 写 /tmp/v11_bgm_ready
失败不写哨兵并 exit 1（rec_seg4.sh 据此中止，防 BGM2 误录）。
"""
import os
import sys
import time

import numpy as np

os.environ.setdefault("V11_DIFF", "むずかしい")
HERE = "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas"
sys.path.insert(0, HERE)
import ds
import mode2_fast as M

M.OUT = "/tmp/seg4_prep"
os.makedirs(M.OUT, exist_ok=True)

OPT_X = 215           # 右侧菜单「オプション」x
OPT_YS = (372, 374, 378, 382, 368)
BGM_XY = (205, 263)   # オプション菜单里 BGM 行「3」
BGM_BOX = (193, 252, 217, 276)   # 「3」按钮判定区域
SENTINEL = "/tmp/v11_bgm_ready"


def shot(n, tag=""):
    im = ds.grab(None)
    im.save(f"{M.OUT}/bgm3_setup_{n:02d}.png")
    print(f"  [bgm3] shot{n:02d} state={M.state()} {tag}", flush=True)


def bgm3_selected():
    im = ds.grab(None).crop(BGM_BOX).convert("L")
    return float(np.asarray(im).astype(int).mean()) > 125


def confirm_bgm3(max_checks=4):
    """limiter ON 下高亮渲染有延迟：点完先重查几次，别急着重点。"""
    for _ in range(max_checks):
        if bgm3_selected():
            return True
        time.sleep(0.6)
    return bgm3_selected()


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
    print("=== bgm3 setup ===", flush=True)
    for attempt in range(3):
        print(f"--- attempt {attempt+1} ---", flush=True)
        if not enter_first_level():
            print("  [bgm3] enter lvl1 fail", flush=True)
            continue
        shot(1, "in lvl1")
        if not open_option():
            print("  [bgm3] open option fail", flush=True)
            for _ in range(8):
                if M.state() == "select":
                    break
                ds.press("x", wait=0.6, hold=0.05)
                time.sleep(0.3)
            continue
        shot(2, "option open")
        for t in range(3):
            ds.tap_local(*BGM_XY, after=0.8)
            if confirm_bgm3():
                break
            print(f"  [bgm3] tap3 not confirmed (try {t+1})", flush=True)
        shot(3, "after tap BGM3")
        if not bgm3_selected():
            print("  [bgm3] BGM3 select fail", flush=True)
            back_to_select()
            continue
        print("  [bgm3] BGM3 confirmed", flush=True)
        if back_to_select():
            print("  [bgm3] back to select OK", flush=True)
            open(SENTINEL, "w").close()
            print("BGM3_SETUP_OK", flush=True)
            return 0
        print("  [bgm3] back_to_select fail", flush=True)
    print("BGM3_SETUP_FAIL", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
