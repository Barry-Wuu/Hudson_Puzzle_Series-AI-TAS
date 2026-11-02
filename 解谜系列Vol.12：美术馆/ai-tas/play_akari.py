#!/usr/bin/env python3
"""Vol.12 美术馆(Akari) 入門批量点灯清关 v2（键盘导航版）。

用法: python3.11 play_akari.py <起始关> <结束关>

流程（2026-10-28 校准定案）:
  选关页光标(绿框)停在刚通关的格 -> Right(单步,hold=0.04) -> x 进下一关
  -> 按 bulbs 点灯 -> 通关(盘面全亮) -> x 回选关页
键位: A=x B=z Start=Return; 方向键 hold=0.14 会一次跳3格(SDL重复), 必须 hold=0.04
坐标: 游戏盘面 X0=24 Y0=216 P=24; 选关格 行1 y=289 行2 y=310, x=18+24*(col-1)
"""
import json
import os
import sys
import time

import numpy as np

import ds

X0, Y0, P = 24, 216, 24
PUZZLES = os.path.join(os.path.dirname(__file__), "..", "validation", "puzzles.json")
STEP = dict(hold=0.04, wait=0.5)      # 单步方向键

# ★ 2026-10-28 剂量重标定（两轮）：
#   turbo(--disable-limiter)：after=0.04 即可（游戏轮询快）。
#   limiter ON（正常60fps）：实测 after<=0.10 时 9 灯全不亮、after>=0.22 才 9/9 全中
#   —— 点灯后有约0.2s点亮动画，期间游戏屏蔽触摸。取 after=0.26 留余量。
BULB_DOSE = dict(gap=0.04, hold=0.10, after=0.26)
# ★2026-10-28 实测重标定：光标环 24x16，行1环心 y≈279.5、行2 y≈295.5（行距16！），
#   列1环心 x≈19.5、列距24。旧 SEL_Y{289,310} 有误（环跨两窗口被重复计数，
#   Q11 导航"失败"实为验证误读），此常量仅留档，检测已改为中位数自适应。
SEL_Y = {1: 280, 2: 296}
RING_Y = (279.5, 295.5)               # 两行环心 y
RING_X0 = 19.5                        # 列1环心 x


def cursor_green(im):
    """选关页光标格：亮绿环(0,255,65) 24x16。★2026-10-28 重写：
    对全部 mg 像素取中位数 (cx,cy) 定位环心，再就近匹配行列——
    不依赖固定窗口，页面布局漂移免疫；稀疏噪点被中位数天然滤除。"""
    a = np.asarray(im.convert("RGB")).astype(int)
    R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    mg = (G > 225) & (R < 25) & (B < 110)          # 亮绿环
    ys, xs = np.nonzero(mg)
    if len(ys) < 20:
        return None
    cy = float(np.median(ys))
    cx = float(np.median(xs))
    row = 1 if abs(cy - RING_Y[0]) <= abs(cy - RING_Y[1]) else 2
    col = int(round((cx - RING_X0) / 24)) + 1
    if not 1 <= col <= 10:
        return None
    return (row - 1) * 10 + col


def goto(n):
    """键盘把光标移到格 n。返回最终关号（失败 None）。"""
    for attempt in range(3):
        c = cursor_green(ds.grab(""))
        if c is None:
            time.sleep(1.0)
            continue
        rc, cc = divmod(c - 1, 10)
        rn, cn = divmod(n - 1, 10)
        while cc != cn:
            ds.press("Right" if cn > cc else "Left", **STEP)
            cc += 1 if cn > cc else -1
        while rc != rn:
            ds.press("Down" if rn > rc else "Up", **STEP)
            rc += 1 if rn > rc else -1
        time.sleep(0.4)
        got = cursor_green(ds.grab(""))
        if got == n:
            return n
    return None


