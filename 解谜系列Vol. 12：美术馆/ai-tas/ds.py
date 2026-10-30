#!/usr/bin/env python3
"""Vol.11 DeSmuME 操作公用层。

铁律（踩过的坑）：
  1. 窗口必须 windowmove 到 (384,192)，截图 crop 才能对齐。
  2. 按键必须 windowfocus + XTEST(keydown/keyup)，绝不能用 xdotool key --window
     （XSendEvent 会被 SDL 丢弃，表现为「输入死亡」）。
  3. 首次按键常被吞，关键操作后要截图确认。
"""
import os
import signal
import subprocess
import time

from PIL import Image

DISP = ":99"
BASE = "/root/.codebuddy/artifact/vol12"
# ★ 2026-10-28 存档隔离：必须用 vol12.nds（按文件名存 ~/.config/desmume/vol12.dsv），
#   不能叫 game.nds——会和 Vol.11 共用 game.dsv（Vol.11 最终档在 game.dsv.bak_vol11_final）。
ROM = os.path.join(BASE, "vol12.nds")
WIN_X, WIN_Y = 384, 192
WIN_W, WIN_H = 256, 384

ENV = dict(os.environ, DISPLAY=DISP)


def win():
    # ★ 2026-10-28 修：窗口名实测为「Desmume 571.428589」（大写D），xdotool --name 是
    #   POSIX 正则（不支持 (?i) 前缀，会编译失败），用 [Dd] 前缀大小写通吃。
    out = subprocess.run(["xdotool", "search", "--name", "[Dd]esmume"],
                         env=ENV, capture_output=True, text=True).stdout.split()
    return out[0] if out else None


def ensure_window():
    """确保窗口存在、位置正确、有焦点。返回 winid 或 None。"""
    w = win()
    if not w:
        return None
    subprocess.run(["xdotool", "windowmove", w, str(WIN_X), str(WIN_Y)], env=ENV)
    subprocess.run(["xdotool", "windowfocus", w], env=ENV)
    return w


def start():
    """启动 DeSmuME（若未运行）。"""
    if win():
        ensure_window()
        return win()
    log = open("/tmp/desmume.log", "w")
    subprocess.Popen(["desmume-cli", "--cpu-mode=0", "--disable-sound",
                      "--num-cores=1", os.path.basename(ROM)],
                     cwd=BASE, env=ENV, stdout=log, stderr=log,
                     start_new_session=True)
    for _ in range(40):
        time.sleep(0.5)
        if ensure_window():
            time.sleep(3)
            return win()
    raise RuntimeError("DeSmuME 启动失败")


def kill():
    subprocess.run(["pkill", "-x", "desmume-cli"])
    time.sleep(1.2)


def grab(name="tmp"):
    """截 NDS 双屏画面（256x384），返回 PIL Image（真彩 RGB）。

    ★2026-10-30 改用 ffmpeg x11grab 直抓窗口区：ImageMagick 的 import 在
      当前 Xvfb 环境下抓出来是灰度(PseudoColor)图 → 所有 RGB 判据失效
      （detect_level / in_play_page 全程 m=0、盘面不可信）。ffmpeg 抓到的
      是真彩 RGB；且与录制阶段的 ffmpeg x11grab 各写各的文件、互不写坏，
      并发比 import+xwd 更稳。加 3 次重试 + 间隔兜底偶发抓取失败。
    """
    ensure_window()
    raw = os.path.join(BASE, "_raw.png")
    last = None
    for _ in range(3):
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-loglevel", "error", "-f", "x11grab",
                 "-video_size", f"{WIN_W}x{WIN_H}", "-i", f"{DISP}.0+{WIN_X},{WIN_Y}",
                 "-frames:v", "1", raw],
                env=ENV, check=True,
            )
            im = Image.open(raw).convert("RGB")
            if im.size != (WIN_W, WIN_H):
                raise ValueError(f"grab size {im.size}")
            if name:
                im.save(os.path.join(BASE, f"{name}.png"))
            return im
        except Exception as e:
            last = e
            time.sleep(0.35)
    raise RuntimeError(f"grab 失败（3 次重试）: {last}")


def press(key, wait=0.55, hold=0.14):
    """发一次按键。keydown/keyup 分离，确保 SDL 能收到。"""
    w = ensure_window()
    subprocess.run(["xdotool", "keydown", key], env=ENV)
    time.sleep(hold)
    subprocess.run(["xdotool", "keyup", key], env=ENV)
    time.sleep(wait)


def press_n(key, n, wait=0.4):
    for _ in range(n):
        press(key, wait)


def diff(a, b):
    """两张 PIL Image 的 L1 差异。"""
    import numpy as np
    x = np.asarray(a.convert("L")).astype(int)
    y = np.asarray(b.convert("L")).astype(int)
    return int(abs(x - y).sum())


# ---- 视口盘面几何（下屏局部坐标，已标定） ----
GRID_X0, GRID_Y0 = 24, 216
PITCH = 16
VIS_COLS, VIS_ROWS = 10, 9

C_WHITE = (246, 246, 246)
C_WALL = (159, 159, 159)
C_CURSOR = (24, 24, 24)


def cell_center(r, c):
    """视口第 (r,c) 格中心（下屏局部像素坐标）。"""
    return GRID_X0 + PITCH * c, GRID_Y0 + PITCH * r


