import os, sys, time
os.environ["V11_DIFF"]="むずかしい"
sys.path.insert(0, "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas")
import mode2_fast as m
import ds
m.ensure_select()
m.goto_level_cell(51)
ds.press("x", wait=0.3, hold=0.05)
time.sleep(3.5)
print("BEFORE -> w_best_offset(50):", m.w_best_offset(50), " clue_match:", m.clue_match(50))
# 先点棋盘聚焦（模仿 fill 的第一步）
ds.tap(120, 100, after=0.4)
time.sleep(0.4)
m._hold_key("Left", 5.0)
m._hold_key("Up", 4.0)
time.sleep(0.8)
print("AFTER focus+hold -> w_best_offset(50):", m.w_best_offset(50), " clue_match:", m.clue_match(50))
# 广扫确认是否真是 l51
best=None
for idx in range(40, 80):
    ok,_=m.clue_match(idx)
    if best is None or ok>best[1]: best=(idx,ok)
print("best idx:", best, "=> lvl", best[0]+1)
ds.grab("diag_l51_focusfixed")
