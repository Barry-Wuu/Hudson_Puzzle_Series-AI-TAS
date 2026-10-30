import sys, time
sys.path.insert(0, ".")
from cal_hold import PZ
from play_akari_seg3 import light_big, wait_clear
pz = PZ[31]
t0 = time.time()
miss = light_big(pz)
print("miss:", miss, "| light_big 耗时 %.1fs" % (time.time() - t0), flush=True)
print("wait_clear:", wait_clear(12), flush=True)