def scan_cursor(im):
    """返回光标所在格 (r,c) 列表。"""
    px = im.convert("RGB").load()
    hits = []
    for r in range(VIS_ROWS + 1):
        for c in range(VIS_COLS + 2):
            x, y = cell_center(r, c)
            if x >= WIN_W or y >= WIN_H:
                continue
            if px[x, y] == C_CURSOR:
                hits.append((r, c))
    return hits


def scan_board(im):
    """返回 {(r,c): 'W'|'B'|'T'|'.'} —— 白/黑墙/仮置き/其它。"""
    px = im.convert("RGB").load()
    out = {}
    for r in range(VIS_ROWS):
        for c in range(VIS_COLS):
            x, y = cell_center(r, c)
            v = px[x, y]
            if v[0] >= 235:
                out[(r, c)] = "W"
            elif 145 <= v[0] <= 175:
                out[(r, c)] = "B"
            elif v[0] < 120:
                out[(r, c)] = "T"
            else:
                out[(r, c)] = "."
    return out


def show_board(im):
    b = scan_board(im)
    for r in range(VIS_ROWS):
        print("".join(b[(r, c)] for c in range(VIS_COLS)))


if __name__ == "__main__":
    import sys
    w = start()
    print("winid", w)
    if len(sys.argv) > 1:
        im = grab(sys.argv[1])
        print("size", im.size)
        print("cursor", scan_cursor(im))
        show_board(im)


def find_cursor(im):
    """检测橙色四角光标框，返回 (r,c) 或 None。

    光标框画在格子四条边附近（格线内侧 1-3px），颜色约 (255,140,0)。
    """
    import numpy as np
    a = np.asarray(im.convert("RGB")).astype(int)
    R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    mask = (R > 200) & (G > 90) & (G < 200) & (B < 100)
    best, bestv = None, 0
    for r in range(11):
        for c in range(12):
            x0, y0 = 16 + 16 * c, 208 + 16 * r
            if x0 + 16 > 192 or y0 + 16 > 384:
                continue
            # 四条边带
            band = mask[y0:y0 + 17, x0:x0 + 17]
            # 只统计距边 4px 内的像素
            edge = np.zeros_like(band)
            edge[0:4, :] = True
            edge[-4:, :] = True
            edge[:, 0:4] = True
            edge[:, -4:] = True
            v = int((band & edge).sum())
            if v > bestv:
                bestv, best = v, (r, c)
    return best if bestv >= 8 else None, bestv


def cursor_box(im):
    """返回光标框 (x0,y0,x1,y1,cx,cy) 或 None。限定盘面区，按格统计边框命中。"""
    import numpy as np
    a = np.asarray(im.convert("RGB")).astype(int)
    R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    m = (B == 0) & (R >= 230) & (G >= 40) & (G <= 220)
    m[:208, :] = False
    m[384:, :] = False
    m[:, 192:] = False
    best, bestv = None, 0
    for r in range(11):
        for c in range(10):
            x0, y0 = 16 + 16 * c, 208 + 16 * r
            if x0 < 0 or y0 < 0 or x0 + 18 > 192 or y0 + 18 > 384:
                continue
            reg = m[y0 - 2:y0 + 18, x0 - 2:x0 + 18]
            if reg.shape[0] < 20 or reg.shape[1] < 20:
                continue
            edge = np.zeros_like(reg)
            edge[0:3, :] = True
            edge[-3:, :] = True
            edge[:, 0:3] = True
            edge[:, -3:] = True
            v = int((reg & edge).sum())
            if v > bestv:
                bestv, best = v, (r, c)
    if bestv < 6:
        return None
    r, c = best
    cx, cy = 24 + 16 * c, 216 + 16 * r
    return (cx - 10, cy - 10, cx + 10, cy + 10, cx, cy), (r, c)


def tap(nds_x, nds_y, hold=0.06, after=0.6, gap=0.04):
    """按压式触摸（PITFALLS B1/L 铁律）：mousemove → sleep gap → down → hold → up。

    nds_x/nds_y 为下屏 NDS 相对坐标 (0-255, 0-191)。
    gap 默认 0.04（铁律：mousemove 后须等坐标生效再 down）。
    """
    w = ensure_window()
    sx, sy = WIN_X + nds_x, WIN_Y + 192 + nds_y
    subprocess.run(["xdotool", "mousemove", str(sx), str(sy), "sleep", str(gap),
                    "mousedown", "1", "sleep", str(hold), "mouseup", "1"], env=ENV)
    time.sleep(after)


def tap_local(lx, ly, hold=0.06, after=0.6):
    """按截图局部坐标触摸（lx 0-255, ly 192-383）。

    ★ DeSmuME 把窗口内 y(0-383) 线性映射到触摸屏 y(0-191)，即 y_nds = y_rel/2。
      故要触摸下屏局部 ly，须发窗口内 y_rel = 2*(ly-192)。
    """
    tap(lx, ly - 192, hold, after)


_WIN_CACHE = None


def tap_batch(points, gap=0.04, hold=0.06, after=0.16):
    """单进程批量触摸（Vol.13 单进程提速思路）：一条 xdotool 命令连发多次点击。

    points: [(nds_x, nds_y), ...]
    """
    global _WIN_CACHE
    if not points:
        return
    w = ensure_window()
    args = []
    for (nx, ny) in points:
        sx, sy = WIN_X + nx, WIN_Y + 192 + ny
        args += ["mousemove", str(sx), str(sy), "sleep", str(gap),
                 "mousedown", "1", "sleep", str(hold), "mouseup", "1",
                 "sleep", str(after)]
    subprocess.run(["xdotool"] + args, env=ENV)
