#!/usr/bin/env python3.11
"""端到端录制: 清档->导航->第1关盘面->录屏->集合覆盖填字->通关->停录。"""
import os, sys, time, subprocess
import ds
from enter_q1 import navigate

OUT = os.path.join(os.path.dirname(ds.BASE),
                   "vol8_やさしい_Q01_集合覆盖最速_libopenh264.mp4")


def record():
    time.sleep(1.2)
    ds.grab("cvrec_ready")
    log = open("/tmp/cvrec_ff.log", "w")
    cmd = ["ffmpeg", "-y", "-f", "x11grab", "-r", "30", "-video_size", "256x384",
           "-i", ":99+384,192", "-c:v", "libopenh264", "-profile:v", "high",
           "-b:v", "2500k", "-pix_fmt", "yuv420p", OUT]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=log, stderr=log)
    print("REC START", flush=True)
    time.sleep(0.8)
    sys.argv = ["fast_solve_cover.py", "1", "0.40"]
    import fast_solve_cover as F
    F.main()
    time.sleep(4.0)
    ds.grab("cvrec_result")
    try:
        proc.stdin.write(b"q\n"); proc.stdin.flush()
    except Exception:
        proc.terminate()
    proc.wait(timeout=30)
    log.close()
    print("REC DONE", os.path.getsize(OUT) if os.path.exists(OUT) else "NOFILE", flush=True)


if __name__ == "__main__":
    if not navigate():
        print("!! 未进盘面, 放弃录制", flush=True)
        sys.exit(1)
    record()
