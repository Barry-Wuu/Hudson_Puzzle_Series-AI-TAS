import os, sys, time
os.environ["V11_DIFF"]="むずかしい"
sys.path.insert(0, "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas")
import mode2_fast as m
import ds
m.ensure_select()
m.scroll_select_edge(down=True)
time.sleep(0.5)
ds.grab("diag_sel_p2_v")          # 第2页选关（滚动到底）
m.goto_level_cell(51)
time.sleep(0.5)
ds.grab("diag_sel_p2_cursor")     # 光标应在 l51
ds.press("x", wait=0.3, hold=0.05)
time.sleep(8.0)
ds.grab("diag_play_afterx")       # 进关后
print("rect_oc/or:", m.rect_oc(), m.rect_or())
