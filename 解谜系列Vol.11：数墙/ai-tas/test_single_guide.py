#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""单关测试（照抄攻略 / 去求解器）：正常倍速（限速器ON/固定60fps）+ 有声录像
条件下，单关最快实打耗时。

与 seg1_run 的区别：play 段不再 read_board() 识别谜面、不再 solve() 求解，
而是直接从《攻略.md》解析出的黑格坐标查表，用 cell_nds 算屏幕坐标逐个涂黑。
仅保留一次轻量「当前黑白」回读（不识别数字、不求解）用于补涂漏格，保证涂齐。

计时拆解：enter->clear 总墙钟 = START动画 + 网格检测 + 涂格+校验。
用法: python3 test_single_guide.py [lvl ...]   (默认 2 3 17 18)
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
import guide

ANSWERS = guide.load_answers("入門")
print(f"=== single-lvl GUIDE test (照抄攻略/去求解器) ===", flush=True)
# 用法:
#   python3 test_single_guide.py seg1        -> 暖机第1关(不录)，录入门 2..20 作为 seg1
#   python3 test_single_guide.py 3           -> 单关测试（直接录该关，含其教程）
#   python3 test_single_guide.py 2 3 17 18   -> 指定关列表测试


def state():
    return state2.detect(ds.grab(None))


def read_current_blacks(grid):
    """轻量回读：只判当前盘面每个格是否黑（颜色均值），不识别数字、不求解。"""
    f = tut.grab_np()
    x0, y0, cols, rows = grid
    blacks = set()
    for r in range(rows):
        for c in range(cols):
            win = f[y0 + 24 * r + 4:y0 + 24 * r + 20,
                    x0 + 24 * c + 4:x0 + 24 * c + 20]
            m = win.reshape(-1, 3).mean(axis=0)
            if m[0] < 115 and m[1] < 115 and m[2] < 115:
                blacks.add((r, c))
    return blacks


def advance_to_play(lvl, timeout=150.0):
    """进关后推进教学/说明屏（tut）直到进入真实 play 界面。返回 True=已进入 play/clear。

    实测（diag_tut2 截图证实）：fresh save 下进关触发完整「チュートリアル」——
    上屏多页说明（戻るL/進むR）+ 下屏互动教学盘（点闪烁格涂黑）。state2 会把它
    判为 tut，单按 A 无效，必须 tut.do_step（闪烁检测+点击/R 翻页）逐步推进；
    do_step 每次调用只推进一步，整套教学需十几次调用（约 1~2 分钟）。故超时
    放大到 150s：教学是每存档一次性的，第一关吸收该成本后，后续关应直进 play。
    do_step 返回 advanced=True 仅代表上屏翻页/步骤推进，不等于已到 play，
    必须以 state 转为 play/clear 为准。max_rounds=4 限制单次 do_step 最坏耗时。
    """
    t0 = time.time()
    n_step = 0
    while time.time() - t0 < timeout:
        st = state()
        if st == "clear":
            return True
        if st == "play":
            # 防过渡屏误判：连续两帧 detect_grid 几何一致才算真 play
            g1 = tut.detect_grid(tut.grab_np())
            if g1:
                time.sleep(0.15)
                g2 = tut.detect_grid(tut.grab_np())
                if g1 == g2:
                    return True
            time.sleep(0.2)
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
            else:
                print(f"  [adv lvl{lvl}] tut step#{n_step} grid=NONE "
                      f"elapsed={time.time()-t0:.1f}s", flush=True)
            if not advanced and state() != "clear":
                # 教学完成页等无闪烁目标态：按 A 推进
                ds.press("x", wait=0.4, hold=0.05)
            time.sleep(0.3)
        else:
            # 其他过渡态（说明页/解锁页等）：按 A 推进
            ds.press("x", wait=0.4, hold=0.05)
            time.sleep(0.3)
    print(f"  [adv lvl{lvl}] TIMEOUT after {n_step} steps (state={state()})",
          flush=True)
    return state() == "play"


