#!/usr/bin/env python3.11
"""稳定导航: 从冷启动到第2关填字盘面(计时归零)。
坐标全部为下屏 NDS 相对坐标(0-255,0-191), 已由 fx_01~fx_14 实机标定。
"""
import time, subprocess
import ds


def tapt(x, y, after=0.5, confirm=True):
    ds.tap(x, y, after=after)
    if confirm:
        ds.tap(x, y, after=after + 0.4)


def keyA():
    for k in ("keydown", "keyup"):
        subprocess.run(["xdotool", k, "x"], env=ds.ENV)
        if k == "keydown":
            time.sleep(0.12)


def main():
    ds.kill()
    ds.start()
    w = ds.ensure_window()
    subprocess.run(["xdotool", "windowfocus", w], env=ds.ENV)
    time.sleep(0.4)

    # 1. 标题 -> 触摸推进
    ds.tap(128, 150, after=0.8)
    # 2. 游戏菜单 スタート(128,48)
    tapt(128, 48, 0.5)
    time.sleep(1.5)
    # 3. 教程实操页: 触摸激活 + 长按 w(R) 跳过
    ds.tap(128, 150, after=0.4)
    subprocess.run(["xdotool", "keydown", "w"], env=ds.ENV)
    time.sleep(1.9)
    subprocess.run(["xdotool", "keyup", "w"], env=ds.ENV)
    time.sleep(1.2)
    # 4. サポートなし(128,148) 两次
    tapt(128, 148, 0.5)
    time.sleep(1.5)
    # 5. 主菜单 通常問題(128,79)
    tapt(128, 79, 0.5)
    time.sleep(1.5)
    # 6. 难度页 やさしい(128,79)
    tapt(128, 79, 0.5)
    time.sleep(1.5)
    # 7. 选关页: 光标默认在第1关, Right 移到第2关, A 进关
    for k in ("keydown", "keyup"):
        subprocess.run(["xdotool", k, "Right"], env=ds.ENV)
        if k == "keydown":
            time.sleep(0.12)
    time.sleep(0.6)
    keyA()
    time.sleep(1.8)
    ds.grab("nav_final_q2")
    print("导航完成, 应停在第2关填字盘面(计时接近0)", flush=True)


if __name__ == "__main__":
    main()
