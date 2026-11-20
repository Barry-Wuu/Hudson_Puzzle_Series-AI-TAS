#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""冷启动直达 むずかしい 选关页（从标题画面出发）。"""
import os, sys, time
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ds, nav18 as N, slither18 as s18, record18_v4 as V, record_big36 as RB, slither_big36 as SB

def main():
    ds.ensure_window()
    # 1) 标题 -> 启动提示：连按 x
    for _ in range(3):
        ds.press("x", wait=1.5)
        if s18.is_select_ui():
            break
    # 2) 玩家选择：点「うえ」槽（左）
    if not s18.is_select_ui():
        ds.tap(60, 42, hold=0.15, after=3.0)
    # 3) 主菜单 -> スタート
    for _ in range(5):
        if s18.is_select_ui():
            break
        ds.tap(200, 75, hold=0.15, after=2.2)   # スタート
        # 4) 难度选择 -> むずかしい
        for _ in range(3):
            ds.tap(176, 167, hold=0.15, after=2.2)
            if s18.is_select_ui():
                break
    ok = s18.is_select_ui()
    print("选关页:", ok, "frame:", SB.frame_view(), flush=True)
    if ok:
        N.goto_window(1)
        N.wait_select_ready()
        print("goto_window(1) 后 is_select_ui:", s18.is_select_ui(), flush=True)
        ds.grab(None).save("/tmp/muzu_select.png")
    return ok

if __name__ == "__main__":
    main()
