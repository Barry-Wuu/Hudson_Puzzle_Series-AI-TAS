#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI_TAS 计时基线/对比台（nav / fill / settle 分段墙钟 + spawn 探针）。

用法:
  python3 measure_bench.py <level> [--cold] [--lr] [KEY=VALUE ...]
    --cold   走全链路冷启动导航（首次建立状态用）；否则走暖路径 warm-nav
    --lr     用 lr_plan（L/R 跳跃）序列；否则 plan_fast
    KEY=VALUE 在 import kanji_common 前注入环境变量（如 TAP_AFTER=0.05）

输出: nav / fill / settle 分段墙钟 + 动作计数 + 每动作均值 + spawn 探针。
★ 不碰帧率：绝不设 FAST_KEY / frameskip。
★ 判定只看 do_settle 打印的「蓝% / 灰%」（level_cleared），不搞自造像素判据（PITFALLS C2d）。
"""
import os
import sys
import time

ARGS = sys.argv[1:]
level = 35
cold = '--cold' in ARGS
use_lr = '--lr' in ARGS
env_overrides = {}
# 短名 -> kanji_common / fill_fast_any 实际读取的 AI_TAS_* 环境变量
SHORT2ENV = {
    'TAP_AFTER': 'AI_TAS_TAP_AFTER',
    'TAP_HOLD': 'AI_TAS_TAP_HOLD',
    'MOVE_GAP': 'AI_TAS_MOVE_GAP',
    'KEY_HOLD': 'AI_TAS_KEY_HOLD',
    'NAV_AFTER': 'AI_TAS_NAV_AFTER',
    'NAV_ENTER': 'AI_TAS_NAV_ENTER_WAIT',
    'PANEL_WAIT': 'AI_TAS_PANEL_WAIT',
    'SEIKAI_WAIT': 'AI_TAS_SEIKAI_WAIT',
    'PAGE_WAIT': 'AI_TAS_PAGE_WAIT',
    'SETTLE_POLL': 'AI_TAS_SETTLE_POLL',
}
for a in ARGS:
    if a.startswith('--'):
        continue
    if '=' in a:
        k, v = a.split('=', 1)
        env_overrides[SHORT2ENV.get(k, k)] = v

for k, v in env_overrides.items():
    os.environ[k] = v

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
import kanji_common as F          # noqa: E402
import fill_fast_any as FA         # noqa: E402


def probe_spawn():
    """测量单次 tap / hop 的真实墙钟（含子进程开销）。"""
    print('--- spawn 探针 ---')
    # tap
    t = time.time()
    F.tap(100, 100, after=0.0, hold=0.0)
    dt_tap = time.time() - t
    # hop (key_press: 2 次 spawn)
    t = time.time()
    F.hop('w', after=0.0, hold=0.0)
    dt_hop = time.time() - t
    # 纯 xdotool 一次 spawn 耗时
    t = time.time()
    import subprocess
    subprocess.run(['xdotool', 'getdisplaygeometry'], env=F.ENV, check=False)
    dt_xdo = time.time() - t
    print('  tap(含 after0/hold0) = %.3fs | hop = %.3fs | 单次 xdotool spawn = %.3fs'
          % (dt_tap, dt_hop, dt_xdo))


def run():
    print('=== 配置 ===')
    print('  DIFF=%s level=%d plan=%s cold=%s'
          % (F.DIFF, level, 'lr' if use_lr else 'fast', cold))
    print('  TAP_AFTER=%.3f TAP_HOLD=%.3f TAP_MOVE_GAP=%.3f KEY_HOLD=%.3f'
          % (F.TAP_AFTER, F.TAP_HOLD, F.TAP_MOVE_GAP, F.KEY_HOLD))
    print('  NAV_TAP_AFTER=%.3f NAV_ENTER_WAIT=%.3f PANEL_WAIT=%.3f SEIKAI_WAIT=%.3f PAGE_WAIT=%.3f SETTLE_POLL=%.3f'
          % (F.NAV_TAP_AFTER, F.NAV_ENTER_WAIT, FA.PANEL_WAIT, FA.SEIKAI_WAIT,
             FA.PAGE_WAIT, F.SETTLE_POLL))

    # --- nav ---
    if cold:
        t0 = time.time()
        F.nav_to_fill(level, warm=False)
        nav_dt = time.time() - t0
    else:
        t0 = time.time()
        x, y = F.level_xy(level)
        F.tap(x, y, after=F.NAV_TAP_AFTER)
        F.tap(x, y, after=F.NAV_TAP_AFTER)
        time.sleep(F.NAV_ENTER_WAIT)
        nav_dt = time.time() - t0

    # --- fill ---
    res, fill_dt = FA.do_fill(level, plan_mode='lr' if use_lr else None)

    # --- settle ---
    t0 = time.time()
    FA.do_settle(level)
    settle_dt = time.time() - t0

    nt = res['n_touch']
    na = res['n_arrow']
    nh = res.get('n_hop', 0)
    npg = res.get('n_page', 0)
    total_act = nt + na + nh + npg
    # 注意：do_fill 的 dt 只含「动作循环」，PANEL_WAIT/SEIKAI_WAIT 在循环外（开面板延迟+填后缓冲）
    fixed_wait = FA.PANEL_WAIT + FA.SEIKAI_WAIT
    true_total = nav_dt + fill_dt + settle_dt + fixed_wait
    print('=== 分段计时 (level %d, %s) ===' % (level, 'lr' if use_lr else 'fast'))
    print('  nav    = %.2fs' % nav_dt)
    print('  fill(loop) = %.2fs  (动作循环；PAGE_WAIT 已含内)' % fill_dt)
    print('  settle = %.2fs' % settle_dt)
    print('  PANEL_WAIT+SEIKAI_WAIT = %.2fs (循环外固定等待)' % fixed_wait)
    print('  TOTAL(真) = %.2fs' % true_total)
    print('  动作: touch=%d arrow=%d hop=%d page=%d 合计=%d' % (nt, na, nh, npg, total_act))
    if total_act:
        print('  每动作均值(loop) = %.3fs' % (fill_dt / total_act))
    probe_spawn()


if __name__ == '__main__':
    run()
