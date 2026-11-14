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


PLAYER_SLOT = (65, 55)      # プレイヤー選択：左槽中心（下屏 NDS 坐标）
START_BTN   = (188, 64)     # メインメニュー：スタート（下屏 NDS 坐标）


def _screen_kind():
    """粗分当前画面：select / board / title / menu（用选关页判据的暗色占比）。

      - select：むずかしい/入門 选关页（0.30~0.62，含右上「クリア数」标签）
      - board ：盘内（<0.30）
      - title ：标题 splash（>0.82）
      - menu  ：メインメニュー（0.62~0.82）
    其它（教程页/对话框/面板）按暗色占比落入最接近的桶，由调用方兜底。
    """
    import numpy as np
    a = np.asarray(ds.grab(None).convert("RGB")).astype(int)
    bot = a[192:384]
    r = bot[10:30, 150:252]
    dark = float((r.sum(axis=2) < 260).mean())
    if 0.30 <= dark <= 0.62:
        return "select"
    if dark < 0.30:
        return "board"
    if dark > 0.82:
        return "title"
    return "menu"


def _to_main_menu():
    """冷启动标题 -> プレイヤー選択 -> メインメニュー（难度入口）。

    实测流程（2026-11-13 重新标定）：
      标题 splash（"触摸或 A 继续"）-> 点触中心进 プレイヤー選択 ->
      选左槽 + A 确认 -> 标题(已选玩家) -> A -> メインメニュー。
    """
    ds.ensure_window()
    ds.tap(128, 96, hold=0.15, after=2.0)            # 标题 -> プレイヤー選択
    ds.tap(*PLAYER_SLOT, hold=0.15, after=1.5)        # 选左槽
    ds.press("x", wait=1.5)                           # A 确认 -> 标题(已选玩家)
    ds.press("x", wait=2.0)                           # 标题 -> メインメニュー
    return _screen_kind() == "menu"


def goto_muzukashii_select():
    """任意状态 -> むずかしい 选关页（5x10，第 1~50 問同屏）。

    ★ 2026-11-13 重写：原 boot_to_select 假设「从标题按 A 直接进选关页」，
      但 Vol.05 实际流程是 标题->玩家选择->メインメニュー->スタート(恢复
      むずかしい)->盘->退关。且スタート 直接恢复「上次开始」的 むずかしい
      第18問盘，而非难度选择页；选关页内也无 やさしい/ふつう 切换按钮。
      故改为按真实流程把冷启动收敛到 むずかしい 选关页，全程不依赖已废弃的
      教程退出逻辑（改用 v5_snapshot_1112.dsv 已过教程存档，boot_audio.sh
      每次启动前强制覆盖，彻底消除教程弹窗）。
    """
    ds.ensure_window()
    kind = _screen_kind()
    if kind == "select":
        return True
    if kind == "board":
        for _ in range(4):
            if s18.is_select_ui():
                return True
            leave_level()
            time.sleep(0.8)
        if s18.is_select_ui():
            return True
        kind = _screen_kind()
    if kind == "menu":
        # メインメニュー -> スタート -> むずかしい 盘 -> 退关 -> 选关页
        ds.tap(*START_BTN, hold=0.15, after=2.5)
        for _ in range(4):
            if s18.is_select_ui():
                return True
            leave_level()
            time.sleep(0.8)
        return s18.is_select_ui()
    # title / 未知：走完整冷启动流程
    _to_main_menu()
    ds.tap(*START_BTN, hold=0.15, after=2.5)
    for _ in range(4):
        if s18.is_select_ui():
            return True
        leave_level()
        time.sleep(0.8)
    return s18.is_select_ui()


def boot_to_select(max_wait=60):
    """冷启动 -> むずかしい 选关页（兼容旧调用名）。"""
    return goto_muzukashii_select()


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


def _yellow_at(x0, x1, y0, y1):
    import numpy as np
    a = s18.bot_rgb()
    r = a[y0:y1, x0:x1]
    m = (r[:, :, 0] > 190) & (r[:, :, 1] > 140) & (r[:, :, 2] < 110)
    return int(m.sum()) > 20


def wait_select_ready(timeout=6.0):
    """等选关页画完（三角按钮出现），否则存在性判据会把「还没画出来」当成「已在顶端」。"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        if _yellow_at(118, 140, 14, 30) or _yellow_at(118, 140, 152, 172):
            return True
        time.sleep(0.35)
    return False


def scroll_top(max_try=10):
    """点顶部▲直到它消失（动画期间点击会被吞，所以按存在性闭环）。"""
    wait_select_ready()
    for _ in range(max_try):
        if not _yellow_at(118, 140, 14, 30):
            return True
        ds.tap(*TAP_UP, hold=0.12, after=0.9)
    return not _yellow_at(118, 140, 14, 30)


def scroll_down(n, max_try=14):
    """点底部▼ n 次，每次确认▼仍在（用尽/到底则停）。"""
    wait_select_ready()
    done = 0
    for _ in range(n):
        if not _yellow_at(118, 140, 152, 172):
            break
        ds.tap(*TAP_DOWN, hold=0.12, after=0.95)
        done += 1
    return done


def goto_window(start):
    """把选关窗口确定地滚到以 start 为首关的那一屏（先▲到底再▼下滚）。

    实机：▲ 12 次必停在上限（1~50），此后 ▼ 每按一次窗口下移 10 关，
    5 次正好到 51~100。这样就不必猜当前窗口位置。
    """
    scroll_top()
    scroll_down(max(0, (start - 1) // 10))
    return start