def play_guide(lvl, max_rounds=4, clear_wait=4.0):
    """照攻略坐标直接涂格。返回 ok。

    流程：wait_start_done（START 动画）-> advance_to_play（推进说明屏直到真实
    play）-> detect_grid 定位网格几何 -> 按攻略黑格坐标涂 -> 轮询等 clear。
    坐标映射恒等（mode=id）：攻略 (r,c) 即屏幕 (r,c)，无需翻转/转置。说明屏的
    网格几何与真实 play 不同，必须先推进到 play 再 detect_grid，否则会在说明屏
    上误涂（重现早期 missing/extra 假象）。
    打印 missing/extra 用于诊断坐标方向是否正确（涂齐后应为 0/0）。
    """
    t0 = time.time()
    S.wait_start_done()                      # 等 START 动画（若有）
    # 关键：推进说明屏直到进入真实 play（limiter ON 下说明屏停留真实时长）
    if not advance_to_play(lvl):
        print(f"  [lvl{lvl}] did not reach play (state={state()})", flush=True)
        return False
    # 录制起止由 main() 统一控制：seg1 模式下第1关暖机回选关写开录哨兵、
    # 末关回选关写停录哨兵；单关模式在 main() 进关前/后写。这里只负责涂格。
    # 真实 play：detect_grid 定位网格几何
    grid = None
    for _ in range(60):
        f = tut.grab_np()
        g = tut.detect_grid(f)
        if g:
            grid = g
            break
        time.sleep(0.2)
    if not grid:
        print(f"  [lvl{lvl}] NO GRID (state={state()})", flush=True)
        return False
    blacks = set(ANSWERS[lvl])
    t_grid = time.time()
    for rd in range(max_rounds):
        if state() == "clear":
            break
        cur = read_current_blacks(grid)
        missing = blacks - cur               # 应黑未黑 -> 补涂
        extra = cur - blacks                 # 误黑 -> 擦除
        if not missing and not extra:
            break
        for (r, c) in sorted(missing):
            ds.tap(*N.cell_nds(grid, r, c), hold=0.06, after=0.02, gap=0.02)
        for (r, c) in sorted(extra):
            ds.tap(*N.cell_nds(grid, r, c), hold=0.06, after=0.02, gap=0.02)
        time.sleep(0.3)                      # 等真实帧把本轮点击结算完
    # 涂齐后等 clear 动画出现
    for _ in range(int(clear_wait / 0.2)):
        if state() == "clear":
            break
        time.sleep(0.2)
    ok = state() == "clear"
    missing, extra = set(), set()
    if not ok:
        # 通关动画会改盘面渲染，clear 后回读必然失真——只在未通关时回读诊断
        cur = read_current_blacks(grid) if grid else set()
        missing = blacks - cur
        extra = cur - blacks
    t_clear = time.time()
    print(f"  [lvl{lvl}] blacks={len(blacks)} enter_to_clear={t_clear - t0:.2f}s "
          f"(wait_ready={t_grid - t0:.2f} tap+verify={t_clear - t_grid:.2f}) "
          f"ok={ok} missing={len(missing)} extra={len(extra)}", flush=True)
    return ok


def main():
    if state() != "select":
        import boot_to_select
        if not boot_to_select.boot_to_select():
            print("FATAL boot", flush=True)
            return 1

    seg1 = len(sys.argv) > 1 and sys.argv[1] == "seg1"

    if seg1:
        # 暖机：第1关吸收一次性教程（不录），清完回选关后写开录哨兵
        print("=== seg1 mode: warmup lvl1 (NOT recorded) ===", flush=True)
        if not S.enter_level(1):
            print("FAIL enter warmup lvl1", flush=True)
            return 1
        ok1 = play_guide(1)
        S.clear_to_select()
        print(f"  [warmup lvl1] ok={ok1} (tutorial absorbed; NOT recorded)", flush=True)
        try:
            open("/tmp/v11_rec_start", "w").close()
        except OSError:
            pass
        print("  [rec] START capture @ select screen (after lvl1) -> seg1 = lvls 2..20",
              flush=True)
        time.sleep(0.8)  # 给外层录制脚本启动抓帧的余量
        lvls = list(range(2, 21))
    else:
        lvls = [int(x) for x in sys.argv[1:]]
        if not lvls:
            lvls = [2, 3, 17, 18]
        # 单关/指定列表：直接录制（含其教程，供诊断）。进关前开录。
        try:
            open("/tmp/v11_rec_start", "w").close()
        except OSError:
            pass
        time.sleep(0.8)

    results = []
    last = lvls[-1]
    for lvl in lvls:
        if not S.enter_level(lvl):
            print(f"FAIL enter lvl{lvl}", flush=True)
            results.append((lvl, False))
            continue
        ok = play_guide(lvl)
        S.clear_to_select()
        results.append((lvl, ok))
        if lvl == last:
            try:
                open("/tmp/v11_rec_stop", "w").close()
            except OSError:
                pass
            print(f"  [rec] STOP capture @ select screen (after lvl{lvl})", flush=True)

    # 汇总
    print("=== summary ===", flush=True)
    for lvl, ok in results:
        print(f"{'OK  ' if ok else 'FAIL'} lvl{lvl:02d}", flush=True)
    done = sum(1 for _, ok in results if ok)
    print(f"cleared {done}/{len(results)}; final_state={state()}", flush=True)
    print("DONE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
