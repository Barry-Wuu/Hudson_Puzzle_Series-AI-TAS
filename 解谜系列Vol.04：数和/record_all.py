#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vol.4（数和 / Kakuro）入門 002~020 批量有声实况录制。

用户本轮要求（逐条落实）：
  * 「把 2 开始入门关卡都录完」= 入門第 2 問 ~ 第 20 問（lv1..lv19）全录。
  * 「有声」= ffmpeg 从 pulse `auto_null.monitor` 录真实游戏声音，不再是静音轨。
  * 「原始分辨率」= 直接抓 desmume 原生 256×384 窗口，不做任何 scale。
  * 「不要黑❌光标」= `-draw_mouse 0` + X11 透明根光标（外部已设置）。

答案来源（用户定调：答案本来就在 bin 里，玩的时候挖出）：
  validation/vol4_all.json —— ROM `CPQ.` 数据块静态提取的 310 关记录表。

盘面分档（本轮静态 + 实机双重确认，勿外推）：
  * 入門 001~010（lv0..9）：head=[k,1,3,7,11]，答案盘 = body 末 36B = 6×6 网格
    缩略盘格心(触屏) = (13+25*(c+.5), 20+25.5*(r+.5))
  * 入門 011~020（lv10..19）：head=[k,1,4,8,12]，答案盘 = body 末 64B = 8×8 网格
    缩略盘格心(触屏) = (7+22.5*(c+.5), 7+22.5*(r+.5))  ← 本轮拟合，屏幕白格 45/45 吻合
  行优先，0=斜线提示格/黑格，1..9=该白格正解。

