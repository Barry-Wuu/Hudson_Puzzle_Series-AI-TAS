#!/usr/bin/env python3
"""Vol.06《数织 / ILLUST LOGIC》实机填充剂量实测。

用法（沙箱内 DeSmuME + Xvfb 已就绪）：
    python3 probe_dose.py --n 8 --gap 0.012 --hold 0.020 --after 0.003
    python3 probe_dose.py --n 8 --gap 0.012 --hold 0.020 --after 0.003 --restart

「剂量」= 每格一次触摸的三个时间参数（秒）：
    gap   光标移到该格到按下之间的停顿（等模拟器把触笔坐标收进寄存器）
    hold  按下保持（≧1 帧 16.7 ms 才能被 60 fps 的触摸采样看到）
    after 抬起后到下一次移动的停顿

本脚本只做「按答案盘面逐格点一遍 → 读回盘面 → 判定正解」，不做求解。
答案盘面来自 extract_vol6_answers.py 的 validation/puzzles.json。
"""
import argparse
import json
import os
import subprocess
import time

import numpy as np
from PIL import Image

DISPLAY = ':99'
ENV = dict(os.environ, DISPLAY=DISPLAY)
WIN = (512, 320)                 # 模拟器窗口在 1280x1024 虚拟屏上的原点
SHOT = '256x384+512+320'         # 两屏叠合的原生分辨率

# 盘面几何（截图坐标，非屏幕坐标）：由网格线实测得出
#   竖向格线 x = 87,103,119,...,247（10 列 ×16 px，第 5 列后为红色粗线 x=167）
#   横向格线 y = 200,216,...,360（10 行 ×16 px，第 5 行后为红色粗线 y=280）
#   故格子中心 X = 87+8+16c = 95+16c，Y = 200+8+16r = 208+16r
X0, Y0, S, N = 95, 208, 16, 10

ROM = '/workspace/roms/解谜系列Vol.06：数织.nds'
HERE = os.path.dirname(os.path.abspath(__file__))
PUZZLES = os.path.join(HERE, 'validation', 'puzzles.json')


# ---------- 底层输入输出 ----------

def _win_id():
    out = subprocess.run(['xdotool', 'search', '--class', 'desmume'],
                         env=ENV, capture_output=True, text=True).stdout.split()
    if not out:
        raise RuntimeError('没找到 DeSmuME 窗口，先起 Xvfb :99 与 desmume-cli')
    return out[-1]


def shot(path='/tmp/_shot.png'):
    subprocess.run(['import', '-window', 'root', '-crop', SHOT, path], env=ENV, check=True)
    return np.array(Image.open(path).convert('RGB')).astype(int)


def tap(x, y, gap=0.10, hold=0.06):
    """单点触摸；坐标用截图坐标系（自动加窗口偏移）"""
    subprocess.run(['xdotool',
                    'mousemove', str(x + WIN[0]), str(y + WIN[1]), 'sleep', f'{gap:.3f}',
                    'mousedown', '1', 'sleep', f'{hold:.3f}',
                    'mouseup', '1'], env=ENV, check=True)


def taps(cells, gap, hold, after):
    """批量逐格点；整串动作塞进一次 xdotool 调用，省掉进程启动开销"""
    args = []
    for (x, y) in cells:
        args += ['mousemove', str(x + WIN[0]), str(y + WIN[1]), 'sleep', f'{gap:.3f}',
                 'mousedown', '1', 'sleep', f'{hold:.3f}',
                 'mouseup', '1', 'sleep', f'{after:.3f}']
    subprocess.run(['xdotool'] + args, env=ENV, check=True)


# ---------- 画面判定 ----------

def blank_ok(img):
    """空板自检：100 格中心都是米白/黄高亮"""
    n = 0
    for r in range(N):
        for c in range(N):
            x, y = X0 + c * S, Y0 + r * S
            m = np.median(img[y - 4:y + 5, x - 4:x + 5].reshape(-1, 3), axis=0)
            n += bool(m[0] > 240 and m[1] > 220 and 100 < m[2] < 240)
    return n


