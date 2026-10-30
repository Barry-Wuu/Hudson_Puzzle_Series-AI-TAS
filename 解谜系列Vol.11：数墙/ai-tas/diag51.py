import os, sys, time
os.environ["V11_DIFF"]="むずかしい"
sys.path.insert(0, "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas")
import mode2_fast as m
import ds
print("PUZ len:", len(m.PUZ), "lvl51 w/h:", m.PUZ[50]["w"], m.PUZ[50]["h"])
print("ensure_select:", m.ensure_select())
m.goto_level_cell(51)
ds.press("x", wait=0.3, hold=0.05)
time.sleep(3.5)
st = m.state()
print("state after enter:", st)
ds.grab("diag_l51_enter")
ok,tot = m.clue_match(50)
print("clue_match(50) BEFORE reset:", ok, tot)
# 强力归位（36 宽需最多 26 次 Left）
ds.press_n("Left", 30, 0.20)
ds.press_n("Up", 20, 0.20)
time.sleep(1.0)
ok2,tot2 = m.clue_match(50)
print("clue_match(50) AFTER  reset:", ok2, tot2)
# 同时试一下 clue_match 在 oc 扫描下最佳
print("w_best_offset:", m.w_best_offset(50))
