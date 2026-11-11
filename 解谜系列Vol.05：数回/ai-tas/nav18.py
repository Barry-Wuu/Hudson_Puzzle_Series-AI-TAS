#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""18x10 档导航：选关页格子坐标、进关、退关回选关页。全部为实机标定。

选关页（やさしい）实测：
  5 行 × 10 列，格子中心 x = 20+24*col（col=0 在 x≈22），y = 44+24*row；
  第 51..100 关的窗口固定显示 51~100：row=(lvl-51)//10, col=(lvl-51)%10。
  第 1..50 关的窗口是 1~50，row=(lvl-1)//10。
进关：**单击一次**即可（双击第二下会被当成盘面点击，曾误入第 64 問）。
退关：オプション(225,178) -> 問題選択画面へ(222,36) -> はい(90,122)。
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ds                      # noqa: E402
import record_levels as rl     # noqa: E402
import slither18 as s18        # noqa: E402


def level_xy(lvl):
    if lvl > 50:
        return 22 + 24 * ((lvl - 51) % 10), 44 + 24 * ((lvl - 51) // 10)
    return 22 + 24 * ((lvl - 1) % 10), 44 + 24 * ((lvl - 1) // 10)


def to_select(max_try=6):
    """确保停在选关页。"""
    for _ in range(max_try):
        if s18.is_select_ui():
            return True
        ds.tap(128, 96, hold=0.15, after=1.6)
    return s18.is_select_ui()


def leave_level(max_try=3):
    """从盘面退回选关页（オプション -> 問題選択画面へ -> はい）。"""
    for _ in range(max_try):
        if s18.is_select_ui():
            return True
        ds.tap(225, 178, hold=0.20, after=1.6)   # オプション
        ds.tap(222, 36, hold=0.20, after=1.6)    # 問題選択画面へ
        ds.tap(90, 122, hold=0.20, after=2.4)    # はい
    return s18.is_select_ui()


def enter_level(lvl, wait=3.2):
    """单击关卡格子进关；若仍在选关页再点一次（不重复点同一格超过 2 次）。"""
    x, y = level_xy(lvl)
    for k in range(3):
        ds.tap(x, y, hold=0.12, after=wait)
        if not s18.is_select_ui():
            wait_start_anim()
            return True, k + 1
    return False, 3


if __name__ == "__main__":
    print("state select?", s18.is_select_ui(), "view", s18.view_now())


def boot_to_select(max_wait=60):
    """冷启动 -> やさしい 选关页。"""
    ds.ensure_window()
    for _ in range(max_wait):
        ds.press("x", wait=1.5)
        if s18.is_select_ui():
            return True
        break
    # 玩家选择
    ds.tap(60, 42, hold=0.15, after=3.0)
    for _ in range(4):
        ds.tap(200, 75, hold=0.15, after=2.2)     # スタート
        for _ in range(3):
            ds.tap(200, 95, hold=0.15, after=2.2)  # やさしい
            if s18.is_select_ui():
                return True
    return s18.is_select_ui()


def wait_start_anim(timeout=8.0):
    """进关后的 START 演出期间触摸会被吞，等中央蓝色字消失。"""
    import numpy as np
    t0 = time.time()
    while time.time() - t0 < timeout:
        a = np.asarray(ds.grab(None).crop((0, 192, 256, 384)).convert("RGB")).astype(int)
        c = a[60:130, 60:200]
        blue = ((c[:, :, 2] > 150) & (c[:, :, 2] > c[:, :, 0] + 60)).sum()
        if blue == 0:
            return True
        time.sleep(0.5)
    return False


TAP_UP = (127, 23)      # 顶部▲：滚到最上窗口（1~50）
TAP_DOWN = (127, 162)   # 底部▼：每次下滚一行（10 关）


def goto_window(start):
    """把选关窗口确定地滚到以 start 为首关的那一屏（先▲到底再▼下滚）。

    实机：▲ 12 次必停在上限（1~50），此后 ▼ 每按一次窗口下移 10 关，
    5 次正好到 51~100。这样就不必猜当前窗口位置。
    """
    for _ in range(12):
        ds.tap(*TAP_UP, hold=0.12, after=0.55)
    for _ in range(max(0, (start - 1) // 10)):
        ds.tap(*TAP_DOWN, hold=0.12, after=0.55)
    return start