def banner(img):
    """「正解」橙字横幅像素数：1500 以上=通关，<100=未通关（实测 1743 / 37~99）"""
    z = img[250:312, 50:205]
    o = (z[:, :, 0] > 200) & (60 < z[:, :, 1]) & (z[:, :, 1] < 190) & (z[:, :, 2] < 100)
    return int(o.sum())


def filled_map(img, ref):
    """与空板逐格比对（未通关时可用；通关后正解横幅会遮住盘面，只能用 banner 判定）"""
    g = np.zeros((N, N), int)
    for r in range(N):
        for c in range(N):
            x, y = X0 + c * S, Y0 + r * S
            d = np.abs(img[y - 6:y + 7, x - 6:x + 7] - ref[y - 6:y + 7, x - 6:x + 7])
            g[r, c] = int(d.mean() > 45)
    return g


# ---------- 界面导航（实测路径） ----------

def box_x(n):
    """问题选择格中心 x：10 题一行，x = 19 + 23.5·(n-1)"""
    return int(round(19 + 23.5 * (n - 1)))


def enter(n, wait=5.0):
    """问题选择画面 → 第 n 题：点数字格两次弹出确认 → はい"""
    tap(box_x(n), 234); time.sleep(0.5)
    tap(box_x(n), 234); time.sleep(1.2)
    tap(95, 330); time.sleep(wait)          # はい；等「10x10問題 No.X」+ スタート 演出


def restart(wait=5.0):
    """盘面上：中断(130,374) → やり直し(128,272) → はい(75,330)"""
    tap(130, 374); time.sleep(1.2)
    tap(128, 272); time.sleep(1.2)
    tap(75, 330); time.sleep(wait)


def to_select(max_try=8):
    """任意画面 → 问题选择：连点下屏推进结算/存档，直到顶部红底标题出现"""
    for i in range(max_try):
        img = shot()
        z = img[12:48, 8:248]
        if ((z[:, :, 0] > 140) & (z[:, :, 1] < 90) & (z[:, :, 2] < 90)).sum() > 300:
            return True
        tap(128, 300); time.sleep(3.0)
    return False


# ---------- 主流程 ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, required=True, help='10x10 题号 1..50（题号=idx+1）')
    ap.add_argument('--gap', type=float, default=0.012)
    ap.add_argument('--hold', type=float, default=0.020)
    ap.add_argument('--after', type=float, default=0.003)
    ap.add_argument('--restart', action='store_true', help='不重新进题，只把当前题重开')
    ap.add_argument('--tag', default='run')
    a = ap.parse_args()

    P = json.load(open(PUZZLES))[a.n - 1]
    cells = [(X0 + c * S, Y0 + r * S)
             for r in range(N) for c in range(N) if P['grid'][r][c]]

    if a.restart:
        restart()
    else:
        if not to_select():
            raise SystemExit('没能回到问题选择画面')
        enter(a.n)

    ref = shot(f'/tmp/ref_{a.tag}.png')
    if blank_ok(ref) != 100:
        raise SystemExit(f'盘面不是空白（{blank_ok(ref)}/100 格为底色），先 restart')

    t0 = time.time()
    taps(cells, a.gap, a.hold, a.after)
    dt = time.time() - t0
    time.sleep(1.6)
    img = shot(f'/tmp/post_{a.tag}.png')

    per = (a.gap + a.hold + a.after) * 1000
    ok = banner(img)
    g = filled_map(img, ref)
    bad = [(r, c) for r in range(N) for c in range(N) if g[r][c] != P['grid'][r][c]]
    print(f'第{a.n}題 ink={len(cells)} 剂量 {a.gap}/{a.hold}/{a.after} = {per:.0f} ms/格')
    print(f'实测 {dt:.2f}s（{dt/len(cells)*1000:.0f} ms/格），正解横幅={ok} → '
          f'{"通关" if ok > 1500 else "未通关"}')
    if ok < 1500:
        print(f'逐格不符 {len(bad)}：{bad[:16]}')
        for r in range(N):
            print('  ' + ''.join('■' if g[r][c] else '・' for c in range(N)) + '   ' +
                  ''.join('■' if P['grid'][r][c] else '・' for c in range(N)))


if __name__ == '__main__':
    main()
