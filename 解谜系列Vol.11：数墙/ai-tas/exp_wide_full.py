#!/usr/bin/env python3
"""18×10 宽盘整关实测：对比不同 TAP_WIDE 剂量下的真实 TIME。

背景（2026-10-25）：用户从录像肉眼看出 81 的涂墙频率明显慢于 80。
  - 10×10: TAP(0.02/0.04/0.01) = 0.07s/格 → lvl80 TIME 4s
  - 18×10: TAP_WIDE(0.04/0.06/0.02) = 0.12s/格 → lvl81 TIME 14s
剂量网格实测结论（lvl81 段a 55 格，三轮共 30 档）：
  - hold ≥ 0.055 是硬线（按下时长不够不算一次涂格）
  - hold+after ≥ 0.08 是硬线（松开后需静默期让游戏结算）
  - gap 0.04 → 0.02 无损（现役 gap 是纯冗余）
  - 最小可行剂量 = 0.02/0.06/0.02 = 0.100s/格，命中 96%

本脚本：直接改 mode2_fast.TAP_WIDE 后跑整关，读通关页 TIME。

用法：python3 exp_wide_full.py <lvl> <gap> <hold> <after>
"""
import sys
import time

sys.path.insert(0, "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas")
import ds
from PIL import Image
import mode2_fast as M

LVL = int(sys.argv[1]) if len(sys.argv) > 1 else 81
GAP = float(sys.argv[2]) if len(sys.argv) > 2 else 0.02
HOLD = float(sys.argv[3]) if len(sys.argv) > 3 else 0.06
AFTER = float(sys.argv[4]) if len(sys.argv) > 4 else 0.02

# 关键：覆盖剂量常量后再跑整关
M.TAP_WIDE = dict(gap=GAP, hold=HOLD, after=AFTER)
M.VERIFY_WIDE = dict(gap=0.06, hold=0.06, after=0.22)

walls = M.walls_of(LVL - 1)
print(f"=== lvl{LVL} 整关实测 TAP_WIDE gap={GAP} hold={HOLD} after={AFTER} "
      f"({GAP+HOLD+AFTER:.3f}s/格) 墙={len(walls)} ===", flush=True)

if not M.ensure_select():
    print("FAIL select", flush=True)
    sys.exit(1)

t0 = M.enter_level(LVL)
if t0 is None:
    print("FAIL enter", flush=True)
    sys.exit(1)

# ★ 与正式管线完全一致：解锁探针（涂黑后保持涂黑，burst 排除该格）
walls = M.walls_of(LVL - 1)
a_all = [(r, c) for r, c in walls if c < 10]
probe = next(((r, c) for r, c in a_all if r < 10 and c < 10), None)
tu = time.time()
if probe is not None:
    M.wait_unlocked(LVL - 1, probe)
else:
    time.sleep(M.UNLOCK)
print(f"unlock_probe {time.time()-tu:.2f}s skip={probe}", flush=True)

a = [w for w in a_all if w != probe]
b = [(r, c) for r, c in walls if c >= 10]
print(f"段a={len(a)} 段b={len(b)} 理论纯涂={len(walls)*(GAP+HOLD+AFTER):.2f}s", flush=True)

t_start = time.time()
for oc, seg in ((0, a), (8, b)):
    if not M.hold_scroll(oc):
        print(f"  scroll oc{oc} FAIL", flush=True)
        continue
    tb = time.time()
    ds.tap_batch([M.cell_nds(r, c) if oc == 0 else (24 + 16 * (c - 8), 24 + 16 * r)
                  for r, c in seg], **M.TAP_WIDE)
    M.safe_mouseup()
    el = time.time() - tb
    print(f"  oc{oc} 连涂 {el:.2f}s ({el/len(seg):.3f}s/格, {len(seg)} 格)", flush=True)
    time.sleep(1.2)
    g = M.board_gray()
    miss = [(r, c) for r, c in seg if M.cell_state(g, r, c - oc) == "W"]
    print(f"  oc{oc} topup={len(miss)}", flush=True)
    if miss:
        tb2 = time.time()
        ds.tap_batch([(24 + 16 * (c - oc), 24 + 16 * r) for r, c in miss], **M.VERIFY_WIDE)
        M.safe_mouseup()
        print(f"  oc{oc} 补点 {len(miss)} 格 {time.time()-tb2:.2f}s", flush=True)
        # ★ 补点后必须沉降：补点点击的 toggle 尚未结算就滚屏 → 该格仍算「未涂」
        #   → 游戏记为改答案 → 掉星（2026-10-25 实测 1★ vs 正式管线 4★）
        time.sleep(1.2)

fill_total = time.time() - t_start
cleared = M.wait_clear(5.0)
print(f"  填充总耗时 {fill_total:.2f}s  通关判定={cleared}  墙钟总={time.time()-t_start:.2f}s", flush=True)

if cleared:
    # ★ 必须等金星动画画完再截图：正式管线 sleep 2.5s，动画逐颗点亮，
    #   早截会读到「正在点亮」的过程帧（恒为 1★，与剂量无关 —— 曾误判掉星）
    time.sleep(2.5)
    im = ds.grab(None)
    im.save(f"/tmp/full_l{LVL}_g{GAP}_h{HOLD}_a{AFTER}.png")
    im.crop((0, 192, 256, 384)).resize((512, 384), Image.LANCZOS).save(
        f"/tmp/full_l{LVL}_g{GAP}_h{HOLD}_a{AFTER}_small.png")
    # 读星数（复用 mode2_fast.stars_gold，与 check_evidence.py 同一实现）
    st = M.stars_gold(im)
    # TIME 横幅数字区（y245-320 是横幅带，数字在其内）
    im.crop((30, 240, 226, 322)).resize((588, 246), Image.LANCZOS).save(
        f"/tmp/full_l{LVL}_g{GAP}_h{HOLD}_a{AFTER}_time.png")
    print(f"  星数={st}  截图: /tmp/full_l{LVL}_g{GAP}_h{HOLD}_a{AFTER}.png", flush=True)
else:
    print("  未通关（未判定）", flush=True)
