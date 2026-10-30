#!/usr/bin/env python3
"""读「选关页」每关的 枠の大きさ / 口の数（用于把游戏内关卡锚定到 datasheet 记录号）。

用法：直接跑，会把模式2 やさしい 7 关的选关页截图落到 /tmp/LVP_N.png。
要点（2026-10-14 实测）：
  * 停在选关页，**点未选中的徽章 1 下 = 只移动选中框**（上屏参数随之更新，不进入关卡）；
  * **点当前已选中的徽章 1 下 = 直接进关**（易1 是默认选中项）——早期误记成「一律两下才进关」；
  * 徽章中心 x = 19 + 24*i（i=0..6），y ≈ 83；上屏参数区在 y≈34..136。
配套：读出的「口の数」应与记录槽位区的非零字节数相等，见 PITFALLS §S29。
"""
import os, subprocess, sys, time
os.environ.setdefault('DISPLAY', ':99')
sys.path.insert(0, '/workspace/Kanji/ai-tas/scripts')
import kanji_common as F

subprocess.run(['pkill','-x','desmume-cli'], check=False); time.sleep(2)
subprocess.run(['bash','/workspace/Kanji/ai-tas/scripts/ensure_env.sh'], check=False, capture_output=True)
time.sleep(F.INIT_WAIT)
F.tap(128,100, after=F.NAV_TAP_AFTER); F.tap(95,76, after=F.NAV_TAP_AFTER); time.sleep(3.0)
F.tap(136,96, after=F.NAV_TAP_AFTER); F.tap(136,96, after=F.NAV_TAP_AFTER); time.sleep(2.0)
F.tap(135,59, after=F.NAV_TAP_AFTER); time.sleep(2.0)
F.tap(135,59, after=F.NAV_TAP_AFTER); time.sleep(2.5)
F.shot('/tmp/LVP_1.png')            # 默认（易1）
print('选关页默认 -> LVP_1', flush=True)
for i in range(2, 8):
    F.tap(19 + 24*(i-1), 83, after=0.8)     # ★ 只点 1 下，预期只移动选中框
    time.sleep(1.4)
    F.shot('/tmp/LVP_%d.png' % i)
    print('易%d -> /tmp/LVP_%d.png' % (i, i), flush=True)
