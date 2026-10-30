import os, sys, time
os.environ["V11_DIFF"]="むずかしい"
sys.path.insert(0, "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas")
import mode2_fast as m
import ds
m.ensure_select()
m.goto_level_cell(51)
ds.press("x", wait=0.3, hold=0.05)
time.sleep(6.0)
print("entry settle done. rect_oc/or:", m.rect_oc(), m.rect_or())
for i in range(4):
    before=(m.rect_oc(), m.rect_or())
    m._hold_key("Left", 2.0)
    time.sleep(0.5)
    after=(m.rect_oc(), m.rect_or())
    print(f"  hold Left 2s #{i}: {before} -> {after}")
# 然后试 tap 棋盘聚焦后再按住
ds.tap(120, 100, after=0.4); time.sleep(0.4)
b2=(m.rect_oc(), m.rect_or())
m._hold_key("Left", 3.0)
time.sleep(0.5)
a2=(m.rect_oc(), m.rect_or())
print("after tap-focus + hold Left 3s:", b2, "->", a2)
