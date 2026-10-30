#!/usr/bin/env python3
"""18×10 宽盘剂量网格：分离 gap / hold / after 三因子，找 ≥96% 命中的最低总时长。

背景（2026-10-25）：
  - 10×10 用 TAP(0.02/0.04/0.01)=0.07s/格 零丢击
  - 18×10 用 TAP_WIDE(0.04/0.06/0.02)=0.12s/格 98% 命中，肉眼频率慢 71%
  - 单格独立点击（格间 0.8s）实测：0.07s 剂量 65%，0.12s 剂量 95%
    → 丢格与「是否连涂/游戏忙」无关，是**触摸被识别窗口不足**（hold+after 决定）
  - 拖动连涂实测仅 34% → 排除拖动方案

经济账：总时长 = 墙数×dose + 漏格数×0.34(补点) + 固定
  dose=0.095 命中率 96% → 98×0.095 + 4×0.34 = 10.7s
  dose=0.09  命中率 89% → 98×0.09 + 11×0.34 = 12.6s（补点吞掉收益，反而更慢）
  ⇒ 目标不是"最快"，而是 **命中率 ≥96% 的最低 dose**。

用法：python3 exp_dose_grid.py [lvl]
"""
import sys
import time

sys.path.insert(0, "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas")
import ds
import mode2_fast as M

LVL = int(sys.argv[1]) if len(sys.argv) > 1 else 81
IDX = LVL - 1

# (gap, hold, after) —— 刻意打乱，让「总量」与「分配」解耦
# 第一轮结论：after=0.005 时 hold 0.07→0.08 只 80→87%；after 提到 0.01 立刻 95%。
# 第二轮结论：压 hold 用大 after 补无效（0.04+0.04=60%）。
#   两条约束：① hold ≥ ~0.055（按住时长不够不算涂格）② hold+after ≥ ~0.08（松开后静默结算）
#   且 gap 0.04→0.02 无损 → 现役 gap=0.04 是纯浪费。
# 第三轮：在 hold+after≈0.075~0.085 区间精确定位最小可行剂量。
DOSES = [
    (0.02, 0.06, 0.02),   # 对照：现役 hold/after，gap 减半
    (0.02, 0.06, 0.015),
    (0.02, 0.065, 0.015),
    (0.02, 0.06, 0.01),
    (0.02, 0.065, 0.01),
    (0.02, 0.055, 0.025),
    (0.02, 0.055, 0.03),
    (0.02, 0.07, 0.005),  # 上一轮 80% 的对照档
    (0.025, 0.065, 0.01),
    (0.03, 0.065, 0.01),
]


def run_one(gap, hold, after):
    """干净进关 → 涂段a → 统计命中率。返回 (命中, 总数, 耗时, 实测s/格)"""
    if not M.ensure_select():
        return None
    t0 = M.enter_level(LVL)
    if t0 is None:
        return None
    walls = M.walls_of(IDX)
    a = [(r, c) for r, c in walls if c < 10]
    probe = next((w for w in a if w[0] < 10), None)
    tu = time.time()
    M.wait_unlocked(IDX, probe)
    unlock_t = time.time() - tu
    M.scroll_to_oc_rect(0)
    time.sleep(0.4)

    g0 = M.board_gray()
    pre = sum(1 for (r, c) in a if M.cell_state(g0, r, c) == "B")

    tb = time.time()
    ds.tap_batch([M.cell_nds(r, c) for r, c in a], gap=gap, hold=hold, after=after)
    M.safe_mouseup()
    el = time.time() - tb
    time.sleep(1.4)

    g = M.board_gray()
    blk = sum(1 for (r, c) in a if M.cell_state(g, r, c) == "B")
    hit = blk - pre
    wrong = sum(1 for (r, c) in a if M.cell_state(g, r, c) == "A")
    return hit, len(a), el, el / len(a), unlock_t, wrong


if __name__ == "__main__":
    print(f"=== 18×10 剂量网格 lvl{LVL}（段a {len(M.walls_of(IDX))//2}+ 格，只测 oc=0 视口）===", flush=True)
    print(f"{'gap':>6}{'hold':>7}{'after':>7}{'总s':>8}{'实测/格':>9}"
          f"{'命中':>10}{'命中率':>8}{'解锁s':>8}", flush=True)
    results = []
    for (gp, hd, af) in DOSES:
        r = run_one(gp, hd, af)
        if r is None:
            print(f"{gp:>6}{hd:>7}{af:>7}   FAIL", flush=True)
            continue
        hit, tot, el, per, ult, wrong = r
        rate = 100 * hit / tot
        results.append((gp, hd, af, per, rate, hit, tot))
        print(f"{gp:>6}{hd:>7}{af:>7}{gp+hd+af:>8.3f}{per:>9.3f}"
              f"{str(hit)+'/'+str(tot):>10}{rate:>7.0f}%{ult:>8.2f}", flush=True)
    print("\n=== 排序（按实测 s/格，仅看命中率≥96%）===", flush=True)
    for (gp, hd, af, per, rate, hit, tot) in sorted(
            [x for x in results if x[4] >= 96], key=lambda x: x[3]):
        print(f"  gap{gp} hold{hd} after{af} → {per:.3f}s/格  命中 {rate:.0f}%", flush=True)
    print("\n=== 全部结果（按实测 s/格）===", flush=True)
    for (gp, hd, af, per, rate, hit, tot) in sorted(results, key=lambda x: x[3]):
        est = 98 * per + (tot - hit) * 0.34
        print(f"  gap{gp} hold{hd} after{af} → {per:.3f}s/格  命中 {rate:.0f}%"
              f"  预估整关涂+补点 {est:.1f}s", flush=True)
