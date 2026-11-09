#!/usr/bin/env python3.11
# 从 300 支通关录播视频中，为每一关抽取一张「正解」画面帧，
# 按难度分文件夹存放（mode1_easy / mode2_medium / mode3_hard，编号＝游戏难度菜单序号），
# 文件名沿用其他卷约定：lNNN_clear.png（NNN 为该难度内连续编号 001..N）。
#
# 识别方法：游戏 UI 五颜六色，颜色统计 / OCR / 模板匹配均不可靠；
# 唯一稳定信号是「正解」二字的黄色填充（低蓝值黄，区别于奶油色面板）。
# 正解帧的黄填充量(~3400)远高于对局恒定背景(~460)，故每关扫描多个时刻、
# 用【输入后精确定位】抽取（避免 ffmpeg -ss 关键帧吸附导致相邻时刻抽到不同画面），
# 取黄填充量最大的那一帧作为正解帧。
import os, re, subprocess, glob
from concurrent.futures import ThreadPoolExecutor
from PIL import Image

SRC = '/workspace/Vol.3_全关录播'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'validation')
DIFF_MAP = {'やさしい': 'mode1_easy', 'ふつう': 'mode2_medium', 'むずかしい': 'mode3_hard'}
STEP = 2.0   # 中段粗采样步长（秒）
TAIL = 7.0    # 尾部密集采样覆盖长度（秒）——正解必在片尾出现，必须覆盖到真实结尾
TAIL_STEP = 0.3  # 尾部密集采样步长（秒）
BOX = (0.24, 0.60, 0.76, 0.82)  # 正解二字所在的下方区域


def dur(v):
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                        '-of', 'default=nw=1:nk=1', v], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def extract_acc(v, t, dst):
    # 输入后精确定位：逐帧解码到 t，帧精确（避免关键帧吸附）
    subprocess.run(['ffmpeg', '-y', '-i', v, '-ss', f'{t:.2f}', '-frames:v', '1',
                    '-q:v', '2', dst, '-loglevel', 'error'], check=True)


def yellow_fill(p):
    im = Image.open(p).convert('RGB'); W, H = im.size; px = im.load()
    x0, x1 = int(W * BOX[0]), int(W * BOX[2]); y0, y1 = int(H * BOX[1]), int(H * BOX[3])
    c = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            r, g, b = px[x, y]
            if r > 200 and g > 170 and b < 90:  # 低蓝值的黄（正解填充），排除奶油面板(B~180)
                c += 1
    return c


def process(args):
    v, diff, num = args
    d = dur(v)
    best = (0, None)  # (yellow, t)
    ts = []
    # 中段粗采样：避开片头（开始界面黄色数字面板会误判）与片尾
    coarse_end = max(2.0, d - TAIL)
    t = 2.0
    while t <= coarse_end:
        ts.append(round(t, 2)); t += STEP
    # 尾部密集采样：正解（通关结算大字）必出现在片尾，必须覆盖到真实结尾，
    # 用 0.3s 步长保证不漏掉极窄的结算窗口（尤其是每档最后一关会跳列表/存档页）
    tt = max(2.0, d - TAIL)
    while tt <= d - 0.08:
        ts.append(round(tt, 2)); tt += TAIL_STEP
    seen = set()
    ts = [x for x in ts if not (x in seen or seen.add(x))]
    for t in ts:
        tmp = f'/tmp/v3y_{diff}_{num}_{int(t*10)}.png'
        try:
            extract_acc(v, t, tmp)
            s = yellow_fill(tmp)
        except Exception:
            continue
        if s > best[0]:
            best = (s, t)
    # 重抽最佳时刻，保证画质
    dst = os.path.join(OUT, DIFF_MAP[diff], f'l{num:03d}_clear.png')
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        extract_acc(v, best[1], dst)
    except Exception:
        pass
    return diff, num, best[0], best[1], os.path.getsize(dst) if os.path.exists(dst) else 0


def main():
    pat = re.compile(r'Vol\.3_数独_(やさしい|ふつう|むずかしい)_(\d+)_')
    jobs = []
    for v in sorted(glob.glob(os.path.join(SRC, '*.mp4'))):
        m = pat.search(os.path.basename(v))
        if not m:
            continue
        jobs.append((v, m.group(1), int(m.group(2))))
    print('任务数:', len(jobs))
    low = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for i, (diff, num, score, t, sz) in enumerate(ex.map(process, jobs), 1):
            if score < 1500:
                low.append((diff, num, score, t))
            if i % 30 == 0 or i == len(jobs):
                print(f'  {i}/{len(jobs)}  最近: {diff} {num:03d} 黄={score} t={t} {sz}B')
    print('黄填充偏低（需人工核对）:', low)
    for diff, folder in DIFF_MAP.items():
        n = len(glob.glob(os.path.join(OUT, folder, '*.png')))
        print(f'  {folder}: {n} 张')


if __name__ == '__main__':
    main()
