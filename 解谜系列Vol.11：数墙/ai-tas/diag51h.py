import os, sys, time
os.environ["V11_DIFF"]="むずかしい"
sys.path.insert(0, "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas")
import mode2_fast as m
m.ensure_select()
m.goto_level_cell(51)
ds_press = __import__("ds")
ds_press.press("x", wait=0.3, hold=0.05)
time.sleep(6.0)
print("enter -> rect_oc/or:", m.rect_oc(), m.rect_or(), " clue_match(50):", m.clue_match(50))
# 用 _blind 钳位归零（36 宽 oc_max=26, or_max=10）
m._blind("Left", 9 + 26 + 3)
m._blind("Up", 9 + 10 + 3)
time.sleep(0.5)
print("after _blind clamp -> rect_oc/or:", m.rect_oc(), m.rect_or(), " clue_match(50):", m.clue_match(50))
# 确认确实是 l51：广扫
best=None
for idx in range(40,80):
    ok,_=m.clue_match(idx)
    if best is None or ok>best[1]: best=(idx,ok)
print("best match idx:", best, "=> lvl", best[0]+1)
ds_press.grab("diag_l51_clamped")
