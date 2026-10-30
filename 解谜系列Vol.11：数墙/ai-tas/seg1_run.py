#!/usr/bin/env python3
"""seg1 主管线：入門 20 关全过（第 1 关 tut 引导 + 其余 play 解题），回选关页。

流程（2026-10-25 实战标定）：
  boot_to_select(V11_DIFF=入門) -> 每关:
    ensure_select -> goto_level_cell -> x -> poll(play/tut)
    tut:  tut.do_step 推进引导（闪烁目标单击/按R）
    play: nyumon_play.play_once（读盘->数墙求解->涂格）
    clear: 按 x(A) -> slot(存档/解锁弹窗) -> select
用法: python3 seg1_run.py [lo] [hi]
"""
import os
import sys
import time

os.environ.setdefault("V11_DIFF", "入門")
sys.path.insert(0, "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas")
import ds
import state2
import mode2_fast as M
import tut
import nyumon_play as N

HERE = "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas"


def state():
    return state2.detect(ds.grab(None))


def _goto_level_fast(lvl):
    """入門专用选格：20 关 = 2 行，全在一屏，无需滚动。

    M.goto_level_cell() 每次都先 scroll_select_edge() 滚到网格边缘，实测
    12.5s/关（20 关白烧 ~4 分钟）。入門一屏可见，直接 tap 目标格即可。
    """
    row, col = (lvl - 1) // 10, (lvl - 1) % 10
    wy = 280 + 16 * row
    wx = 19 + 24 * col
    ds.tap(wx, wy - 192, after=0.5)


def enter_level(lvl):
    """选关页 -> 进入第 lvl 关。返回 True。

    2026-10-26 提速：M.ensure_select() 带难度模板校验，而 seg1 全程不换难度、
    关间本就停在入門选关页 —— 校验会误判并每关重走一遍 diff->select
    （press z 1.5s + press x 1.5s ...），实测每关白耗 13s。故已在 select 时
    直接跳过校验，只在真的不在选关页时才走完整 ensure_select。
    """
    if state() != "select" and not M.ensure_select():
        print(f"  [enter {lvl}] cannot reach select", flush=True)
        return False
    _goto_level_fast(lvl)
    ds.press("x", wait=0.3, hold=0.05)
    st = M.poll(("play", "tut"), timeout=6)
    print(f"  [enter {lvl}] -> {st}", flush=True)
    return st in ("play", "tut")


def wait_start_done(timeout=10.0):
    """等 START 动画结束（底屏中央金色 START 大字消失）。
    动画中读盘会把数字/白格误读成 marks/unknown —— 2026-10-25 lvl4 实踩。"""
    import numpy as np
    t0 = time.time()
    while time.time() - t0 < timeout:
        a = np.asarray(ds.grab(None).convert("RGB")).astype(int)
        R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
        gold = (R > 200) & (G > 140) & (B < 130) & (G > R * 0.6)
        n = int(gold[242:332, 60:190].sum())     # 底屏中央区（全屏坐标）
        if n < 50:
            return True
        time.sleep(0.15)
    return False


def play_level(lvl):
    """打一关：tut/play 分流 -> clear。返回 ok。

    稳健化（2026-10-26 修）：原 else 分支对未知态只 sleep(0.4)、最多 60 轮 ->
    关卡结束后的过渡屏（教程完成页/解锁页等）一旦未被 clear/tut/play/slot 命中，
    就会空转 24s。现改为：未知态主动按 A 推进；tut 的 do_step 未推进时也按 A
    试探；slot 收紧；整体 60s 硬上限。
    """
    t0 = time.time()
    for attempt in range(120):               # 120*0.5 ≈ 60s 硬上限
        st = state()
        if st == "clear":
            print(f"  [lvl{lvl}] CLEAR {time.time()-t0:.1f}s", flush=True)
            return True
        if st == "tut":
            f = tut.grab_np()
            grid = tut.detect_grid(f)
            if not grid:
                time.sleep(0.3)
                continue
            fp0 = tut.upper_fp(f)
            advanced = tut.do_step(grid, fp0)
            if not advanced and state() != "clear":
                # 教程完成页可能仍判为 tut：按 A 推进到 clear
                ds.press("x", wait=0.4, hold=0.05)
            time.sleep(0.3)
        elif st == "play":
            if attempt == 0:
                wait_start_done()               # 进关首次：等 START 动画播完
            ok, b, sol = N.play_once(verbose=(attempt < 2))
            if not ok and b and any(v is None for v in b["clues"].values()):
                time.sleep(2.0)                 # 动画残留误读 -> 重读一次
                ok, b, sol = N.play_once(verbose=False)
            if not ok and b and any(v is None for v in b["clues"].values()):
                ds.grab(f"seg1_unknown_l{lvl:03d}")
                print(f"  [lvl{lvl}] UNKNOWN DIGIT -> saved", flush=True)
                return False
            time.sleep(0.3)
        elif st == "slot":
            ds.press("x", wait=0.6, hold=0.05)   # 存档提示/解锁弹窗
            time.sleep(0.5)
        else:
            # 未知过渡态（教程完成页/解锁页等）：按 A 推进，杜绝 sleep 空转
            ds.press("x", wait=0.4, hold=0.05)
            time.sleep(0.3)
    ds.grab(f"seg1_stuck_l{lvl:03d}")
    print(f"  [lvl{lvl}] STUCK state={state()}", flush=True)
    return state() == "clear"


def clear_to_select():
    """通关屏 -> 选关页。稳健推进：clear/slot 按 A；其他过渡态也按 A 试探；
    16 轮(~6s)硬上限，杜绝未知态空转导致的关间长静止。"""
    t0 = time.time()
    for _ in range(16):
        st = state()
        if st == "select":
            return True
        if st in ("clear", "slot"):
            ds.press("x", wait=0.6, hold=0.05)
        else:
            # play/tut/title/diff/menu/option 等过渡态：按 A 推进
            ds.press("x", wait=0.4, hold=0.05)
        time.sleep(0.3)
    print(f"  back_to_select timeout {time.time()-t0:.1f}s state={state()}", flush=True)
    return state() == "select"


def main():
    lo = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    hi = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    print(f"=== seg1 run: 入門 lvl {lo}..{hi}", flush=True)
    if lo <= 1 and state() != "select":
        # 冷启动/中途续跑都先确保在入門选关页
        import boot_to_select
        if not boot_to_select.boot_to_select():
            print("FATAL boot", flush=True)
            return 1
    results = []
    for lvl in range(lo, hi + 1):
        if not enter_level(lvl):
            print(f"FAIL enter lvl{lvl}", flush=True)
            break
        ok = play_level(lvl)
        if not ok:
            # 脏盘/无解：退出关卡重进一次（enter_level 内 ensure_select 负责回选关）
            print(f"  [lvl{lvl}] retry once", flush=True)
            if enter_level(lvl):
                ok = play_level(lvl)
        results.append((lvl, ok))
        if not ok:
            print(f"FAIL solve lvl{lvl}", flush=True)
            break
        if not clear_to_select():
            print(f"FAIL back-to-select lvl{lvl} state={state()}", flush=True)
            break
    print("=== summary ===", flush=True)
    for lvl, ok in results:
        print(f"{'OK ' if ok else '   '} lvl{lvl:02d}", flush=True)
    done = sum(1 for _, ok in results if ok)
    print(f"cleared {done}/{hi-lo+1}; final_state={state()}", flush=True)
    return 0 if done == hi - lo + 1 and state() == "select" else 1


if __name__ == "__main__":
    sys.exit(main())
