#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性把 BGM 设为 BGM3 —— **在录制窗口之外**执行，绝不被录进视频。

为什么独立：录制脚本 rec_muzu_*.sh 只在 driver 到达「选关页」后才写开录哨兵，
driver 全程不碰 BGM；本脚本是录制前的单独准备步骤，设好后 BGM3 落盘，
后续录制不会再改 BGM。

用法（环境已起、游戏停在 muzusaki 选关页）：
    cd ai-tas && python3.11 setup_bgm3.py

流程：选关页 → 进第1关（暂停/选项菜单须从盘面打开）→ Return 开选项菜单 →
      点 BGM 行第3格 (x=203, y≈263) → x 确认 → 退出关卡写存档 → 回选关页。
"""
import sys
import time

import ds
import play_akari_muzu as M

# 选项菜单里 BGM 行的四个可选位置（下屏局部坐标，x；y≈263 用 263+192=455 绝对 y？）
# ★沿用上一轮实测定标：菜单在小屏，ds.tap_local 用小屏局部坐标（y 不 +192）。
#   OFF=131 / 1=155 / 2=179 / 3=203；行中心 y≈263（局部）。
BGM3_X = 203
BGM3_Y = 263


def main():
    # 1) 确保停在选关页
    if not M.in_select_page(M.grab_np()):
        print("[bgm] 不在选关页 → escape_to_select", flush=True)
        M.escape_to_select()
        time.sleep(1.2)
    if not M.in_select_page(M.grab_np()):
        print("[bgm] 无法回到选关页，退出", flush=True)
        return 1

    # 2) 进第1关（暂停菜单只能从盘面打开）
    if not M.goto_level(1):
        print("[bgm] 进第1关失败，退出", flush=True)
        return 1
    time.sleep(1.5)

    # 3) 开选项菜单（Start/Return）
    ds.press("Return", wait=1.5)
    opened = False
    for _ in range(3):
        if M.option_menu_open(M.grab_np()):
            opened = True
            break
        ds.press("Return", wait=1.5)
    if not opened:
        print("[bgm] 选项菜单未打开，退出", flush=True)
        return 1

    # 4) 点 BGM=3 并确认
    ds.tap_local(BGM3_X, BGM3_Y, after=0.6)
    ds.press("x", wait=0.8)
    time.sleep(0.5)
    print(f"[bgm] 已点 BGM 第3格 ({BGM3_X},{BGM3_Y}) 并确认", flush=True)

    # 5) 退出关卡（写存档）→ 回选关页
    M.escape_to_select()
    time.sleep(1.2)
    if M.in_select_page(M.grab_np()):
        print("[bgm] BGM3 设置完成，存档已落盘，已回选关页。", flush=True)
        return 0
    print("[bgm] 设置完成但未能确认回选关页（可能仍在菜单），请手动确认。", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
