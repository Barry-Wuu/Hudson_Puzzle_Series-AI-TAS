#!/usr/bin/env python3.11
"""端到端录一关: 冷启动->跳教程->进第2关->ffmpeg录制->填字->结算->停录。

录制抓 Xvfb :99 的 DeSmuME 窗口区域 256x384, libx264 重编码防花屏。
剂量 after=0.40 (接近已验证稳定的 0.45, 去掉空点/reset/多进程开销)。
"""
import os, sys, time, subprocess
import numpy as np
import ds
import fast_solve_vol8 as F

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "vol8_q2_record.mp4")
LEVEL_ARG = "1"


def tap(x, y, a1=0.6, a2=None):
    ds.tap(x, y, after=a1)
    if a2 is not None:
        ds.tap(x, y, after=a2)


def key(k, hold=0.12):
    for phase in ("keydown", "keyup"):
        subprocess.run(["xdotool", phase, k], env=ds.ENV)
        if phase == "keydown":
            time.sleep(hold)


def focus():
    w = ds.ensure_window()
    subprocess.run(["xdotool", "windowfocus", w], env=ds.ENV)
    time.sleep(0.35)


def is_fill_board(im):
    """检测填字盘面: 上屏右上角计时器是黑底白字, 单词本/菜单那里是灰图标背景。"""
    a = np.asarray(im.convert("RGB"))
    # 上屏右上角计时器区(整图 x=195..255, y=2..20)
    tr = a[2:20, 195:255]
    dark = ((tr[:, :, 0] < 60) & (tr[:, :, 1] < 60) & (tr[:, :, 2] < 60)).mean()
    # 下屏假名键盘区(整图 y=270..380)文字密集 -> 边缘多
    kb = a[270:380, 5:250]
    kb_nonbg = (kb.mean(axis=2) < 100).mean()   # 假名是深色字
    ok = dark > 0.25 and kb_nonbg > 0.05
    return dark, ok


def keyA_long(hold=0.5):
    subprocess.run(["xdotool", "keydown", "x"], env=ds.ENV); time.sleep(hold)
    subprocess.run(["xdotool", "keyup", "x"], env=ds.ENV); time.sleep(2.0)


def navigate():
    ds.kill()
    ds.start()
    focus()
    time.sleep(2.0)
    # 欢迎页 -> 触摸
    ds.tap(128, 150, after=1.0)
    # 游戏菜单 スタート(128,47) 触摸选中, 再用A确认(避免双击误触データ消去)
    ds.tap(128, 47, after=0.8)
    key("x"); time.sleep(2.0)
    # 教程实操页: 触摸激活 + 长按 w(R) 跳过
    ds.tap(128, 150, after=0.4)
    subprocess.run(["xdotool", "keydown", "w"], env=ds.ENV); time.sleep(1.9)
    subprocess.run(["xdotool", "keyup", "w"], env=ds.ENV); time.sleep(1.3)
    ds.grab("rec_supp_check")
    # サポートなし(128,148)
    tap(128, 148, 0.7, 1.6); time.sleep(1.5)
    # 通常問題(128,79)
    tap(128, 79, 0.7, 1.6); time.sleep(1.5)
    # 难度页 やさしい(128,79) 触摸选中 -> 短按A进预览页
    tap(128, 79, 0.7, 1.6); time.sleep(1.5)
    key("x"); time.sleep(1.5)
    ds.grab("rec_sel_cursor")
    # 在预览页长按A进关(已验证: nr_09 成功, 短按无效)
    focus()
    keyA_long(hold=0.5)
    time.sleep(2.0)
    im = ds.grab("rec_enter")
    bright, ok = is_fill_board(im)
    print(f"进关检测 bright={bright:.3f} ok={ok}", flush=True)
    return ok


def record():
    # ffmpeg: 抓 :99 窗口 256x384, 30fps, libx264
    cmd = ["ffmpeg", "-y", "-f", "x11grab", "-r", "30",
           "-video_size", "256x384", "-i", ":99+384,192",
           "-c:v", "libopenh264", "-profile:v", "high", "-b:v", "2500k",
           "-pix_fmt", "yuv420p", OUT]
    log = open("/tmp/vol8_ffmpeg.log", "w")
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=log, stderr=log)
    print("录制开始", flush=True)
    time.sleep(1.0)
    # 填字 (after=0.40)
    sys.argv = ["fast_solve_vol8.py", LEVEL_ARG, "0.40"]
    F.main()
    # 填完等结算画面
    time.sleep(4.0)
    ds.grab("rec_result")
    # 停录
    try:
        proc.stdin.write(b"q\n"); proc.stdin.flush()
    except Exception:
        proc.terminate()
    proc.wait(timeout=20)
    log.close()
    print(f"录制完成: {OUT}", flush=True)


if __name__ == "__main__":
    if not navigate():
        print("❌ 未进入填字盘面, 中止录制 (见 rec_enter.png)", flush=True)
        sys.exit(1)
    record()
