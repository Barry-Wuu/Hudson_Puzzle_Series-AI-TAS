import os, sys, time
os.environ["V11_DIFF"]="むずかしい"
sys.path.insert(0, "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas")
import mode2_fast as m
import ds
m.ensure_select()
m.goto_level_cell(51)
ds.press("x", wait=0.3, hold=0.05)
time.sleep(12.0)
print("after 12s wait -> rect_oc/or:", m.rect_oc(), m.rect_or(), " clue_match(50):", m.clue_match(50))
m._blind("Left", 9 + 26 + 3)
m._blind("Up", 9 + 10 + 3)
time.sleep(0.5)
print("after _blind -> rect_oc/or:", m.rect_oc(), m.rect_or(), " clue_match(50):", m.clue_match(50))
best=None
for idx in range(40,80):
    ok,_=m.clue_match(idx)
    if best is None or ok>best[1]: best=(idx,ok)
print("best match idx:", best)
ds.grab("diag_l51_wait12")
