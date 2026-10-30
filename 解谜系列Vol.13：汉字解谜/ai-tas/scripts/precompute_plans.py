#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""并行预生成模式1 L/R 规划，汇总写入统一仓库 `validation/plans.json`。

背景：`lr_plan.make_plan` 中1 实测 ~15s（束搜索 400 iters / 15.5s）。逐关在批处理里
现算会白等 15s × 关数（167 关 ≈ 42min，且发生在游戏计时器之外、不进截图）。
本脚本用多核一次性并行算好；批处理侧 `lr_plan.make_plan` 自动读仓库，0s 命中。

★ 2026-10-15：三个 plans 目录（`plans/`、`plans_mode2/`、`plans_by_rec/`）已合并成
  单个 `validation/plans.json`（列表第 n 项 = rec n，见 plan_store.py）。本脚本相应改为
  **父进程汇总后一次性 save()** —— worker 只算不写，避免多进程对同一文件读—改—写互相覆盖。

用法：
  python3 precompute_plans.py                  # 三难度全部关卡
  python3 precompute_plans.py futsuu           # 只 futsuu
  python3 precompute_plans.py --force muzukashii
  python3 precompute_plans.py --jobs 16
"""
import argparse
import multiprocessing as mp
import os
import sys
import time

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
SCRIPTS = os.path.join(REPO, 'ai-tas', 'scripts')
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, REPO)

import plan_store as PS      # noqa: E402
import kanji_common as KC    # noqa: E402

COUNTS = {'yasashii': 35, 'futsuu': 60, 'muzukashii': 65}
FLUSH = 20                   # 每攒 20 条 save 一次：中途被杀也只丢最后一批


def _work(task):
    """算一关并原样返回（不落盘）——落盘由父进程汇总后一次性 save()。"""
    diff, level, force = task
    rec = KC.rec_for(1, diff, level)
    if not force and PS.has(rec):
        return (diff, level, 'skip', 0.0, '', None)
    os.environ['AI_TAS_DIFFICULTY'] = diff
    os.environ.pop('AI_TAS_PLAN_FILE', None)
    sys.path.insert(0, SCRIPTS)
    sys.path.insert(0, REPO)
    # ★ kanji_common.DIFF 是**导入时快照**（读 AI_TAS_DIFFICULTY），而 mp.Pool 的
    #   fork worker 会连 sys.modules 一起继承父进程的那份 —— 不弹掉的话，
    #   plan_fast.solve → K.rec_for_level 会一律按父进程难度映射，算错关。
    #   弹掉后下面 `import lr_plan` 会按本任务刚设好的难度重新导入、重新快照。
    for m in ('kanji_common', 'plan_fast', 'lr_plan', 'plan_store'):
        sys.modules.pop(m, None)
    import lr_plan                                 # noqa: E402
    t0 = time.time()
    try:
        # use_cache=False：跳过已由父进程判过的仓库缓存，强制重算（--force 用）
        res = lr_plan.make_plan(level, verbose=False, use_cache=False)
    except SystemExit as e:
        return (diff, level, 'FAIL', time.time() - t0, str(e), None)
    if not res or not res.get('seq'):
        return (diff, level, 'NOWRITE', time.time() - t0, '未产出序列', None)
    res['rec'] = rec
    res['mode'] = 1
    res['diff'] = diff
    res['level'] = level
    return (diff, level, 'ok', time.time() - t0,
            '箭头%d 跳%d 触%d 页%d 预估%.2fs'
            % (res['n_arrow'], res['n_hop'], res['n_touch'], res['n_page'],
               res.get('pred_fill_s', -1)), res)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('diffs', nargs='*', default=None)
    ap.add_argument('--jobs', type=int, default=0)
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args()
    diffs = a.diffs or list(COUNTS)
    for d in diffs:
        if d not in COUNTS:
            raise SystemExit('未知难度 %s（可用：%s）' % (d, list(COUNTS)))
    tasks = [(d, L, a.force) for d in diffs for L in range(1, COUNTS[d] + 1)]
    jobs = a.jobs or min(len(tasks), os.cpu_count() or 4)
    print('预生成 L/R 规划：%d 关，难度 %s，并发 %d → %s'
          % (len(tasks), diffs, jobs, PS.path()))
    t0 = time.time()
    ok = fail = skip = 0
    pending = {}
    with mp.Pool(jobs, maxtasksperchild=1) as pool:
        for i, (d, L, st, dt, info, res) in enumerate(pool.imap_unordered(_work, tasks), 1):
            if st == 'ok':
                ok += 1
                if res is not None:
                    pending[res['rec']] = res
            elif st == 'skip':
                skip += 1
            else:
                fail += 1
            if st not in ('skip',):
                print('  [%d/%d] %s No.%02d %s %.1fs  %s'
                      % (i, len(tasks), d, L, st, dt, info), flush=True)
            if len(pending) >= FLUSH:
                PS.save(pending)
                pending.clear()
    if pending:
        PS.save(pending)
    print('完成：ok=%d skip=%d fail=%d，仓库现有 %d 条，总耗时 %.1fs'
          % (ok, skip, fail, PS.stats()['cached'], time.time() - t0))


if __name__ == '__main__':
    main()
