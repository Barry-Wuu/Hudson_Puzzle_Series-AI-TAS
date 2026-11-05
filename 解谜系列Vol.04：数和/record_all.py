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

# ffmpeg 启动等待 / 开头留白 / 点击间隔 / CLEAR 等待
# 实测：0.15/0.18 + 0.4s 留白会漏点（入場演出未结束触摸被吞，2 格漏填不 CLEAR）。
# 回调到与 Vol.10 后作一致的 0.22/0.25，留白 1.2s 等演出走完；并加「读盘补点」兜底。
FFMPEG_WARM = 0.6
LEAD_IN = 1.2
TAP_CELL = 0.28
TAP_NUM = 0.30
CLEAR_WAIT = 3.5
FILL_ROUNDS = 4          # 最多补点轮数

with open(DATA, encoding='utf-8') as fp:
    REPORT = json.load(fp)


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
        # 实机标定（入門011 单格命中实验）：
        #   r1c3 触屏 (85,40) 正确填入；r7c4 用旧公式 (108,175) 却落在盘面外的
        #   底部菜单条上——格子没被选中，数字反而覆盖到上一个仍选中的格，
        #   这正是 8×8 档整盘填数始终不 CLEAR 的根因。
        #   两点拟合：y(r1)=40、y(r7)=166 → 格宽 21、起点 8.5（取整 9）。
        #   上半部分与旧公式差 1~2px，下半部分整体上移 4~10px，全部落回盘面内。
        def cell_xy(r, c):
            return int(9 + 21 * (c + .5)), int(9 + 21 * (r + .5))
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
        x0, y0, cw, ch = 7, 199, 22.5, 22.5
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


def on_select_screen():
    """判定选关层：上屏深蓝背景 + 1-20 关号按钮的深蓝数字笔画。

    实测区分度（60+ 张各界面截图统计）：
      * 选关层：blue≈0.54~0.57，20 值中 19~20 落在 [20,90]，>100 的有 0 个；
        当前光标所在关号会变红/带「クリア済」标记，该按钮笔画值掉到 0~22，
        故不能要求 20/20 全在区间内（旧判据在通关后误判失败的原因）。
      * オプション菜单：blue≈0.05（上屏是白底 KAKURO logo），但按钮位恰有 18 个落在区间；
      * 结算/演出/答题盘面：blue 低或 >100 的极端值成片出现。
    旧版「数白像素 / 数游程」同样会被盘面数字键盘或缩略盘白格误判。
    """
    im = ds.shot()
    if _blue_top(im) < 0.45:
        return False
    vals = [_pen(im, x, y) for y in (264, 292) for x in SELC_COLS]
    return (sum(1 for v in vals if 20 <= v <= 90) >= 18
            and sum(1 for v in vals if v > 100) <= 1)


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


def record_one(k):
    """录 1-based 入門关号 k。返回 (ok, 说明)。"""
    level = k - 1
    n, disk, cell_xy = grid_of(level)
    cells = answer_cells(n, disk)
    tag = '%03d' % k
    out = os.path.join(OUTDIR, 'Vol.4_数和_入門%s_256x384.mp4' % tag)
    print('\n=== 入門%s (lv%d, %d×%d, %d 格) ===' % (tag, level, n, n, len(cells)), flush=True)

    # 1) 选关层点关号 → A 进入
    if not ensure_select(tag):
        return False, '未处于选关层'
    sx, sy = sel_xy(k)
    ds.click_touch(sx, sy, wait=0.8)
    ds.key('x', wait=1.0)              # A 进入（教学/START 由 ensure_board 处理）
    time.sleep(1.6)

    # 2) 就绪自检（含教学跳过 / 解答中残留复位）
    if not ensure_board(n, disk, cell_xy, tag):
        return False, '盘面未就绪(教学/演出未跳过或复位失败)'

    # 3) 录制：整盘按序填 → 等结算页 →（必要时）再整盘重填一轮 → A 決定 → 等结算页
    #
    # 放弃「读盘找漏格再补点」：实测补点点击会因为选中态/演出把数字填到别的格，
    # 反而制造答案错误（004/006/008/009 因此没 CLEAR，002/010 靠首轮填满才通关）。
    # 改为整盘重填一轮（同格同数字覆盖，不会改错），并以下屏深蓝占比判定结算页，
    # 不再依赖 filled_state() 的笔画读数。
    p = ffmpeg_proc(out)
    time.sleep(FFMPEG_WARM)
    time.sleep(LEAD_IN)
    for rnd in range(2):
        for r, c, v in cells:
            x, y = cell_xy(r, c)
            nx, ny = num_xy(v)
            ds.click_touch(x, y, wait=TAP_CELL)
            ds.click_touch(nx, ny, wait=TAP_NUM)
        print('  [%s] 第%d轮整盘填数完成 (%d 格)' % (tag, rnd + 1, len(cells)), flush=True)
        for _ in range(12):           # CLEAR 演出 + 结算页切换可达 4~5s，最多等 6s
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
    time.sleep(1.5)                   # 让结算页在视频里停留，避免末尾被截断
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