def board_walls(im):
    a = np.asarray(im.convert("RGB")).astype(int)
    out = []
    for r in range(6):
        row = ""
        for c in range(6):
            cx, cy = X0 + P * (c + 0.5), Y0 + P * (r + 0.5)
            cell = a[int(cy) - 7:int(cy) + 7, int(cx) - 7:int(cx) + 7].reshape(-1, 3)
            blue = ((cell[:, 2] > 100) & (cell[:, 2] > cell[:, 0] + 35)).mean()
            row += "W" if blue > 0.35 else "."
        out.append(row)
    return out


def expected_walls(pz):
    return ["".join("." if pz["given"][y * pz["w"] + x] == 45 else "W"
                    for x in range(pz["w"])) for y in range(pz["h"])]


def board_dark_count(im):
    a = np.asarray(im.convert("RGB")).astype(int)
    reg = a[Y0:Y0 + 6 * P, X0:X0 + 6 * P]
    return int(((reg[:, :, 0] < 60) & (reg[:, :, 1] < 60) & (reg[:, :, 2] < 60)).sum())


def wait_select(timeout=12):
    t0 = time.time()
    while time.time() - t0 < timeout:
        im = ds.grab("")
        a = np.asarray(im.convert("RGB")).astype(int)
        rows_ok = 0
        for y in (290, 310):
            row = a[y]
            m = (row[:, 2] > 90) & (row[:, 0] < 90) & (row[:, 1] > 70)
            runs, s = 0, None
            for i, v in enumerate(m):
                if v and s is None:
                    s = i
                if not v and s is not None:
                    if i - s > 12:
                        runs += 1
                    s = None
            if s is not None and 255 - s > 12:
                runs += 1
            if runs >= 9:
                rows_ok += 1
        if rows_ok >= 1:
            return True
        time.sleep(0.8)
    return False


def escape_to_select():
    """从游戏内 Start 菜单退回选关页。
    ★2026-10-28 实测定案：問題選択へ按钮 y 210-221（中心215，原237误触ギブアップ）；
    はい确认后**直接回选关页，无「正解表示」环节**——旧序列末尾多余的 x 在选关页
    上等于「进光标所在关」，是 Q11 误入关卡的根因，已删。"""
    ds.press("Return", wait=1.5)         # 打开 Start 菜单（若已开着再按=关闭，调用方需保证菜单关着）
    ds.tap_local(197, 215, after=1.2)    # 問題選択へ
    ds.press("x", wait=1.5)              # はい
    return wait_select()


def at_title(im):
    """标题页判定：slot 页有蓝底行(0,98,131)，标题页没有。"""
    a = np.asarray(im.convert("RGB")).astype(int)
    seg = a[205:315, 8:248]
    blue = ((seg[:, :, 0] < 50) & (np.abs(seg[:, :, 1] - 98) < 40) & (np.abs(seg[:, :, 2] - 131) < 40)).sum()
    return blue < 300


def boot_to_select():
    """标题 -> 存档槽 -> 菜单 -> 入門选关页（实测路径）。返回 True/False。"""
    if wait_select(3):
        return True
    for _ in range(3):
        ds.press("x", wait=2.2)
        if not at_title(ds.grab("boot_title")):
            break
    ds.tap_local(128, 232, after=1.2)      # 槽1
    ds.press("x", wait=2.0)                # スタート
    ds.press("x", wait=2.0)                # 进 入門选关页（スタート高亮）
    return wait_select(6)


def bulb_points(pz):
    """bulbs -> tap_batch 用的 NDS 触摸坐标 [(nx, ny), ...]"""
    pts = []
    for (x, y) in pz["bulbs"]:
        nx = int(X0 + P * (x + 0.5))
        ny = int(Y0 + P * (y + 0.5) - 192)
        pts.append((nx, ny))
    return pts


SENTINEL = "/tmp/v12_rec_start"     # 开录哨兵：导航到起始关成功后写入
STOP_SENTINEL = "/tmp/v12_rec_stop"  # 停录哨兵：全部关卡完成后写入


