#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vol.05 数回 —— 24x14 大盘连续录制（ふつう 65~100 / むずかしい 1~17）。

判定链路与 18x10（record18_v4.py）完全共用：
  Completion!!（下屏橙字模板）-> tap(128,96) 触摸确认 -> 真结算页
  （上屏绿色竹叶底 + 蓝色 クリアタイム/取得星数 横幅，real_result 三重判据）。

绘制链路改用 slither_big：6 视口遍历逐边画 + 每视口净盘差分核查。
每关独立导航（禁用 chained 连关），失败自动删坏 mp4 整关重录。

用法:
    bash ai-tas/boot_audio.sh
    python3 ai-tas/record_big.py --diff futsuu     --lo 65 --hi 100
    python3 ai-tas/record_big.py --diff muzukashii --lo 1  --hi 17
    python3 ai-tas/record_big.py --diff futsuu --lo 65 --hi 65 --dry
"""
import argparse
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ds                      # noqa: E402
import nav18 as N              # noqa: E402
import record_levels as rl     # noqa: E402
import slither18 as s18        # noqa: E402
import record18_v4 as V        # noqa: E402  判据共用
import slither_big as SB       # noqa: E402  24x14 绘制核心

# 24x14 チェック 按钮（下屏 y=174..190 一排，チェック x≈175..214 中心 195,182）
CHECK_BTN = (195, 182)

DIFFS = {
    #   ふつう 65..100 = 24x14（idx = 1522 + 关号）
    #   むずかしい 1..17 = 24x14（idx = 1622 + 关号）
    "futsuu":     dict(label="ふつう",     tap=(176, 127), base=1522, total=100),
    "muzukashii": dict(label="むずかしい", tap=(176, 167), base=1622, total=50),
}
MISS_TH = 80
MAX_LEVEL_S = 420              # 24x14 边数翻倍，单关硬上限放大


def settled():
    return V.settled()


def judge(timeout=26.0):
    """复用 18x10 判定，但用 24x14 的チェック坐标。

    ★ 24x14 第65問实测：画完最后一条边后触摸释放/动画窗口较长，
      チェック 单击偶尔被吞（前两次 attempt 判定超时、第三次才过关）。
      故把チェック改成「低频循环重试直到出现 Completion/真结算页」，
      并在开判前等 1.2s 让末条边稳定；触摸确认循环也加长。
      成功时第一次点击即触发，不改变正常链路，也不动 18x10 生产代码。
    """
    def finish(tag, t0):
        ok = False
        for _ in range(8):
            if V.real_result():
                ok = True
                break
            ds.tap(128, 96, hold=0.15, after=1.0)   # 确认 "Please touch!"
        else:
            ok = V.real_result()
        time.sleep(1.8)
        return ok, time.time() - t0, tag if ok else "touch-failed"

    time.sleep(1.2)                                  # 末条边触摸释放 / 动画稳定
    t0 = time.time()
    if V.real_result():
        return True, time.time() - t0, "result-auto"
    while time.time() - t0 < timeout:
        ds.tap(*CHECK_BTN, hold=0.18, after=0.9)    # チェック（可能被吞，重试）
        for _ in range(4):
            if V.completion_anim() or V.real_result():
                return finish("completion", t0)
            time.sleep(0.35)
    # 超时：留一张当时整屏截图供诊断（到底停在盘面 / まちがい / Completion），
    # 并如实判失败，绝不假报过关。
    try:
        ds.grab(None).save(f"/tmp/vol5_judge_fail_{int(time.time())}.png")
    except Exception:
        pass
    return False, time.time() - t0, None


def on_board():
    return s18.bot_rgb() is not None and float(
        (s18.bot_rgb()[10:30, 150:252].sum(axis=2) < 260).mean()) < 0.30


def to_select_of(diff):
    """切到指定难度选关页（复用 18x10 已验证的 B 返回 + 点难度）。"""
    ds.ensure_window()
    if on_board():
        N.leave_level()
    if s18.is_select_ui():
        ds.press("z", wait=1.8)
        time.sleep(0.6)
        if s18.is_select_ui():
            ds.tap(48, 165, hold=0.15, after=1.8)
    if s18.is_select_ui():
        print("  !! 无法离开选关页，难度切换不可靠", flush=True)
        return False
    for _ in range(4):
        ds.tap(*DIFFS[diff]["tap"], hold=0.12, after=1.8)
        time.sleep(0.4)
        if s18.is_select_ui():
            return True
    return False


def ensure_board(lvl, diff):
    """开场确保停在 lvl 的干净盘面（跳过进关成绩页 / 残留结算页）。"""
    for i in range(6):
        if V.real_result():
            ds.press("x", wait=1.2)
            time.sleep(0.3)
            continue
        k = V.result_kind()
        if k is None and not V.completion_anim() and not s18.is_select_ui():
            return True
        if s18.is_select_ui():
            if not to_select_of(diff):
                return False
            N.goto_window(51 if lvl > 50 else 1)
            ok, _ = N.enter_level(lvl)
            if not ok:
                return False
            N.wait_start_anim()
        else:
            ds.tap(128, 96, hold=0.12, after=1.1)
            time.sleep(0.3)
            if V.result_kind() is not None:
                ds.press("x", wait=1.1)
        time.sleep(0.3)
    return V.result_kind() is None


def run(lo, hi, dry, force, outdir, diff, assume_board=False, retries=3):
    SB.STOP_HOOK = settled
    os.makedirs(outdir, exist_ok=True)
    ds.ensure_window()
    base_idx = DIFFS[diff]["base"]
    label = DIFFS[diff]["label"]
    logpath = os.path.join(outdir, "record_log.json")
    merged = {}
    if os.path.exists(logpath):
        try:
            merged = {r["lvl"]: r for r in json.load(open(logpath, encoding="utf-8"))}
        except (ValueError, OSError):
            pass

    for lvl in range(lo, hi + 1):
        idx = base_idx + lvl
        out = os.path.join(outdir, f"数回_{label}24x14_第{lvl:02d}問.mp4")
        if not dry and not force and os.path.exists(out) and os.path.getsize(out) > 20000:
            print(f"第{lvl}問 已存在，跳过", flush=True)
            continue
        cleared = False
        for attempt in range(1, retries + 1):
            if attempt > 1:
                print(f"  ↻ 第{lvl}問 第{attempt}次重录（上次未过关，已删坏文件）", flush=True)
            if assume_board and lvl == lo and attempt == 1:
                taps = 0
            else:
                if not to_select_of(diff):
                    print("  !! 无法回到目标难度选关页，重试", flush=True)
                    continue
                N.goto_window(51 if lvl > 50 else 1)
                ok, taps = N.enter_level(lvl)
                if not ok:
                    print(f"  !! 第{lvl}問 进关失败，重试", flush=True)
                    continue
                N.wait_start_anim()
            if not ensure_board(lvl, diff):
                print(f"  !! 第{lvl}問 无法进入干净盘面，重试", flush=True)
                continue
            # 干净进关视口必须是逻辑 (0,0)；纵向无反向控件，否则无法遍历
            M0 = SB.measure(idx)
            v0 = (M0["r0"], M0["c0"])
            if v0 != (0, 0) or M0["score"] < 110:
                print(f"  !! 第{lvl}問 视口未复位 {v0} score={M0['score']}，整关重导航", flush=True)
                continue
            print(f"第{lvl}問 idx={idx} 尝试{attempt} 进关(tap{taps}) 视口={v0} "
                  f"原点=({M0['X0']},{M0['Y0']}) score={M0['score']} 边={len(SB.edges_of(idx))}", flush=True)

            rec = None if dry else rl.rec_start(out)
            t0 = time.time()
            wall = 0.0
            uncovered_n = miss_n = 0
            stopped = False
            visited = []
            cleared, waited, kind, rc = False, 0.0, None, None
            try:
                uncovered, miss_n, stopped, visited = SB.draw_all(idx, settled=settled)
                uncovered_n = len(uncovered)
                wall = time.time() - t0
                cleared, waited, kind = judge()
                if rec:
                    rc = rl.rec_stop(rec)
                    rec = None
            finally:
                if rec:
                    rl.rec_stop(rec)
                    rc = -9
            size = os.path.getsize(out) if (not dry and os.path.exists(out)) else 0
            merged[lvl] = dict(lvl=lvl, idx=idx, board="24x14", edges=len(SB.edges_of(idx)),
                               diff=diff, draw=round(wall, 1), uncovered=uncovered_n,
                               missing=int(miss_n), stopped=bool(stopped),
                               views=[list(v) for v in visited],
                               cleared=bool(cleared), result=kind, judge_s=round(waited, 1),
                               ff_rc=rc, size=size, attempt=attempt)
            print(f"第{lvl}問 画 {wall:.1f}s 未覆盖{uncovered_n} 仍缺{miss_n} "
                  f"结算={kind} 过关={cleared}({waited:.1f}s) mp4={size}B", flush=True)
            json.dump([merged[k] for k in sorted(merged)], open(logpath, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
            if cleared:
                break
            if not dry and os.path.exists(out):
                os.remove(out)
        if not cleared:
            print(f"  !! 第{lvl}問 {retries} 次仍未过关，停批", flush=True)
            break
    print("结束。日志", logpath, "共", len(merged), "关", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lo", type=int, default=65)
    ap.add_argument("--hi", type=int, default=100)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--outdir", default=None)
    ap.add_argument("--diff", choices=list(DIFFS), default="futsuu")
    ap.add_argument("--assume-board", action="store_true")
    ap.add_argument("--retries", type=int, default=3)
    a = ap.parse_args()
    od = a.outdir or f"/workspace/vol5_recordings_{a.diff}_24x14"
    run(a.lo, a.hi, a.dry, a.force, od, a.diff, a.assume_board, a.retries)
