#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""seg2 驱动：速通「やさしい」（1..100），直接执行 puzzles.json 已知答案
（mode2_fast 引擎，零求解、不 OCR）。原分辨率录制由外层 rec_seg2.sh 控制。

用法: python3 seg2_run.py <LO> <HI> [warmup]
  warmup: 若存在，先打第1关（吸收教程，不录），回选关后写开录哨兵，再录 LO..HI。
          否则：直接写开录哨兵（假定已在选关页、教程已吸收），录 LO..HI。
哨兵: /tmp/v11_rec_start (开录) / /tmp/v11_rec_stop (末关回选关后停录)
"""
import os
import sys
import time

os.environ.setdefault("V11_DIFF", "やさしい")
HERE = "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas"
sys.path.insert(0, HERE)
import ds
import state2
import tut
import mode2_fast as M

# 清关截图落临时目录，不污染 validation/
M.OUT = "/tmp/seg2_clear"
os.makedirs(M.OUT, exist_ok=True)


def state():
    return state2.detect(ds.grab(None))


def clear_to_select():
    """通关屏 -> 选关页（与 seg1 同款稳健推进）。"""
    for _ in range(16):
        st = state()
        if st == "select":
            return True
        if st in ("clear", "slot"):
            ds.press("x", wait=0.6, hold=0.05)
        else:
            ds.press("x", wait=0.4, hold=0.05)
        time.sleep(0.3)
    print(f"  clear_to_select timeout state={state()}", flush=True)
    return state() == "select"


def advance_tutorial(lvl, timeout=150.0):
    """进关后推进教程/说明屏（tut）直到进入真实 play。返回 True=已进入。"""
    t0 = time.time()
    n_step = 0
    while time.time() - t0 < timeout:
        st = state()
        if st == "clear":
            return True
        if st == "play":
            # 确认进入 play 即返回；后续 fill_level 的 wait_unlocked 会等输入解锁，
            # 不会在盘面未就绪时误涂。放宽原 seg1 的「两帧网格稳定」校验，避免暖机空转。
            return True
        if st == "tut":
            f = tut.grab_np()
            grid = tut.detect_grid(f)
            advanced = False
            if grid:
                advanced = tut.do_step(grid, tut.upper_fp(f), max_rounds=4)
                n_step += 1
                if n_step % 5 == 0 or not advanced:
                    print(f"  [adv lvl{lvl}] tut step#{n_step} advanced={advanced} "
                          f"elapsed={time.time()-t0:.1f}s", flush=True)
            if not advanced and state() != "clear":
                ds.press("x", wait=0.4, hold=0.05)
            time.sleep(0.3)
        else:
            ds.press("x", wait=0.4, hold=0.05)
            time.sleep(0.3)
    print(f"  [adv lvl{lvl}] TIMEOUT after {n_step} steps (state={state()})", flush=True)
    return state() == "play"


def set_rect(p):
    """按盘面尺寸设定 mode2_fast 的红框几何全局变量（与 play_level 一致）。"""
    if p["h"] > 10:
        if p["w"] > 30:
            M._RECT_X0, M._RECT_SX = -6, 7.0
            M._RECT_Y0, M._RECT_SY = 29, 7.0
            M._RECT_W36 = True
        else:
            M._RECT_X0, M._RECT_SX = 33, 7.0
            M._RECT_W36 = False
    else:
        M._RECT_X0, M._RECT_SX = 13, 11.0
        M._RECT_W36 = False


def fill_level(lvl):
    """照答案涂格（含大盘面滚动），涂齐后等 clear。返回 ok。不含星级/截图等待，
    让 seg2 录制更紧凑。失败自动走 verify 修复。"""
    idx = lvl - 1
    p = M.PUZ[idx]
    set_rect(p)
    probe = next(((r, c) for (r, c) in M.walls_of(idx) if c < 10 and r < 10), None)
    skip = None
    if probe:
        res = M.wait_unlocked(idx, probe)
        skip = res
    else:
        time.sleep(M.UNLOCK)
    if p["h"] > 10:
        ok = M.fill_huge(idx, skip=skip)
    elif p["w"] > 10:
        ok = M.fill_wide(idx, skip=skip)
    else:
        ok = M.burst_fill(idx, skip=skip)
    if not ok:
        if p["h"] > 10:
            ok = M.verify_huge(idx)
        elif p["w"] > 10:
            ok = M.verify_wide(idx)
        else:
            ok = M.verify_fill(idx)
        ok = bool(ok) and M.wait_clear(8.0)
    return bool(ok)


def enter_and_prepare(lvl):
    """回目标难度选关页 -> 进关 -> 遇教程先推完 -> 进入 play。返回 True/False。

    注意：不能用 mode2_fast.enter_level —— 它在进关后做 clue_match 校验，而教程屏
    上没有谜面线索，会误判失败直接返回。这里自己处理 tut 态：进关若落在 tut，
    先 advance_tutorial 推到 play，再涂格。
    """
    if not M.ensure_select():
        print(f"  [enter {lvl}] ensure_select fail", flush=True)
        return False
    M.goto_level_cell(lvl)
    ds.press("x", wait=0.3, hold=0.05)
    for _ in range(8):
        st = M.poll(("play", "tut", "clear"), timeout=8)
        if st == "tut":
            advance_tutorial(lvl)
            continue
        if st == "clear":
            ds.press("x", wait=0.5, hold=0.05)
            time.sleep(0.4)
            continue
        if st == "play":
            return True
        ds.press("x", wait=0.4, hold=0.05)
        time.sleep(0.3)
    print(f"  [enter {lvl}] final state={M.state()}", flush=True)
    return M.state() == "play"


def play_one(lvl):
    """进关 + 照抄答案通关 + 回选关。返回 ok。"""
    if not enter_and_prepare(lvl):
        print(f"FAIL enter lvl{lvl}", flush=True)
        return False
    ok = fill_level(lvl)
    print(f"  [lvl{lvl}] ok={ok}", flush=True)
    clear_to_select()
    return ok


def main():
    lo = int(sys.argv[1])
    hi = int(sys.argv[2])
    warmup = len(sys.argv) > 3 and sys.argv[3] == "warmup"
    print(f"=== seg2 run: やさしい lvl {lo}..{hi} warmup={warmup} ===", flush=True)
    if not M.ensure_select():
        print("FAIL ensure_select", flush=True)
        return 1
    if warmup:
        print("  [warmup] やさしい lvl1 (NOT recorded)", flush=True)
        play_one(1)
        try:
            open("/tmp/v11_rec_start", "w").close()
        except OSError:
            pass
        print("  [rec] START capture @ select (after warmup lvl1)", flush=True)
        time.sleep(0.8)
    else:
        try:
            open("/tmp/v11_rec_start", "w").close()
        except OSError:
            pass
        time.sleep(0.8)
    results = []
    for lvl in range(lo, hi + 1):
        ok = play_one(lvl)
        results.append((lvl, ok))
        if not ok:
            print(f"FAIL lvl{lvl}; abort segment", flush=True)
            break
        if lvl == hi:
            try:
                open("/tmp/v11_rec_stop", "w").close()
            except OSError:
                pass
            print(f"  [rec] STOP capture @ select (after lvl{lvl})", flush=True)
    done = sum(1 for _, ok in results if ok)
    print(f"cleared {done}/{len(results)}; final_state={state()}", flush=True)
    print("DONE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
