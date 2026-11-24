#!/usr/bin/env python3.11
"""可靠导航到全新档第1关干净盘面(每步已在实机验证)。"""
import time, subprocess
import numpy as np
import ds


def key(k, hold=0.12, wait=0.35):
    subprocess.run(["xdotool", "keydown", k], env=ds.ENV); time.sleep(hold)
    subprocess.run(["xdotool", "keyup", k], env=ds.ENV); time.sleep(wait)


def focus():
    w = ds.ensure_window()
    subprocess.run(["xdotool", "windowfocus", w], env=ds.ENV)
    time.sleep(0.3)


def is_board():
    im = ds.grab("_probe")
    a = np.asarray(im.convert("RGB"))
    tr = a[5:22, 190:252]                        # 上屏右上角计时器
    dark = ((tr[:,:,0]<90)&(tr[:,:,1]<90)&(tr[:,:,2]<90)).mean()
    return dark, dark > 0.25


def navigate():
    ds.start()                                   # 冷启动读全新档
    focus()
    time.sleep(3.0)
    ds.tap(128,150,after=1.2)                    # 欢迎页触摸 -> 游戏菜单
    ds.tap(128,47,after=0.7)                     # 选中スタート
    key("x", wait=2.0)                           # A -> 教程提示
    ds.tap(128,150,after=0.6)                    # 进教程实操
    # 教程实操页需先触摸下屏激活焦点, 再长按R才生效; 有时要按两次
    for _ in range(2):
        ds.tap(128,150,after=0.4)
        key("w", hold=2.2, wait=1.8)
        dark,ok = is_board()
        # 教程页顶部有"チュートリアル"橙字; 跳过成功的标志是到达サポート页(下屏出现3个选项)
        im = ds.grab("_tut"); a = np.asarray(im.convert("RGB"))
        top = a[0:20, 0:130]
        orange = ((top[:,:,0]>150)&(top[:,:,1]>70)&(top[:,:,1]<190)&(top[:,:,2]<110)).mean()
        if orange < 0.08:                        # 教程标题消失
            break
    key("Down", wait=0.35); key("Down", wait=0.35)  # 选最底 サポートなし
    key("x", wait=1.8)                           # -> 主菜单
    key("x", wait=1.8)                           # 通常問題 -> 难度页
    key("x", hold=0.5, wait=2.5)                 # 长按A -> 预览页
    key("x", hold=0.5, wait=2.5)                 # 长按A -> 盘面
    dark, ok = is_board()
    print(f"进关检测 timer_dark={dark:.3f} ok={ok}", flush=True)
    return ok


if __name__ == "__main__":
    import sys
    sys.exit(0 if navigate() else 1)
