#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""seg3 剂量快测：在 limiter ON（=录屏时的真实游戏速度）下，对ふつう的两种盘面尺寸
（18×10 / 24×14）扫描比现役更激进的 dose，用 fill 阶段的 topup（首次涂漏的格数）作为
真实命中率指标。

关键：剂量由「盘面尺寸」决定，与难度无关。故用やさしい 同尺寸关卡（18×10=rec1..70、
24×14=rec71..100）实测，结论直接适用于ふつう。录制（x11grab 被动抓帧）不干扰 desmume
帧循环，故 limiter ON 下的结果即「录屏时」结果（seg2 录制中 100 关全 OK 已实证）。

用法: python3 seg3_dose_test.py
"""
import os
import sys
import re
import io
import contextlib
import time

# 用やさしい 同尺寸等价测（剂量只取决于盘面尺寸，与难度无关）
os.environ.setdefault("V11_DIFF", "やさしい")
HERE = "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas"
sys.path.insert(0, HERE)
import mode2_fast as M
import seg2_run as S
import boot_to_select

M.OUT = "/tmp/seg3_dose"
os.makedirs(M.OUT, exist_ok=True)


def test_dose(lvl, dose):
    """进关 -> 用给定 dose 完整 fill（首次涂 + topup 补漏）-> 回选关。
    返回 (首涂命中率%, ok, topup, 总墙数, fill墙钟)。"""
    idx = lvl - 1
    p = M.PUZ[idx]
    if not S.enter_and_prepare(lvl):
        print(f"  FAIL enter lvl{lvl}", flush=True)
        return None
    S.set_rect(p)
    # 注入被测 dose
    if p["h"] > 10:
        M.TAP_HUGE = dict(dose)
    elif p["w"] > 10:
        M.TAP_WIDE = dict(dose)
    else:
        M.TAP = dict(dose)
    t0 = time.time()
    buf = io.StringIO()
    # 用 fill_level（含 verify 兜底）：limiter ON 下 fill 的 wait_clear(4s) 常超时
    # （クリア横幅实时出现 >4s），盘面已涂对；verify 兜底能确认 clear（seg2 同机制 ok=True）。
    # topup 解析取自 fill 阶段，反映首涂命中率。
    with contextlib.redirect_stdout(buf):
        ok = S.fill_level(lvl)
    log = buf.getvalue()
    topups = [int(x) for x in re.findall(r"topup=(\d+)", log)]
    nwalls = len(M.walls_of(idx))
    total_topup = sum(topups)
    el = time.time() - t0
    S.clear_to_select()
    rate = 100.0 * (nwalls - total_topup) / nwalls if nwalls else 0.0
    print(f"  lvl{lvl} {p['w']}x{p['h']} g{dose['gap']} h{dose['hold']} a{dose['after']} "
          f"({sum(dose.values()):.3f}s/格) | 墙={nwalls} 首涂漏={total_topup} "
          f"首涂命中={rate:.0f}% ok={bool(ok)} fill={el:.1f}s", flush=True)
    return rate, bool(ok), total_topup, nwalls, el


def main():
    # 每种尺寸选一个中间关；每个尺寸扫 3 档（对照 + 两个更激进）。
    # 18×10: hold 底线 0.055；24×14: hold 底线 0.07、gap≥0.02、after≥0.02（压这些会掉命中率）
    DOSES = {
        "18x10": [
            ("对照 TAP_WIDE",     dict(gap=0.02, hold=0.06, after=0.015)),
            ("hold0.055+a0.025",  dict(gap=0.02, hold=0.055, after=0.025)),
            ("gap0.015(试探)",    dict(gap=0.015, hold=0.055, after=0.02)),
        ],
        "24x14": [
            ("对照 TAP_HUGE",     dict(gap=0.02, hold=0.07, after=0.02)),
            ("gap0.015(试探)",    dict(gap=0.015, hold=0.07, after=0.02)),
            ("after0.015(试探)",  dict(gap=0.02, hold=0.07, after=0.015)),
        ],
    }
    LVL_BY_SIZE = {"18x10": 10, "24x14": 75}   # やさしい 同尺寸关

    print("=== seg3 dose test (limiter ON; やさしい同尺寸等价ふつう) ===", flush=True)
    if not M.ensure_select():
        print("  ensure_select False -> boot_to_select", flush=True)
        if not boot_to_select.boot_to_select():
            print("FATAL boot", flush=True)
            return 1
    for size, lvl in LVL_BY_SIZE.items():
        print(f"\n##### {size}  (lvl{lvl}) #####", flush=True)
        for name, dose in DOSES[size]:
            print(f"-- {name} --", flush=True)
            r = test_dose(lvl, dose)
            if r is None:
                print(f"  [abort] lvl{lvl} enter failed", flush=True)
                break
    print("\nDONE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