def main(lo, hi):
    data = json.load(open(PUZZLES))
    seq = data["入門"]
    done = []
    if not wait_select(4):
        print("不在选关页，执行 boot_to_select…", flush=True)
        if not boot_to_select():
            ds.grab("FAIL_boot_escape")
            print("!! 无法回到选关页，中止", flush=True)
            return
    for n in range(lo, hi + 1):
        pz = seq[n - 1]
        assert pz["rec"] == n and pz["w"] == 6 and pz["h"] == 6, f"Q{n} 尺寸异常"
        print(f"== Q{n:02d} 灯数={len(pz['bulbs'])} ==", flush=True)
        # 导航到格 n 并确认
        if goto(n) != n:
            ds.grab(f"FAIL_Q{n}_nav")
            print(f"!! Q{n} 光标导航失败，中止", flush=True)
            break
        # ★ limiter ON（正常 60fps 游戏速度）：进关后触摸**在游戏内约 5s 内一律无效**
        #   （开场动画期间输入被屏蔽）。实测：等 2.6s→只有后 4 灯生效；
        #   4.5s→7-8 灯；6.0s→9/9 全中并整盘通关。按 x 不能提前解除。
        #   故这里等 5.5s 留余量，之后再点灯才能 9/9 命中。
        # ★ 开录哨兵：首个关卡导航成功后触发，录制脚本据此才开始抓帧
        #   （boot/标题/存档槽阶段不录）。
        if n == lo and not os.path.exists(SENTINEL):
            open(SENTINEL, "w").write("go")
            print("    [哨兵] 开录", flush=True)
        ds.press("x", wait=5.5)          # 进关 + 等开场动画结束 + 等触摸解禁
        # 防御：墙布局比对（★limiter ON 下开场动画比 5.5s 更长，盘面是逐步画出来的，
        #   过早比对必然 partial 匹配。实测稳定后 36/36，故放宽轮询窗口到 ~10s）
        exp = expected_walls(pz)
        match = 0
        for _ in range(9):
            match = sum(a == b for a, b in zip(
                "".join(board_walls(ds.grab(""))), "".join(exp)))
            if match >= 34:
                break
            time.sleep(1.2)
        print(f"    墙匹配 {match}/36", flush=True)
        if match < 34:
            ds.grab(f"FAIL_Q{n}_walls")
            print(f"!! Q{n} 墙布局不符（可能进错关），中止", flush=True)
            escape_to_select()
            break
        # 点灯：tap_batch 单命令连发（无逐次 subprocess 开销）
        ds.tap_batch(bulb_points(pz), **BULB_DOSE)
        # 等点亮（盘面全亮即判定通关），随后让通关结算画面稳定，再按 x 回选关页。
        # ★ 结算画面未稳时按 x 会被吞：固定 settle 后单发 x，失败最多补 1 次（杜绝 3×重试风暴）。
        cleared = False
        t0 = time.time()
        while time.time() - t0 < 4:
            time.sleep(0.5)
            if board_dark_count(ds.grab("")) < 120:
                cleared = True
                break
        time.sleep(3.0)
        if not cleared:
            ds.grab(f"FAIL_Q{n}_clear")
            if wait_select(3):
                # 已在选关页 = 其实通关了（判定误报）
                print(f"    Q{n} 通关 ✓ (兜底判定)", flush=True)
                done.append(n)
                continue
            print(f"!! Q{n} 未通关，中止", flush=True)
            escape_to_select()
            break
        # ★2026-10-28 探针实测：结算稳定后单发 x 即回选关页（≈1.2s），
        #   游戏不会自动返回，故「前置 wait_select(12) 空等」与「后置冗余 wait_select」
        #   纯属浪费（每关 ≈12s）。改为 settle 后单发 x + 短超时确认 + 兜底补 1 次。
        ds.press("x", wait=0.6)
        if not wait_select(6):
            ds.press("x", wait=0.6)   # 兜底，极少触发
            wait_select(6)
        print(f"    Q{n} 通关 ✓", flush=True)
        done.append(n)
    print("已完成:", done, flush=True)
    open(STOP_SENTINEL, "w").write("done")


if __name__ == "__main__":
    lo = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    hi = int(sys.argv[2]) if len(sys.argv) > 2 else 20
    main(lo, hi)
