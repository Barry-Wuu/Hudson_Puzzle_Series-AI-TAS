#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vol.12 冷启动导航（やさしい 版）：DeSmuME 重启 -> 标题 -> 本編を始める -> 存档1 -> やさしい -> 选关页。

改写自已验证的 boot_to_muzu.py（差异：难度条 むずかしい335 -> やさしい279；
导入 play_yasashii）。难度不随存档保存，冷启恒回入門选关页，故必须先 bring-up。

用法（环境已起：bash vol12_env.sh on）：
  cd ai-tas && python3.11 boot_to_yasashii.py
"""
import sys
import time

sys.path.insert(0, "/workspace/hudson_tas/解谜系列Vol.12：美术馆/ai-tas")
import ds
import play_yasashii as P

BASE = "/root/.codebuddy/artifact/vol12"
YASA_Y = 279          # やさしい 条（截图 y = nds_y 87 + 192）


def snap(tag):
    try:
        ds.grab(tag)
        print(f"  [snap] {BASE}/{tag}.png", flush=True)
    except Exception as e:
        print(f"  [snap] 失败 {e}", flush=True)


def at_select():
    return P.in_select_page(P.grab_np())


def at_diff():
    return P._popup_open(P.grab_np())


def advance_to_diff():
    ds.tap_local(128, 235, after=1.0)        # 本編を始める（标题 -> 存档页）
    ds.tap_local(128, 258, after=0.6)        # 存档1 行（存档页）
    ds.press("x", wait=1.5)                  # A 进入 -> 难度一览页
    return at_diff()


def main():
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
        snap("yasa_boot_wait_fail")
        return 1

    for attempt in range(12):
        if at_select():
            snap(f"yasa_boot_select_{attempt}")
            print(f"[boot] 已在选关页（第{attempt}轮）", flush=True)
            return 0
        if at_diff():
            print(f"  [boot] 难度页 -> 点やさしい({YASA_Y})+x", flush=True)
            ds.tap_local(128, YASA_Y, after=0.9)
            ds.press("x", wait=1.8)
            time.sleep(1.0)
            continue
        print(f"  [boot] 第{attempt}轮：推进 标题/存档 -> 难度页", flush=True)
        if not advance_to_diff():
            snap(f"yasa_boot_advance_{attempt}")
            time.sleep(0.5)
            continue

    ok = at_select()
    snap("yasa_boot_final" if ok else "yasa_boot_fail")
    print("RESULT:", "OK" if ok else "FAIL", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
