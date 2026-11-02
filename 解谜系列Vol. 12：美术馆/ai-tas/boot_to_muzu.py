#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vol.12 冷启动导航：DeSmuME 重启 -> 标题 -> 本編を始める -> 存档1 -> むずかしい -> 选关页。

为什么需要本脚本：难度**不随存档保存**，DeSmuME 冷启恒回「入門」选关页。
录制驱动 play_akari_muzu.main() 假定开录前已停在「むずかしい」选关页
（它只会在「非选关页」时调 escape_to_select，而该函数不会切难度），
所以每次重启后必须先人工 bring-up 到むずかしい，再交给录制脚本。

坐标（MUZU_RUN.md §三/§六 实测定标，下屏 NDS 相对 y）：
  本編を始める  tap_local(128,235)   # 标题 -> 存档页
  存档1 行       tap_local(128,258)   # 存档页 -> 难度一览页
  むずかしい 条   tap_local(128,335)   # 难度一览页 -> むずかしい 选关页（nds_y=143）
  A 确认用 ds.press("x")

用法（环境已起：bash vol12_env.sh on）：
  cd ai-tas && python3.11 boot_to_muzu.py
"""
import sys
import time

sys.path.insert(0, "/workspace/hudson_tas/解谜系列Vol. 12：美术馆/ai-tas")
import ds
import play_akari_muzu as P

BASE = "/root/.codebuddy/artifact/vol12"


def snap(tag):
    try:
        ds.grab(tag)
        print(f"  [snap] 截图已存 {BASE}/{tag}.png", flush=True)
    except Exception as e:
        print(f"  [snap] 失败 {e}", flush=True)


def at_select():
    return P.in_select_page(P.grab_np())


def at_diff():
    return P._popup_open(P.grab_np())


def advance_to_diff():
    """从标题/存档页推进到「难度一览页」。

    标题页 tap 本編(235) -> 存档页；存档页 tap 存档1(258)+x -> 难度一览页。
    在存档页上 tap(235) 落在按钮上方空隙、基本无害，故两态共用同一步序。
    """
    ds.tap_local(128, 235, after=1.0)        # 本編を始める（标题 -> 存档页）
    ds.tap_local(128, 258, after=0.6)        # 存档1 行（存档页）
    ds.press("x", wait=1.5)                  # A 进入 -> 难度一览页
    return at_diff()


def main():
    # 1) 等 grab 能取到画面（标题/存档/选关任一皆可），最多 ~21s
    #    ★不能再要求「已是选关/难度页」：冷启后停在标题页，二者皆 False 会死等。
    ready = False
    for i in range(14):
        try:
            im = P.grab_np()
            if im is not None and im.shape[0] == 384 and im.shape[1] == 256:
                ready = True
                print(f"  [boot] 第{i}轮画面就绪", flush=True)
                break
        except Exception:
            pass
        print(f"  [boot] 第{i}轮等待画面...", flush=True)
        time.sleep(1.5)
    if not ready:
        snap("boot_wait_fail")
        print("[boot] 等待超时，截图留存，退出", flush=True)
        return 1

    # 2) 主循环：不在むずかしい选关页就推进
    for attempt in range(12):
        if at_select():
            snap(f"boot_select_{attempt}")
            print(f"[boot] 已在选关页（第{attempt}轮）", flush=True)
            return 0
        if at_diff():
            print(f"  [boot] 难度一览页 -> 点むずかしい(335)+x", flush=True)
            ds.tap_local(128, 335, after=0.9)
            ds.press("x", wait=1.8)
            time.sleep(1.0)
            continue
        # 标题/存档页：推进到难度一览页
        print(f"  [boot] 第{attempt}轮：推进 标题/存档 -> 难度一览", flush=True)
        if not advance_to_diff():
            snap(f"boot_advance_{attempt}")
            time.sleep(0.5)
            continue
        # 已到难度一览页，下一轮循环会点むずかしい

    ok = at_select()
    if ok:
        snap("boot_select_final")
    else:
        snap("boot_fail")
    print("RESULT:", "OK" if ok else "FAIL", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
