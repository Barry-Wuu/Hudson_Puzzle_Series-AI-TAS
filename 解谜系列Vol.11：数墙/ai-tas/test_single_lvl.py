#!/usr/bin/env python3
"""单关计时测试：正常倍速（限速器ON/固定60fps）+ 有声录像 条件下，
单关最快实打时长。

复用 nyumon_play 的 read_board/solve/cell_nds（只读），自带快剂量涂格
循环（剂量来自 FAST_AFTER 环境变量，默认 0.02 => 0.10s/格，命中96%，
满足硬线 hold>=0.055 / hold+after>=0.08）。

只解指定关卡，逐关测 enter->clear 墙钟，并拆解 读盘/求解/涂格校验 三段。
用法: python3 test_single_lvl.py [lvl ...]   (FAST_AFTER=0.02)
"""
import os
import sys
import time

os.environ.setdefault("V11_DIFF", "入門")
sys.path.insert(0, "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas")
import ds
import state2
import tut
import nyumon_play as N
import seg1_run as S

targets = [int(x) for x in sys.argv[1:]] if len(sys.argv) > 1 else [2]
FAST_AFTER = float(os.environ.get("FAST_AFTER", "0.02"))
print(f"=== single-lvl test: targets={targets} FAST_AFTER={FAST_AFTER} "
      f"dose={0.02+0.06+FAST_AFTER:.3f}s/格 ===", flush=True)


def apply_fast(sol_blacks, rounds=6):
    """涂格：缺格涂黑、多格擦除；每轮发完回读校验（动画沉降），通常1-2轮收敛。"""
    for rd in range(rounds):
        if state2.detect(ds.grab(None)) == "clear":
            return True
        b = N.read_board()
        if not b:
            time.sleep(0.3)
            continue
        erase = [c for c in b["blacks"] if c not in sol_blacks]
        todo = [c for c in sol_blacks if c not in b["blacks"]]
        if not todo and not erase:
            return True
        for (r, c) in erase:
            ds.tap(*N.cell_nds(b["grid"], r, c), hold=0.06, after=FAST_AFTER, gap=0.02)
        for (r, c) in todo:
            ds.tap(*N.cell_nds(b["grid"], r, c), hold=0.06, after=FAST_AFTER, gap=0.02)
        time.sleep(0.6)  # 等真实帧把本轮点击全部结算完再回读
    return state2.detect(ds.grab(None)) == "clear"


def solve_level(lvl):
    """进入本关后（state==play）计时到 clear。返回 ok。"""
    t_enter = time.time()
    S.wait_start_done()  # 等 START 动画（限速器ON下为真实时长）
    b = None
    for i in range(10):
        b = N.read_board()
        if b and len(b["marks"]) <= 8:
            break
        if b is None:
            time.sleep(0.4)
            continue
        time.sleep(0.5)
    if not b:
        print(f"  [lvl{lvl}] no board", flush=True)
        return None
    if len(b["marks"]) > 8:
        print(f"  [lvl{lvl}] board unstable marks={len(b['marks'])}", flush=True)
        return None
    if any(v is None for v in b["clues"].values()):
        print(f"  [lvl{lvl}] unknown digit, abort", flush=True)
        return None
    t_read = time.time()
    sol = N.solve(b["clues"], b["blacks"], b["rows"], b["cols"])
    if sol is None:
        print(f"  [lvl{lvl}] NO SOLUTION", flush=True)
        return None
    t_solve = time.time()
    ok = apply_fast(sol)
    t_clear = time.time()
    print(f"  [lvl{lvl}] blacks={len(sol)} enter_to_clear={t_clear-t_enter:.2f}s "
          f"(read={t_read-t_enter:.2f} solve={t_solve-t_read:.2f} "
          f"tap+verify={t_clear-t_solve:.2f}) ok={ok}", flush=True)
    return ok


def main():
    if state2.detect(ds.grab(None)) != "select":
        import boot_to_select
        if not boot_to_select.boot_to_select():
            print("FATAL boot", flush=True)
            return 1
    for lvl in targets:
        if not S.enter_level(lvl):
            print(f"FAIL enter lvl{lvl}", flush=True)
            break
        ok = solve_level(lvl)
        S.clear_to_select()
        if ok is None:
            print(f"ABORT lvl{lvl}", flush=True)
            break
    print("DONE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
