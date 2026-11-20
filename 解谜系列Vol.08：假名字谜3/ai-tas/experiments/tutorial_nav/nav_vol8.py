#!/usr/bin/env python3.11
"""Vol.08 假名字谜3 导航公用层：从任意状态走到指定难度第N关。
所有坐标为下屏 NDS 相对坐标 (0-255, 0-191)。
实测菜单坐标 (v8 2026-11-20):
  游戏菜单: スタート(128,48) 単語帳(128,78) ヘルプ(128,111) データ消去(128,139)
  删除确认框: はい(84,130) いいえ(165,130)
  主菜单: 通常問題(128,140)  [~ v8_11]
  难度页: やさしい(128,155) ふつう(128,?) むずかしい(128,?)
  选关网格: 第1关(15,72)
"""
import sys, time
import ds


def tap(x, y, hold=0.08, after=0.7, gap=0.05):
    ds.tap(x, y, hold=hold, after=after, gap=gap)


def press_a(n=1, wait=0.5):
    for _ in range(n):
        ds.press('x', wait=wait)


def grab(tag):
    ds.grab('nav_' + tag)
    print('  grab nav_' + tag, flush=True)


def cancel_delete_dialog():
    """若卡在删除确认框, 点いいえ取消。"""
    tap(165, 130, after=0.6)   # いいえ


def step_to_start():
    """从当前(可能在确认框/游戏菜单/标题)走到按下スタート。"""
    # 先取消可能的删除确认框
    cancel_delete_dialog()
    # 点スタート
    tap(128, 48, after=1.0)
    grab('after_start')


if __name__ == '__main__':
    ds.start()
    mode = sys.argv[1] if len(sys.argv) > 1 else 'probe'
    if mode == 'recover':
        step_to_start()
    elif mode == 'walk':
        # 手动单步: 每次给一个 x y, 抓图
        x, y = int(sys.argv[2]), int(sys.argv[3])
        tag = sys.argv[4] if len(sys.argv) > 4 else 'step'
        tap(x, y, after=0.9)
        grab(tag)
