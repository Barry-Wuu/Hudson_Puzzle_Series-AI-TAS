import os, sys, time
os.environ["V11_DIFF"]="むずかしい"
sys.path.insert(0, "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas")
import mode2_fast as m
import ds
m.ensure_select()
m.goto_level_cell(51)
ds.press("x", wait=0.3, hold=0.05)
time.sleep(3.5)
print("state:", m.state())
print("BEFORE hold-reset -> clue_match(50):", m.clue_match(50), " w_best_offset:", m.w_best_offset(50))
# 按住钳位归零
m._hold_key("Left", 5.0)
m._hold_key("Up", 4.0)
time.sleep(0.8)
print("AFTER  hold-reset -> clue_match(50):", m.clue_match(50), " w_best_offset:", m.w_best_offset(50))
ds.grab("diag_l51_fixed")
