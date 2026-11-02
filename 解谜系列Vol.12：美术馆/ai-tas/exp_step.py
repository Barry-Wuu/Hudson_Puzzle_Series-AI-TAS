import sys, time, subprocess
sys.path.insert(0, ".")
import numpy as np
from play_akari_seg3 import grab_np
import ds

def step_ascii(tag):
    a = grab_np()
    reg = a[317:329, 214:242]
    R, G, B = reg[:,:,0], reg[:,:,1], reg[:,:,2]
    m = ((R>170)&(G>130)&(B<130)&(R.astype(int)+G.astype(int)-2*B.astype(int)>120)).astype(int)
    print(f"--- {tag}")
    for row in m:
        print(''.join('#' if v else '.' for v in row))

step_ascii("初始")
ds.press("Right", wait=0.35, hold=0.02)
step_ascii("Right x1 后")
subprocess.run(["xdotool","keydown","Right","sleep","0.5","keyup","Right"], env=ds.ENV)
time.sleep(0.4)
step_ascii("hold Right 0.5s 后")
ds.press("x", wait=1.0)
time.sleep(1.2)
step_ascii("A(x) 后")
