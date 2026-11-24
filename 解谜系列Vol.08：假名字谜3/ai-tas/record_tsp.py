#!/usr/bin/env python3.11
"""端到端录制: 清档->冷启动->可靠导航->第1关盘面->录屏->TSP填字->通关->停录。
导航链已在全新档上逐步验证(见标定报告第7节)。"""
import os, sys, time, subprocess
import ds

OUT = os.path.join(os.path.dirname(ds.BASE),
                   "vol8_やさしい_Q01_TSP最速顺序_libopenh264.mp4")
AFTER = "0.40"
LEVEL = "1"


def key(k, hold=0.12, wait=0.3):
    subprocess.run(["xdotool", "keydown", k], env=ds.ENV); time.sleep(hold)
    subprocess.run(["xdotool", "keyup", k], env=ds.ENV); time.sleep(wait)


def focus():
    w = ds.ensure_window()
    subprocess.run(["xdotool", "windowfocus", w], env=ds.ENV)
    time.sleep(0.3)


def navigate():
    ds.start()                            # 启动 desmume(冷启动读全新档)
    focus()
    time.sleep(3.0)                       # 等欢迎页/加载
    ds.tap(128, 150, after=1.2)           # 欢迎页触摸
    ds.tap(128, 47, after=0.7)            # 选中スタート
    key("x", wait=2.0)                    # A -> 教程
    ds.tap(128, 150, after=0.4)           # 教程激活
    # 教程有多步, 反复长按 R 直到离开教程(教程页顶部有"チュートリアル"橙标题)
    for i in range(6):
        key("w", hold=1.9, wait=1.2)
        im = ds.grab(f"tsprec_tut{i}")
        a = __import__("numpy").asarray(im.convert("RGB"))
        # 教程橙标题在上屏顶部 y~0-15, 橙色=r>150,g在80-180,b<100
        top = a[0:16, 0:120]
        orange = ((top[:,:,0] > 150) & (top[:,:,1] > 70) & (top[:,:,1] < 190) & (top[:,:,2] < 110)).mean()
        print(f"  教程步{i}: orange={orange:.3f}", flush=True)
        if orange < 0.05:                  # 标题消失=离开教程
            break
    key("Down", wait=0.3); key("Down", wait=0.3)  # 选中最底 サポートなし
    key("x", wait=1.8)                    # A 确认 -> 主菜单
    key("x", wait=1.8)                    # A 确认 通常問題(默认高亮) -> 难度页
    key("x", hold=0.5, wait=2.5)          # 长按A -> 预览页
    key("x", hold=0.5, wait=2.5)          # 长按A -> 盘面
    im = ds.grab("tsprec_enter")
    a = __import__("numpy").asarray(im.convert("RGB"))
    tr = a[5:22, 190:252]
    dark = ((tr[:, :, 0] < 90) & (tr[:, :, 1] < 90) & (tr[:, :, 2] < 90)).mean()
    print(f"进关检测 timer_dark={dark:.3f}", flush=True)
    return dark > 0.25


def record():
    time.sleep(1.5)                       # 等スタート横幅消失
    ds.grab("tsprec_ready")
    log = open("/tmp/tsprec_ff.log", "w")
    cmd = ["ffmpeg", "-y", "-f", "x11grab", "-r", "30", "-video_size", "256x384",
           "-i", ":99+384,192", "-c:v", "libopenh264", "-profile:v", "high",
           "-b:v", "2500k", "-pix_fmt", "yuv420p", OUT]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=log, stderr=log)
    print("REC START", flush=True)
    time.sleep(0.8)
    sys.argv = ["fast_solve_vol8.py", LEVEL, AFTER]
    import fast_solve_vol8 as F
    F.main()
    time.sleep(4.0)                       # 留通关演出
    ds.grab("tsprec_result")
    try:
        proc.stdin.write(b"q\n"); proc.stdin.flush()
    except Exception:
        proc.terminate()
    proc.wait(timeout=30)
    log.close()
    print("REC DONE", os.path.getsize(OUT) if os.path.exists(OUT) else "NOFILE", flush=True)


if __name__ == "__main__":
    ok = navigate()
    if not ok:
        print("!! 未进盘面, 放弃录制", flush=True)
        sys.exit(1)
    record()