交互（用户明确：这个游戏只能「先点格子后选数字」，不再尝试分组/按键切换）：
  点下屏缩略盘白格 → 选中；点右侧数字键盘 1-9 → 填入；填满自动 CLEAR。
  数字键盘格心(触屏) = (203+19.5*((n-1)%3), 65+23.5*((n-1)//3))，两档一致。

每关流程：选关层点关号 → A 进入 → 就绪自检(自动跳过ルール教学/START演出) →
  ffmpeg 录制 → 逐格填数 → 等 CLEAR → 停录 → A 存档回选关 → 下一关。
每关独立 try/except，失败记录并继续，末尾汇总。

用法：python3.11 record_all.py [起始关=2] [结束关=20]
"""
import os
import sys
import json
import time
import subprocess

sys.path.insert(0, '/tmp')
import ds
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, 'validation', 'vol4_all.json')
OUTDIR = '/workspace/Vol.4_入門录播'
MONITOR = 'auto_null.monitor'
PULSE_SERVER = 'unix:/tmp/runtime-root/pulse/native'

# 选关按钮（触屏坐标）：第一行 1-10 / 第二行 11-20
SELC_COLS = [26, 50, 75, 100, 124, 149, 173, 198, 222, 247]
SELC_ROWY = {0: 75, 1: 99}

# ffmpeg 启动等待 / 开头留白 / 点击间隔 / 结算停留
# 旧版 ds.click_touch 每次固定 0.2(mousemove后)+0.18(按住)+wait≈0.66s，
# 每格两次点击 ≈1.34s，30 格光填数就 40s。用户问「剂量还能更快吗」→
# 改 fast_tap()：单条 xdotool 命令完成 移动→短按(0.06s)→抬起，间隔 TAP_GAP。
# 实测极限（011 实机 30 格，2026-11-07，能自动 CLEAR 即证明全命中）：
#   gap=0.08 每格 0.370s / 11.1s 全命中；gap=0.05 每格 0.305s / 9.1s 全命中；
#   gap=0.04 每格 0.204s、gap=0.02 每格 0.144s 均漏填不 CLEAR（触摸被吞）。
# ★ 但 6×6 档对 0.05 更敏感（002 实测漏 3 格、补点后仍触发整盘重填，
#   反而比 0.08 慢——多等一轮 14s + 重填）。故【两档统一取 0.08】为稳定值：
#   8×8 实测 30/30、6×6 实测 16/16 且填完 4.7s 自动 CLEAR。
# 入场演出由 LEAD_IN=1.2s 挡住（早期 0.15/0.18 漏点的真因是留白太短，不是点击太快）。
FFMPEG_WARM = 0.6
LEAD_IN = 1.2
TAP_CELL = 0.28          # 选关/箭头等非填数点击沿用 ds.click_touch
TAP_NUM = 0.30
TAP_GAP = 0.08           # ★ 填数点击间隔（fast_tap），双档验证的稳定值
RESULT_HOLD = 5.0        # ★ 结算页出现后再录 5s，覆盖星星点亮 + 分数滚动 + 定格
CLEAR_WAIT = 3.5
FILL_ROUNDS = 4          # 最多补点轮数

with open(DATA, encoding='utf-8') as fp:
    REPORT = json.load(fp)


_GEOM = None


def fast_tap(tx, ty, gap=TAP_GAP):
    """填数专用快速点击：单条 xdotool 完成 移动 → 短按 → 抬起。

    ds.click_touch 每次固定 sleep(0.2)+sleep(0.18)+wait ≈ 0.66s；
    这里把指针移动后的等待压到 0.04s、按住压到 0.06s（≈3~4 帧，足够
    DeSmuME 采样触摸），点击后只再等 gap。实测 gap=0.08 时每格 0.370s、
    30 格(8×8)/16 格(6×6) 全部命中并自动 CLEAR；gap<=0.04 会漏填。
    窗口几何固定，只取一次。
    """
    global _GEOM
    if _GEOM is None:
        _GEOM = ds.geom()
    g = _GEOM
    sx = g['x'] + int(tx * g['w'] / 256)
    sy = g['y'] + g['h'] // 2 + int(ty * (g['h'] // 2) / 192)
    subprocess.run(['xdotool', 'mousemove', str(sx), str(sy), 'sleep', '0.04',
                    'mousedown', '1', 'sleep', '0.06', 'mouseup', '1'],
                   env=ds.ENV)
    time.sleep(gap)


def grid_of(level):
    """0-based level → (n, disk, cell_xy)。n=6 或 8。"""
    body = bytes.fromhex(REPORT['levels'][level]['body_hex'])
    head = REPORT['levels'][level]['header_u32']
    if head[2] == 3:            # 6×6 档
        n = 6
        disk = body[-36:]
        def cell_xy(r, c):
            return int(13 + 25 * (c + .5)), int(20 + 25.5 * (r + .5))
    else:                       # 8×8 档 (head[2]==4 等)
        n = 8
        disk = body[-64:]
        # ★ 用户线索「滚动屏幕靠按下屏的黄色箭头」→ 8×8 档是 7×7 滚动视口。
        # 实机（入門011）标定：
        #   * 上屏是完整 8×8 全盘，红框标出下屏当前 7×7 视口位置；
        #     上屏全局格心 = (64+24*(c+.5), 24*(r+.5))，可用于逐格视觉核对。
        #   * 下屏视口格宽 24px；视口 (dr,dc) 显示全局 r=dr..dr+6, c=dc..dc+6，
        #     屏幕格 (vr,vc) ↔ 全局 (r,c)=(dr+vr, dc+vc)；四边橙黄箭头 ◀▶▲▼
        #     每点一次滚动 1 格，到边界后无效。
        #   * 屏幕格心（触屏）= (8+24*(vc+.5), 10+24*(vr+.5))。
        #   * ROM 答案盘 body[-64:] 经斜线提示段和验证完全正确（011: 7=2+1+4、
        #     10=4+1+3+2、6=2+1+3、6=3+2+1 …）。
        #   * 入門011~020 全部答案格都落在 r1..7 × c1..7，因此滚到 (1,1) 一个
        #     视口即可看全，映射 (r,c)→(vr,vc)=(r-1,c-1)，见 fill_8x8()。
        def cell_xy(r, c):          # 全局格 → 视口(0,0) 时的屏幕格心（仅作占位）
            return int(8 + 24 * (c + .5)), int(10 + 24 * (r + .5))
    return n, disk, cell_xy


def num_xy(v):
    return int(203 + 19.5 * ((v - 1) % 3)), int(65 + 23.5 * ((v - 1) // 3))


def sel_xy(k):
    """1-based 入門关号 k → 选关按钮触屏坐标。"""
    idx = k - 1
    row = 0 if idx < 10 else 1
    col = idx if idx < 10 else idx - 10
    return SELC_COLS[col], SELC_ROWY[row]


def classify(im, x, y):
    """全图(256×384)坐标读 5×5 均值：1=白格/答案格, 0=斜线提示格, -1=模糊。"""
    px = [im.getpixel((x + dx, y + dy)) for dx in range(-2, 3) for dy in range(-2, 3)]
    R = sum(p[0] for p in px) // len(px)
    G = sum(p[1] for p in px) // len(px)
    B = sum(p[2] for p in px) // len(px)
    s = R + G + B
    if s > 540:
        return 1
    if R > 200 and 110 < G < 220 and B < 190:   # 橙色选中格（白格被高亮）
        return 1
    if s < 360:
        return 0
    return -1


def board_match(im, n, disk):
    """读屏分类下屏缩略盘，与答案盘非零位置对照。返回 (吻合, 可判定, 白格数)。"""
    if n == 6:
        x0, y0, cw, ch = 13, 212, 25, 25.5        # 全图坐标(下屏起点 y=192)
    else:
        # ★ 改采【上屏完整 8×8 全盘】：格宽 24px、起点 (64,0)，
        #   上屏全盘格心 = (64+24*(c+.5), 24*(r+.5))，与视口滚动无关。
        #   实测 011/016 白格模式 64/64 完全吻合。
        #   旧的下屏「8×8 / 22.5px」与真实 7×7 视口系统性错位，吻合率随
        #   白格模式波动（015 仅 23/43、017 32/45），导致 ensure_board
        #   误判「盘面未就绪」而整关失败。
        x0, y0, cw, ch = 64, 0, 24, 24
    ok = judged = white = 0
    for r in range(n):
        for c in range(n):
            x = int(x0 + cw * (c + .5))
            y = int(y0 + ch * (r + .5))
            v = classify(im, x, y)
            if v < 0:
                continue
            judged += 1
            if v == 1:
                white += 1
            ans = 1 if disk[r * n + c] else 0
            if v == ans:
                ok += 1
    return ok, judged, white


def board_ready(im, n, disk):
    ok, judged, white = board_match(im, n, disk)
    # 可判定格足够多、吻合率高、且确有白格 → 判定为可玩盘面
    return judged >= n * n * 0.6 and white >= n and ok / max(1, judged) >= 0.82


def retry_board(tag):
    """盤面残留「解答中」数据时：START→オプション→リトライ→はい → 复位成空白盘面。

    实测坐标（触屏）：オプション内「リトライ」(203,21)、确认框「Ⓐはい」用 A 键。
    """
    ds.key('Return', wait=0.9)         # START → オプション
    ds.click_touch(203, 21, wait=0.9)  # リトライ
    ds.key('x', wait=1.2)              # Ⓐはい（最初からプレイしますか）
    time.sleep(1.8)                    # 等复位 + START 演出


def ensure_board(n, disk, cell_xy, tag):
    """进关后确保到达【空白】可玩盘面：
    - 教学页/START演出 → 按 A 推进；
    - 残留「解答中」半填盘面 → リトライ 复位成空白；
    最多 12 轮。

    注意：8×8 档缩略盘里斜线提示格印着小号和数，且白格/斜线格紧密相邻，
    filled_state() 的 15×15 采样窗会把这些小数字与斜线格背景误报成「已填」，
    空白盘面也稳定报出约半数的 filled，导致无限 リトライ。批量流程每关都是
    从选关层点关号全新进入、盘面必为空白，故 8×8 档不做该反查；6×6 档保留。
    """
    stable = 0
    for attempt in range(36):
        im = ds.shot()
        ok, judged, white = board_match(im, n, disk)
        if board_ready(im, n, disk):
            if _orange_low(im) > 120:
                # START / 入力開始 演出期间触摸会被吞（实测 6×6 档最先点的
                # r1 行 1~2 格、8×8 档更多格因此漏填）。大字会闪烁，
                # 故要求连续 3 次采样都无大字才算稳定，不按 A、只等待。
                stable = 0
                time.sleep(0.35)
                continue
            stable += 1
            if stable < 3:
                time.sleep(0.35)
                continue
            if n == 6:
                # 6×6 档白格宽 25px、与斜线格分隔清晰，读盘反查可靠
                missing, filled = filled_state(n, disk, cell_xy)
                if filled:
                    print('  [%s] 检测到解答中残留 %d 格 → リトライ 复位' %
                          (tag, filled), flush=True)
                    retry_board(tag)
                    stable = 0
                    continue
            print('  [%s] 空白盘面就绪 (attempt=%d, %d/%d 吻合, 白格%d)' %
                  (tag, attempt, ok, judged, white), flush=True)
            return True
        stable = 0
        ds.key('x', wait=0.5)          # A：翻ルール教学页 / 确认
        time.sleep(0.35)
    im = ds.shot()
    ds.save(im, '/tmp/v4_fail_board_%s.png' % tag)
    print('  [%s] !! 盘面就绪失败 (最后 %d/%d 吻合, 白格%d)' %
          (tag, *board_match(im, n, disk)), flush=True)
    return False


def _pen(im, x, y):
    """(x,y) 附近 11×13 区内深蓝数字笔画像素数。"""
    return sum(1 for dy in range(-6, 7) for dx in range(-5, 6)
               if (lambda R, G, B: R < 120 and G < 140 and B < 190 and B >= R)(
                   *im.getpixel((x + dx, y + dy))))


def _blue_top(im):
    """上屏深蓝背景像素占比。选关层约 0.55；オプション/盘面/结算页 < 0.07。"""
    cnt = tot = 0
    for y in range(0, 192, 3):
        for x in range(0, 256, 3):
            r, g, b = im.getpixel((x, y))
            tot += 1
            if r < 110 and b > 90 and b > r + 35:
                cnt += 1
    return cnt / tot


def _blue_bottom(im):
    """下屏深蓝占比：通关结算页 / 选关层 ≈0.65，答题盘面 ≈0.05。"""
    cnt = tot = 0
    for y in range(192, 384, 3):
        for x in range(0, 256, 3):
            r, g, b = im.getpixel((x, y))
            tot += 1
            if r < 110 and b > 90 and b > r + 35:
                cnt += 1
    return cnt / tot


def in_result_screen():
    """是否已进入蓝色通关结算页（クリアタイム + 星数）。
    实测：结算页 0.68、选关层 0.64、盘面 0.02~0.11，阈值 0.4 区分干净。
    """
    return _blue_bottom(ds.shot()) > 0.4


def _orange_low(im):
    """下屏中央 START / CLEAR 橙色大字像素数：演出中 300~760，正常盘面 <30。"""
    c = 0
    for y in range(230, 330, 2):
        for x in range(10, 195, 2):
            r, g, b = im.getpixel((x, y))
            if r > 170 and 70 < g < 205 and b < 140:
                c += 1
    return c


def _sel_red(im):
    """下屏关号按钮行(y≈255..305)的红色像素数。

    已通关关号按钮会整片变红，通关数越多红色像素越多（013 通关后实测 864）；
    答题盘面 / 结算页 / 空白盘面均 ≤7。这是选关层对任意通关数都成立的特征。
    """
    cnt = 0
    for y in range(255, 306, 2):
        for x in range(10, 250, 2):
            r, g, b = im.getpixel((x, y))
            if r > 170 and g < 130 and b < 130:
                cnt += 1
    return cnt


def on_select_screen():
    """判定选关层：上屏深蓝背景 + 1-20 关号按钮行。

    实测区分度（60+ 张各界面截图统计）：
      * 选关层：blue_top≈0.54~0.57、blue_bottom≈0.63；
      * オプション菜单：blue_top≈0.05（上屏白底 KAKURO logo）；
      * 结算/演出/答题盘面：blue_top≈0.04~0.06。

    深蓝数字笔画判据（20 个按钮 ≥18 落在 [20,90]）只适用于「几乎没通关」时：
    已通关关号按钮变红后测不到深蓝笔画，013 通关后 1~13 全红，inrange 掉到 17
    仍不满足 ≥18，导致 ensure_select 误判、按 A 反而误进关、014~017 连锁失败。
    故新增第二条通路：双深蓝 + 按钮行红色成片 → 同样是选关层。
    """
    im = ds.shot()
    if _blue_top(im) < 0.45:
        return False
    vals = [_pen(im, x, y) for y in (264, 292) for x in SELC_COLS]
    if (sum(1 for v in vals if 20 <= v <= 90) >= 18
            and sum(1 for v in vals if v > 100) <= 1):
        return True
    return _blue_bottom(im) > 0.4 and _sel_red(im) > 100


def is_cleared():
    """CLEAR/结算判定：上屏出现成片橙色 CLEAR 大字或结算演出的亮色块。

    未通关的可玩盘面上屏橙像素极少（选中格只有细橙框）。
    """
    im = ds.shot()
    orange = 0
    for y in range(0, 192, 2):
        for x in range(0, 256, 2):
            R, G, B = im.getpixel((x, y))
            if R > 205 and 90 < G < 190 and B < 130:
                orange += 1
    return orange > 400


def filled_state(n, disk, cell_xy):
    """读盘：返回 (未填答案格列表, 已填数)。用深蓝数字笔画像素判定该格是否已填数字。"""
    im = ds.shot()
    missing = []
    filled = 0
    for r in range(n):
        for c in range(n):
            v = disk[r * n + c]
            if not v:
                continue
            tx, ty = cell_xy(r, c)
            x, y = tx, 192 + ty          # 触屏 → 全图
            pen = 0
            for dy in range(-7, 8):
                for dx in range(-7, 8):
                    R, G, B = im.getpixel((x + dx, y + dy))
                    if R < 120 and G < 140 and B < 190 and B >= R:
                        pen += 1
            if pen < 8:
                missing.append((r, c, v))
            else:
                filled += 1
    return missing, filled


def ensure_select(tag):
    """确保在选关层。绝不在盘面盲目按 A（会误填数字）。

    通关后：结算页按 A → セーブ中 → 自动回选关，等待即可。
    残留盘面：START→オプション→問題選択へ→はい 直接复位回选关。
    """
    for attempt in range(8):
        if on_select_screen():
            return True
        if attempt < 3:
            # 可能是 CLEAR 结算 / セーブ中过渡：按 A 存档并等待
            ds.key('x', wait=1.0)
            time.sleep(1.8)
        else:
            # 仍不在选关层（多半是残留盘面）：走 問題選択へ 复位
            ds.key('Return', wait=0.9)             # START → オプション
            ds.click_touch(207, 45, wait=0.9)      # 問題選択へ
            ds.click_touch(62, 131, wait=0.9)      # Ⓐはい
            time.sleep(1.6)
    ds.save(ds.shot(), '/tmp/v4_fail_select_%s.png' % tag)
    print('  [%s] !! 未回到选关层' % tag, flush=True)
    return False


def ffmpeg_proc(path):
    g = ds.geom()
    cmd = [
        'ffmpeg', '-y', '-loglevel', 'error',
        '-thread_queue_size', '512',
        '-f', 'x11grab', '-video_size', '%dx%d' % (g['w'], g['h']),
        '-framerate', '30', '-draw_mouse', '0',
        '-i', ':99+%d,%d' % (g['x'], g['y']),
        '-thread_queue_size', '512',
        '-f', 'pulse', '-i', MONITOR,
        '-af', 'alimiter=limit=0.9:asc=1',
        '-c:v', 'libopenh264', '-b:v', '1200k', '-r', '30',
        '-c:a', 'aac', '-b:a', '128k',
        '-fflags', '+genpts',
        path,
    ]
    env = dict(os.environ, DISPLAY=':99', PULSE_SERVER=PULSE_SERVER)
    return subprocess.Popen(cmd, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def answer_cells(n, disk):
    return [(r, c, disk[r * n + c])
            for r in range(n) for c in range(n) if disk[r * n + c]]


# ---- 8×8 档：7×7 视口 + 四边橙黄箭头滚动（用户 2026-11-06 线索） ----
# 箭头触屏坐标（全图=触屏 x, 全图 y-192=触屏 y）：
#   ▶(174,90) ◀(10,90) ▼(90,174) ▲(90,10)
V8_ARROW = {'R': (174, 90), 'L': (10, 90), 'D': (90, 174), 'U': (90, 10)}
V8_X0, V8_Y0, V8_CW = 8, 10, 24      # 屏幕格心(触屏) = (X0+CW*(vc+.5), Y0+CW*(vr+.5))


def _v8_arrow_px(im, name):
    """四边箭头区域的橙黄像素数：存在 ~20，不存在 0。用于闭环校验视口状态。"""
    a = __import__('numpy').array(im.convert('RGB'))
    box = {'R': (165, 185, 265, 300), 'L': (0, 20, 265, 300),
           'D': (75, 105, 355, 378), 'U': (75, 105, 192, 215)}[name]
    x0, x1, y0, y1 = box
    seg = a[y0:y1, x0:x1]
    r, g, b = seg[:, :, 0], seg[:, :, 1], seg[:, :, 2]
    return int(((r > 205) & (g > 110) & (g < 215) & (b < 120)).sum())


def _v8_state(im):
    """读箭头判视口 (dr,dc)：R/D 在 → dc=0/dr=0；L/U 在 → dc=1/dr=1。"""
    return (1 if _v8_arrow_px(im, 'U') > 8 else 0,
            1 if _v8_arrow_px(im, 'L') > 8 else 0)


def _v8_scroll(target, tag):
    """把视口滚到 (dr,dc)=target，用箭头闭环推进，最多 6 步。返回是否到达。"""
    for _ in range(6):
        im = ds.shot()
        cur = _v8_state(im)
        if cur == target:
            return True
        dr, dc = cur
        tdr, tdc = target
        # 先纵向再横向；点箭头后要求对应反向箭头出现，否则重试
        if dr != tdr:
            name = 'D' if tdr > dr else 'U'
            ds.click_touch(*V8_ARROW[name], wait=0.7)
        elif dc != tdc:
            name = 'R' if tdc > dc else 'L'
            ds.click_touch(*V8_ARROW[name], wait=0.7)
    ok = _v8_state(ds.shot()) == target
    if not ok:
        print('  [%s] !! 视口滚动未到 %s' % (tag, target), flush=True)
    return ok


def _v8_view_missing(items):
    """读当前视口，返回 items=[(vr,vc,v)...] 中【未填】的格（只检查传入的归属格）。"""
    import numpy as np
    a = np.array(ds.shot().convert('RGB'))
    missing = []
    for vr, vc, v in items:
        x = int(V8_X0 + V8_CW * (vc + .5))
        y = 192 + int(V8_Y0 + V8_CW * (vr + .5))     # 触屏 → 全图
        s = a[y - 7:y + 8, x - 7:x + 8]
        R, G, B = s[:, :, 0], s[:, :, 1], s[:, :, 2]
        pen = int(((R < 120) & (G < 140) & (B < 190) & (B >= R)).sum())
        if pen < 8:
            missing.append((vr, vc, v))
    return missing


def fill_8x8(disk, tag):
    """8×8 档：把视口滚到右下 (1,1)，【单视口一次填完】所有答案格。

    ★ 决定性结论（实机逐格验证，入門011 30 格 100% 核对通过）：
      * 入門011~020 全部答案格都落在全局 r1..7 × c1..7 的 7×7 区域内
        （r0 / c0 全是斜线提示格）。因此【一个 (1,1) 视口即可看全 30~36 格】，
        根本不需要在 4 个视口间来回滚动。
      * 旧版「4 视口分配 + 滚动状态机」在反复滚动中把数字填到错格，
        且 _v8_view_missing 的 pen<8 判据会把斜线提示格误判成已填，
        于是「空格 0」是假象、盘面实际有错值 → 永不 CLEAR。
      * 全局格 (r,c) → 屏幕格 (vr,vc)=(r-1,c-1)，
        格心(触屏) = (V8_X0+V8_CW*(vc+.5), V8_Y0+V8_CW*(vr+.5))。
        上屏全盘格心 = (64+24*(c+.5), 24*(r+.5))，可用于逐格视觉核对。
      * ROM 答案盘 body[-64:] 经斜线提示段和验证完全正确
        (011: 7=2+1+4, 10=4+1+3+2, 6=2+1+3, 6=3+2+1, ...)。
      * 30 格全部填对后游戏会【延迟数秒自动 CLEAR】，按 A 只推进结算演出，
        不需要 CHECK / 決定 之类的额外提交动作。
    """
    cells = answer_cells(8, disk)
    if not _v8_scroll((1, 1), tag):
        return False
    print('  [%s] 视口(1,1) 就绪，单视口一次填 %d 格' % (tag, len(cells)), flush=True)
    for r, c, v in cells:
        vr, vc = r - 1, c - 1
        tx = int(V8_X0 + V8_CW * (vc + .5))
        ty = int(V8_Y0 + V8_CW * (vr + .5))
        nx, ny = num_xy(v)
        fast_tap(tx, ty)
        fast_tap(nx, ny)
    return True


def record_one(k):
    """录 1-based 入門关号 k。返回 (ok, 说明)。"""
    level = k - 1
    n, disk, cell_xy = grid_of(level)
    cells = answer_cells(n, disk)
    tag = '%03d' % k
    out = os.path.join(OUTDIR, 'Vol.4_数和_入門%s_256x384.mp4' % tag)
    print('\n=== 入門%s (lv%d, %d×%d, %d 格) ===' % (tag, level, n, n, len(cells)), flush=True)

    # 1) 选关层点关号 → A 进入
    #    ★ 通关后回选关层时存档/解锁演出可能残留，单次点关号偶发被吞 →
    #      按 A 就进了【当前光标所在的前一关】（2026-11-07 批量 004/006/008
    #      实测都进成第 3/5/7 問，即上一关；017 也曾进成 015）。
    #      故：进关前多等 0.5s、点关号连点 2 次（同一按钮幂等，只移光标
    #      不进关）、并对「盘面不符」做进关重试（回选关层重新进）。
    board_ok = False
    for enter_try in range(3):
        if not ensure_select(tag):
            return False, '未处于选关层'
        time.sleep(0.5)                     # 存档/解锁演出余波
        sx, sy = sel_xy(k)
        ds.click_touch(sx, sy, wait=0.5)
        ds.click_touch(sx, sy, wait=0.8)   # 连点 2 次，防单次被吞
        ds.key('x', wait=1.0)              # A 进入（教学/START 由 ensure_board 处理）
        time.sleep(1.6)
        if ensure_board(n, disk, cell_xy, tag):
            board_ok = True
            break
        print('  [%s] 第%d次进关盘面不符 → 回选关层重试' %
              (tag, enter_try + 1), flush=True)
    if not board_ok:
        return False, '盘面未就绪(多次进关重试仍失败)'

    # 3) 录制：填数 → 等结算页 →（必要时）再重填一轮 → A 決定 → 等结算页
    #
    # 6×6 档：整盘按序填（同格同数字重填覆盖，不会改错），填满自动 CLEAR。
    # 8×8 档：把 7×7 视口滚到 (1,1) 看全所有答案格，单视口一次填完，
    #         见 fill_8x8()。旧版在 4 个视口间来回滚动会填错格，已废弃。
    p = ffmpeg_proc(out)
    time.sleep(FFMPEG_WARM)
    time.sleep(LEAD_IN)
    # 8×8 单视口一次填完；正常第 1 轮即结算，第 2 轮仅在未结算时兜底重填
    # （同格同值覆盖，不会改错；此时视口仍在 (1,1)，_v8_scroll 会立即返回）
    for rnd in range(2):
        if n == 8:
            fill_8x8(disk, tag)
            what = '8×8 单视口(1,1)一次填数'
        else:
            for r, c, v in cells:
                x, y = cell_xy(r, c)
                nx, ny = num_xy(v)
                fast_tap(x, y)
                fast_tap(nx, ny)
            what = '整盘按序填数'
            # ★ 6×6 精确补点：快速点击偶发漏格时只补空格（filled_state 在
            #   6×6 白格宽 25px 分隔清晰、判据可靠，实测 16/16 无误报），
            #   比整盘重填 16 格更快，且视频里不会出现「整盘重填一遍」。
            missing, filled = filled_state(n, disk, cell_xy)
            if missing:
                print('  [%s] 第%d轮读盘空格 %d → 精确补点 %s' %
                      (tag, rnd + 1, len(missing), missing), flush=True)
                for r, c, v in missing:
                    x, y = cell_xy(r, c)
                    nx, ny = num_xy(v)
                    fast_tap(x, y)
                    fast_tap(nx, ny)
        print('  [%s] 第%d轮%s完成 (%d 格)' % (tag, rnd + 1, what, len(cells)), flush=True)
        # ★ 两档统一 14s 等待窗口：填满正确答案后游戏【延迟数秒才自动 CLEAR】。
        #   实机时间线（填完起算）：2.1s CLEAR 大字 → 4.2s 转场 → 4.7s 结算页
        #   （8×8 约 4.5s）。旧版 6×6 只等 12×0.5=6s 且每轮叠加抓屏开销，
        #   正好卡在边界偶发超时，误触发整盘重填第 2 轮。等待期间不按 A。
        for _ in range(28):
            if in_result_screen():
                break
            time.sleep(0.5)
        if in_result_screen():
            print('  [%s] 第%d轮后进入结算页' % (tag, rnd + 1), flush=True)
            break
        print('  [%s] 第%d轮后仍未结算 → 重填一轮' % (tag, rnd + 1), flush=True)
    if not in_result_screen():
        ds.key('x', wait=0.8)         # A：決定 / 结算推进（8×8 大棋盘尤其需要）
    cleared = False
    for _ in range(20):               # 最多再等 10s 让结算页出现
        if in_result_screen():
            cleared = True
            break
        time.sleep(0.5)
    # ★ 结算演出完整收录（用户 2026-11-07 反馈「星星结算没录完」）：
    # 实机时间线（填完最后一格起算，8×8 011）：
    #   0~1.4s 盘面 → 1.6~3.9s CLEAR 橙色大字演出 → 4.1s 暗场转场
    #   → 4.5s 蓝色结算页渐显（in_result_screen 此刻就返回 True）
    #   → 【4 星制，第 3/4 颗延迟点亮】：结算页刚出现只有 2~3 颗金 +
    #     1~2 颗灰，约 2~3s 后第 4 颗才变金，约 7s 起 4 星全金定格。
    # 旧版只 sleep(1.5) 就 terminate，恰好切在第 4 颗星还是灰色时。改为
    # 结算页出现后再录 RESULT_HOLD=5s，覆盖「2/4 → 4/4」点亮全过程 + 定格。
    time.sleep(RESULT_HOLD)
    ds.save(ds.shot(), '/tmp/v4_end_%s.png' % tag)     # 结算证据截图
    if not cleared:
        print('  [%s] !! 未进入结算页（答案可能有误）' % tag, flush=True)
    p.terminate()
    try:
        err = p.communicate(timeout=8)[1]
        if err:
            print('  [%s] ffmpeg stderr: %s' % (tag, err.decode('utf-8', 'ignore')[:300]), flush=True)
    except subprocess.TimeoutExpired:
        p.kill()

    if not os.path.exists(out) or os.path.getsize(out) < 5000:
        return False, '视频未生成/过小'

    # 4) 存档回选关（录制外，不入库）
    #    结算 → セーブ中 → 回选关 全部交给 ensure_select 内部按 A 推进，
    #    避免此处显式按 A 后再由 ensure_select 按一次（重复 A 会在选关层误进关）。
    time.sleep(0.6)
    ok_flow = ensure_select(tag)
    if not cleared:
        return False, '未进入结算页(视频仅作诊断, 已复位)'
    if not ok_flow:
        return False, '通关后未回选关层(视频已生成)'

    kb = os.path.getsize(out) // 1024
    return True, '%d KB, %d 格, %d×%d' % (kb, len(cells), n, n)


def main():
    lo = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    hi = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    os.makedirs(OUTDIR, exist_ok=True)
    results = []
    for k in range(lo, hi + 1):
        try:
            ok, msg = record_one(k)
        except Exception as e:            # 单关失败不影响后续
            ok, msg = False, 'EXC %s: %s' % (type(e).__name__, e)
        print('  => %s  %s' % ('OK' if ok else 'FAIL', msg), flush=True)
        results.append((k, ok, msg))
    print('\n=== 汇总 ===', flush=True)
    for k, ok, msg in results:
        print('  入門%03d  %-4s  %s' % (k, 'OK' if ok else 'FAIL', msg), flush=True)
    print('  成功 %d / %d' % (sum(1 for _, o, _ in results if o), len(results)), flush=True)


if __name__ == '__main__':
    main()
