import os, sys, time
os.environ["V11_DIFF"]="むずかしい"
sys.path.insert(0, "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas")
import mode2_fast as m
import ds
m.ensure_select()
m.goto_level_cell(51)
ds.grab("diag_select51")          # 选关页（光标应在 l51）
ds.press("x", wait=0.3, hold=0.05)
time.sleep(3.5)
ds.grab("diag_play51")            # 进关后
print("state:", m.state())
print("--- 进关后 对 l41..l57 的 clue_match(oc=0) ---")
for idx in range(40, 57):
    ok,tot = m.clue_match(idx)
    if ok >= 70:
        print(f"  idx={idx} (lvl{idx+1}): {ok}/{tot}")
print("--- 当前 w_best_offset(50) ---", m.w_best_offset(50))
