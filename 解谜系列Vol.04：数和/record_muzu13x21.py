# -*- coding: utf-8 -*-
"""录「むずかしい」13×21 关卡（第 21~80 問 → lv = 229 + k，lv250~309）。

=== 本档与前两档的结构差异（2026-11-07 实机破译，见 RESEARCH.md 12.16）===
* 选关页写「マス：13×21」；答案盘 = body[-308:]，形状 **22 行 × 14 列**，
  首行/首列全 0，取值 0..9，196 个数字格。
* 上屏迷你全盘视图：**14 列 × 12 行**，格距 16、网格左边界 x=31、上边界 y=0
  → TOPX = 31+16*(c+.5)、TOPY = 16*(r+.5)。比 11×19 的 x=63 左移 32px，
  因为本档左上竖排「第NN問」文字区更窄。14 列刚好铺满 31..255（14*16=224），
  故横向不滚动；全盘 22 行 → 视图纵向滚动 offset ∈ 0..10，仍用「亮格锚点」
  （classify==1 必是答案格）逐行匹配判定，填数前后判据一致不漂移。
* 上屏红框仍是下屏 7×7 视口在视图内的位置，但左边界从 63 变 31：
  c_view = round((x0-31)/16)、r_view = round(y0/16)。
* 下屏视口与前两档完全相同（7×7、格距 24、左上 (8,10)、Y.safe_xy 直接复用），
  但键盘改为竖排且整体左移上移：数字键 x=202/223/244、触屏 y=59/83/107。
* 滚动规律（12.17 重测后改写，旧结论「步长非线性」是采样假象）：
  下屏 ▼/▲/◀/▶ 是【按住期间连续滚动】，滚多远由按住时长决定，慢速段约
  13 格/秒、含 ~0.10s 启动延迟（短按 0.05~0.10s→1 格、0.22s→4 格、
  0.40s→5 格、横向 0.50s→7 格）。旧版一律 ds.click_touch(wait=.7) 固定
  按住 0.18s → 每次只滚 2 格，于是 22 行盘面要推 15 个视口才覆盖完。
  速率会随模拟器实时帧率漂移（同一 0.38s 实测过 5 格与 11 格），故不写死
  映射表，改「预测-实测-修正」闭环（见 Scroller）。
* 最少窗口：答案行 1..21、答案列 1..13。7 行窗口若从 r=1 起每 7 行一个，
  1-7 / 8-14 / 15-21 恰好铺满（这是「起点对齐 1 而非 0」的关键，起点取 0
  则三屏只够 0..20，末行 21 掉队）；横向 0-6 / 7-13 两屏铺满 14 列。
  合起来 3×2=6 个窗口、蛇形 5 次滚动，即几何下界。
"""
import base64
import io
import os
import subprocess
import sys
import time
import json

import numpy as np
from PIL import Image

sys.path.insert(0, '/tmp')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds
import record_all as R
import record_yasa as Y
import record_futsu11 as F

# ふつう 11×19 选关层的缩略盘（11×19 白格）占满上屏右侧，_blue_top 降到 ≈0.31，
# 低于 record_futsu11._on_select_screen_futsu() 的 0.35 硬门槛 —— 明明在选关层
# 也会返回 False，ensure_select() 会连按 A 误进关。这里再局部覆盖一次：去掉
# blue_top 硬门槛，改以「按钮行墨色 + 下屏蓝底 + 关号按钮红色像素」判据。
def _on_select_screen_11x19():
    im = ds.shot()
    # 存档画面 / オプション页都曾被旧判据误判成选关层（068/069 实测）：
    # 前者满屏蓝 + 橙框，后者按钮行墨色凑巧达标但 blue_bottom 只有 0.26。
    # 先排除存档画面，再要求下屏蓝底，最后以「已通关关号整片红」为主判据。
    if save_screen(im):
        return False
    b = R._blue_bottom(im)
    if b <= 0.42:
        return False
    if R._sel_red(im) > 400:
        return True
    vals = [R._pen(im, x, y) for y in (264, 292) for x in R.SELC_COLS]
    return (sum(1 for v in vals if 20 <= v <= 90) >= 18
            and sum(1 for v in vals if v > 100) <= 1)


R.on_select_screen = _on_select_screen_11x19

# 选关滚动改为确定性，不再依赖 S 模板。原因（067 实测）：
# 通关数 >60 后关号按钮整片变红，cap_top_left() 指纹失配，top_left_S() 会把
# 窗口起点 S 误判成 1 → row=(k-1)//10 越界抛 IndexError；或错点关号进到
# 11×11 档关卡（如第47問），sweep() 拿 20 行答案盘去填 12 行盘面死循环超时。
# 改为：force_top() 纯点击回顶（无模板分支点满 12 次 ▲ 必到顶）+ 固定 t 次 ▼，
# S = 1+10t 直接计算，不读 top_left_S。进错关由 record() 的 view_off rate 兜底。
def _leftnum(im):
    """选关网格左上角第一个关号按钮上的【白色数字】位图。

    关键点：通关后关号按钮整片变红（红底白字），record_futsu11.cap_top_left()
    取的是「墨色」（_ink_bgrel），在红底上取不到笔画 → 归一化后退化成固定占位
    位图（实测 sum 恒 240、翻页 XOR 恒 0），这正是 067 滚动错位的真正根因：
    判据以为每次 ▼ 都没生效，实际页面已经翻过去了。改用白色数字位图则
    静止双采样 XOR=0、翻页 XOR=28，干净可靠且与通关颜色无关。
    """
    a = np.array(im.convert('RGB'))
    r, g, b = a[:, :, 0].astype(int), a[:, :, 1].astype(int), a[:, :, 2].astype(int)
    return ((r > 185) & (g > 185) & (b > 185))[255:285, 10:44]


def _scroll_to_show_11x19(k):
    """回顶 → 逐次 ▼ 到含 k 的窗口，每次翻页都用左上关号位图闭环验证。

    不再用 F.force_top()：它点满 12 次 ▲ 就假定到顶、不校验；也不再用
    cap_top_left()（红底失配）。改用自己的「连续 3 次 ▲ 无变化才认定到顶」
    + 「每次 ▼ 后左上关号数字确实改变才继续」，被吞就补点。
    """
    t = max(0, -((40 - k) // 10))
    S = 1 + 10 * t

    # 回顶：连点 ▲，连续 3 次点击都未引起左上关号变化 → 已到顶 S=1
    prev = _leftnum(ds.shot())
    still = 0
    for _ in range(20):
        ds.click_touch(*F.SCROLL_UP, wait=0.85)
        time.sleep(0.4)
        cur = _leftnum(ds.shot())
        if int((cur ^ prev).sum()) == 0:
            still += 1
            if still >= 3:
                break
        else:
            still = 0
            prev = cur

    # 逐次 ▼：每次必须看到左上关号数字变化（实测翻页 XOR≈28，静止 XOR=0）
    for step in range(t):
        moved = False
        for retry in range(6):
            base = _leftnum(ds.shot())
            ds.click_touch(*F.SCROLL_DOWN, wait=0.9)
            time.sleep(0.5)
            cur = _leftnum(ds.shot())
            if int((cur ^ base).sum()) >= 8:
                moved = True
                break
        if not moved:
            print('  [scroll] %03d 第%d次 ▼ 补点 6 次仍未翻页' %
                  (k, step + 1), flush=True)
    return (k - S) // 10, (k - S) % 10, S


F.scroll_to_show = _scroll_to_show_11x19

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, 'validation', 'vol4_all.json')
# 模板一律【内嵌 base64】：仓库 .gitignore 有 `*.png`（媒体不入库），
# 旧 11×19 脚本靠本地 ref_*.png 文件，克隆后必然缺文件跑不起来。本档把三张
# 几十像素的小模板直接编进源码，脚本自包含、无外部依赖。
_TPL_SIZE_B64 = (
    'iVBORw0KGgoAAAANSUhEUgAAABsAAAALCAIAAAABYGGZAAABcElEQVR4nK1TIYzCMBR9kBOHK26TlZVD9hTgwDEHOE4dSBxBERznmAM3UAw33EBRxzmCa+VQDAXIE03KcrkcuYSfit/X9377X9uMlCc8NTIWc/5mjHoTk3eH74+ZFnNqH70okrvdyWKOxRx/sZfyIuXFX+wt5kh50uPX1bRW014A1Ep1Si29Dy9Wlut5t78S4ZYXKABeLZtT8GKFUVt8KV6gejWtFULduxbhFgCvvhmxCLdKHePkyqh9Pp+9YNp2W14wFZsVgNCP8vlXzTdaEUYAsrr5JLklyc14EfpRktwIIZ43BEAIqZXqppwOpY46MVohlBAqyzlNu6u9rzbLBxUDsBkdTj8B2PmcKTcbBwcVNzruj5vhnHJOs2mbtFO8WAHQ7TcBxAelcUKIxkcDH8ByPR8NfI3ctdWyECpjMYcXK223BcALpgB0HifX5Xqup42OOxsHGrTzOVOi0XHTWrFZiTB6/B7/FaPeJPP0P/MNnFfKkIfgjWUAAAAASUVORK5CYII=')
_TPL_MASU_B64 = (
    'iVBORw0KGgoAAAANSUhEUgAAABYAAAASCAIAAADQR7l6AAABOElEQVR4nKVTIVuDUBQ9+C1gm03ibK5hfNG4tdGwSYSfQJyNNYiYlDTWIGK7cTQWnw0bttEwwMdA5jbkFO537j3nu493nrB4tjEAobe/GqIHMFOvhaIo/qFUNKeuWxY8zcKQbsc3isJqZks7ADXTdTlYOG5gLL2ylifSNrKIEsN8jXkKoODvf+1y+BfG0rNNdfHIAMQ89X1auR+l/jQqC6LENlVdm/uuXvd8Vy8dT2NUfhibMjYFwNOsWrJz+DNb1FCeXgCsLf3Y8AUWiubEPF1b+gO7d9ygt4WiOZuI5InkhfEdMyL67GfhuMEmIgAxT8tCnck1iXaWfqHKBVES73izoWtz36ev76zJNAeORKsXWgEf+FLRvdS+CL29MB6/AXmeZ82GKEoALuRHgARAFMXGpNTQnOd/AKXSj7Z1gl/dAAAAAElFTkSuQmCC')
_TPL_DIGITS_B64 = (
    'iVBORw0KGgoAAAANSUhEUgAAAKsAAAATCAAAAADKGqLdAAABRElEQVR4nO1WOZLDMAwDdvL/L3ML2ToAkk5mmy2CJjLCA6ZEygQABAAAxELMFSfDi97tBpV68g2bxcZYx0ndOQngdTks5z1IGEM3dFCJcI6n5MUHwvwHfop04UmLCPlbPphcNny021FpZaHMMlh8T6gHYNmE88kW3B6vWlIKD+XnJznT4lcWwl9rQ1XXIm5AClduW9gq+i2g/Dp6rWnFdlY3sRRCb1UVxjznwmNdz/YyZS6VHMKeOqXEOc+2KK3WbNQc/qWcpNpeWPGe2UTsPP5dbxUteRjEvdKOe6uqcj3QGvXYoKaucRVRsvbyPzUrMusTgU7rLFVyJP+go1LUxh5keQYieT1tGZ7/iNkcQsnlX+uyCbui93eskvW94maaMJ9/T4gtn3Te+qZa0LnXf5lEYhUY1RX52dV2lrW9xr744l/jF43sbyBef87FAAAAAElFTkSuQmCC')


def _tpl(b64s):
    """base64 PNG → 灰度 ndarray。"""
    return np.array(Image.open(io.BytesIO(base64.b64decode(b64s))).convert('L'))
OUTDIR = '/workspace/Vol.4_むずかしい13x21录播'


def masu_ok(im):
    """选关层上屏固定 UI「マス：13×21」文字条校验（进错档硬判据）。

    点中关号后、按 A 进关前，上屏预览会显示该关的尺寸文字条：
    13×21 档为「マス：13×21」，11×19 档为「マス：11×19」。
    实测同档不同关 xor=0.000、跨 11×19 档 xor=0.106，是唯一能 100% 区分档位
    的判据 —— size_ok() 与 view_off rate 只比斜线格布局，11×11 与 11×19
    前 12 行布局相似时会同时给出 1.000，拦不住「滚动错位落到第47問」。
    """
    ref = _tpl(_TPL_MASU_B64) < 130
    q = np.array(im.convert('L'))[48:66, 88:110] < 130
    return (ref ^ q).mean() < 0.03


_orig_select_level_11 = F.select_level_11


def _select_level_11x19(row, col, tag):
    """点中关号后先确认上屏预览确为 11×19 档，不是就拒绝进关。

    滚动 ▼ 偶发被吞 → 窗口停在 S=11 → 点 (3,6) 落到 11×11 档第47問。
    此时若继续按 A 进关，sweep() 会拿 20 行答案盘去填 12 行盘面，
    r0 乱跳、停滞抛异常、录不出结算页。宁可让 enter_level_11 重试翻页，
    也绝不进错关。
    """
    if not _orig_select_level_11(row, col, tag):
        return False
    time.sleep(0.35)                    # 等上屏预览刷新
    if not masu_ok(ds.shot()):
        print('  [%s] !! 选中关预览非 13×21（滚动错位进错档），拒绝进关' % tag,
              flush=True)
        return False
    return True


F.select_level_11 = _select_level_11x19

LV0 = 229                # 第 k 問 → lv = LV0 + k（問21~80 → lv250~309）
ROWS, COLS = 22, 14      # 答案盘形状（含提示行列；13×21 档 = 22 行 × 14 列 / 308 字节）
TOPX = lambda c: int(31 + 16 * (c + .5))   # 13×21：网格左边界 x=31（不是 63）
TOPY = lambda r: int(16 * (r + .5))
LEAD_IN = 2.0
TARGET_TOTAL = 60.0
HOLD_MIN, HOLD_MAX = 5.0, 15.0


def load_disk(lv):
    rep = json.load(open(DATA, encoding='utf-8'))
    body = bytes.fromhex(rep['levels'][lv]['body_hex'])
    disk = body[-(ROWS * COLS):]
    return disk


_LAST_OFF = [0]     # view_off 最近一次成功的偏移（锚点不足时兜底）


def view_off(im, disk, off_min=0):
    """上屏 12×12 视图对应的全局起始行 offset（0..8）。返回 (off, rate)。

    === 12.14.7 关键修复：只以【亮格】为锚点，杜绝「填数后判据反转」===
    旧版用 R.classify 判「亮=1(答案格) / 暗=0(斜线格)」再与 disk 逐格比对。
    但【已填的深蓝数字格也是暗的】，会被 classify 判成 0，与 disk=1 冲突；
    盘面越填、暗格越多，匹配率越低、off 在多个候选间随机漂移 —— 实测 r0
    从 13 乱跳到 5/1/3/6，造成 067 差 7 格补不上、078/086/102 假满 N/N 却
    不 CLEAR、sweep 纵向停滞误抛。曾试过把「深蓝数字」补判成 1，但 11×19
    上屏的【提示格和数数字 / 斜线墙纹理】同样是深蓝（13×13 块深蓝像素
    78~106），空白盘就崩到 0.674，不可用。

    这里改用不变式：classify==1 的【亮白格/橙色高亮格】必定是答案格
    (disk=1)，而所有暗格（提示数字、斜线墙、已填数字）一律不参与匹配。
    填数只会让亮格集合【单调缩短】，剩下的亮格仍精确对应 disk 的 1，
    故空白 / 部分填 / 全填三种状态下判据完全一致，off 不再漂移。
    off_min：sweep 按 ▼ 单向推进，off 单调不减，用它排除回跳的伪候选。
    """
    best = None
    for off in range(off_min, ROWS - 12 + 1):
        ok = jd = 0
        for r in range(12):
            for c in range(COLS):
                if R.classify(im, TOPX(c), TOPY(r)) != 1:   # 只取亮格锚点
                    continue
                jd += 1
                if disk[(r + off) * COLS + c]:
                    ok += 1
        if best is None or ok > best[0]:
            best = (ok, off, jd)
    if best is None or best[2] < 5:
        # 亮格快被填光时锚点不足，off 退化成 off_min 会把视口判错；沿用上次
        # 成功值。进关（盘面全空）时锚点有一两百个，走不到这里。
        return _LAST_OFF[0], 1.0
    _LAST_OFF[0] = best[1]
    return best[1], best[0] / best[2]


def red_frame(im):
    """上屏 7×7 红框 → (r_view, c_view, x0, y0)；无红框返回 None。

    13×21 档的网格左边界是 x=31（11×19 是 63），F.red_origin_11() 里写死的
    (x0-63)/16 会算出 -2，必须本档自己实现。实测空白盘 x0=31/y0=0 →
    r_view=0/c_view=0，与 #000 进关初始态一致。
    """
    a = np.array(im.convert('RGB'))
    r = a[0:192, :, 0].astype(int)
    g = a[0:192, :, 1].astype(int)
    b = a[0:192, :, 2].astype(int)
    m = (r > 170) & (g < 95) & (b < 95) & (r > g + 80) & (r > b + 80)
    ys, xs = np.where(m)
    if len(xs) < 30:
        return None
    x0, y0 = int(xs.min()), int(ys.min())
    return (int(round(y0 / 16.0)), int(round((x0 - 31) / 16.0)), x0, y0)


def origin(im, disk):
    """当前下屏视口的全局起点 (r0,c0) + 上屏视图偏移 off。"""
    f = red_frame(im)
    if f is None:
        return None
    off, rate = view_off(im, disk)
    return (off + f[0], f[1]), off, f, rate


def lit_global(im, todo, off):
    """按上屏视图偏移平移，判读 todo 中已出现深蓝数字的格。"""
    s = set()
    a = np.array(im.convert('RGB'))
    for r, c, v in todo:
        if not (off <= r <= off + 11):
            continue
        cx, cy = TOPX(c), TOPY(r - off)
        seg = a[cy - 6:cy + 7, cx - 6:cx + 7]
        rr, gg, bb = seg[:, :, 0].astype(int), seg[:, :, 1].astype(int), seg[:, :, 2].astype(int)
        if ((rr < 105) & (gg < 115) & (bb < 175)).sum() > 12:
            s.add((r, c))
    return s


def save_screen(im):
    """「セーブ中…電源を切らないでください」蓝色存档画面判据。

    R.in_result_screen() 只看 _blue_bottom>0.4，存档画面同样满屏蓝会被误判成
    结算页（12.13 实测）。存档画面中央是大橙框文字，结算页该区域没有；
    按 12.13 逐帧分析用过的橙框阈值区分，批量录制必须靠它保证末帧是结算页。
    """
    a = np.array(im.convert('RGB'))
    seg = a[250:325, 15:245]
    rr, gg, bb = seg[:, :, 0].astype(int), seg[:, :, 1].astype(int), seg[:, :, 2].astype(int)
    orange = int(((rr > 195) & (gg > 85) & (gg < 205) & (bb < 115)).sum())
    # 决定性特征：存档画面【上屏满屏纯蓝】blue_top≈1.000；选关层仅 0.430，
    # 结算页/盘面/オプション页 <0.07。橙色阈值单独用会把选关层整片红色
    # 关号按钮误判成存档橙框（实测选关层 orange=463、sel_red=1318），故只作辅助。
    return (R._blue_top(im) > 0.9
            and R._blue_bottom(im) > 0.4
            and orange > 200)


def size_ok(im):
    """上屏左侧尺寸标注必须是「11×19」。

    选关滚动 ▼ 偶发只生效 1 次会把窗口停在 S=11，点 (3,6) 就落到第47問
    （11×11 档）。空白盘面时 classify 只判白格布局，view_off rate 与
    ensure_board11 的 match 都会给出 1.000，拦不住进错关；但上屏左侧的
    尺寸文字是硬证据：正确关与参考模板 xor=0.000，11×11 档 xor=0.047。
    参考模板取自第068問空白盘面，随脚本一同入库。
    """
    ref = _tpl(_TPL_SIZE_B64) < 140
    q = np.array(im.convert('L'))[95:106, 3:30] < 130
    return (ref ^ q).mean() < 0.02


def real_result(im):
    """真正的 ★★★★★ 结算页（むずかしい档专用，见文件头）。

    ふつう档用 _sel_red<60 排除「已通关关号整片红」的选关层；本档 20 关
    全未通关、无红号，选关层 sel_red=39 与结算页(0)混淆，该判据失效。
    改用【上屏蓝色占比】：真结算页上屏是填满数字的盘面，blue_top≈0.04；
    选关层(0.317, 上屏缩略盘+UI) / 难度页(0.543) / 存档画面(1.0) 均 ≥0.3。
    盘面 blue_bottom<0.4 由第一项排除。save_screen 保留作冗余兜底。
    """
    return (R._blue_bottom(im) > 0.4
            and R._blue_top(im) < 0.15
            and not save_screen(im))


# ---------- 视口滚动：按住时长控制 + 自适应速率闭环 ----------
# === 12.17：用户指出「滚动次数太多」后重测得到的关键事实 ===
# 方向键不是离散的一次一格，而是【按住期间连续滚动】；旧版固定按住 0.18s
# 只能滚 2 格，于是 22 行盘面推了 15 个视口（r0∈{0,4,11,13,15}×c0∈{0,5,7}）。
# 速率随模拟器实时帧率漂移（同 0.38s 一次测到 5 格、另一次 11 格），写死映射
# 表必翻车，故做成「预测 → 实测 → 修正」，同一次运行内速率稳定后基本一次到位。
RATE0 = 13.0        # 慢速段初始估计（格/秒）
BASE0 = 0.10        # 启动延迟（秒）：短于它只滚 1 格
HOLD_MAX = 0.46     # 单次按压上限：超过 ~0.5s 滚动会二次加速（实测 0.56s
                    # 滚了 12 格），冲过头再倒回来在视频里很难看，宁可欠一点
                    # 同向再补一次短按。


class Scroller:
    def __init__(self):
        self.rate = RATE0
        self.base = BASE0
        self.n = 0                       # 累计按压次数（用于日志/优化评估）

    def hold_for(self, delta):
        """目标滚 delta 格需要的按住时长。delta<=1 用最短按。"""
        if delta <= 1:
            return 0.10
        return max(0.12, min(HOLD_MAX, self.base + (delta - 1) / self.rate))

    def press(self, name, hold, wait=0.42):
        """按住方向键 hold 秒（ds.click_touch 固定 0.18s，这里要可控）。"""
        x, y = R.V8_ARROW[name]
        g = ds.geom()
        sx = g['x'] + int(x * g['w'] / 256)
        sy = g['y'] + g['h'] // 2 + int(y * (g['h'] / 2) / 192)
        subprocess.run(['xdotool', 'mousemove', str(sx), str(sy)], env=ds.ENV)
        time.sleep(0.04)
        subprocess.run(['xdotool', 'mousedown', '1'], env=ds.ENV)
        time.sleep(hold)
        subprocess.run(['xdotool', 'mouseup', '1'], env=ds.ENV)
        time.sleep(wait)

    def sync(self, hold, moved, at_edge):
        """用一次实测样本修正速率估计（饱和到边界/零位移的样本丢弃）。"""
        if at_edge or moved <= 0:
            return
        eff = hold - self.base
        if eff < 0.05:
            return
        obs = moved / eff
        obs = min(28.0, max(6.0, obs))
        self.rate = 0.65 * self.rate + 0.35 * obs

    def to(self, tr, tc, disk, tag='', tries=10):
        """闭环滚到视口起点 (tr,tc)，返回最终实读 (r0,c0)。"""
        last = (None, None)
        for _ in range(tries):
            q = origin(ds.shot(), disk)
            if q is None:
                time.sleep(0.25)
                continue
            r0, c0 = q[0]
            last = (r0, c0)
            if (r0, c0) == (tr, tc):
                return last
            dr, dc = tr - r0, tc - c0
            if abs(dr) >= abs(dc) and dr != 0:      # 幅度大的轴优先
                name, delta = ('D' if dr > 0 else 'U'), abs(dr)
            else:
                name, delta = ('R' if dc > 0 else 'L'), abs(dc)
            hold = self.hold_for(delta)
            self.press(name, hold)
            self.n += 1
            q2 = origin(ds.shot(), disk)
            after = q2[0] if q2 else last
            moved = (abs(after[0] - r0) if name in 'DU' else abs(after[1] - c0))
            at_edge = (after[0] in (0, ROWS - 7) if name in 'DU'
                       else after[1] in (0, COLS - 7))
            self.sync(hold, moved, at_edge)
            print('    [%s] %s%d hold=%.2f → (%d,%d)' %
                  (tag, name, delta, hold, after[0], after[1]), flush=True)
            last = after
        print('  [%s] !! 滚动未到 (%d,%d)，停在 %s' % (tag, tr, tc, last), flush=True)
        return last


SC = Scroller()


# 13×21 档右下键盘（竖排、比 11×19 左移上移）：实测数字笔画中心
# 列 x=202/223/244（间距 21.5），行触屏 y=59/83/107（间距 24）。
NUM13_X = (202, 223, 244)
NUM13_Y = (59, 83, 107)


def num_xy13(v):
    """数字 v(1..9) 的键盘触屏坐标（13×21 档专用布局）。"""
    return NUM13_X[(v - 1) % 3], NUM13_Y[(v - 1) // 3]


def fill_cell13(vr, vc, v):
    """点下屏视口内 (vr,vc) 格 → 点数字键。格坐标沿用 Y.safe_xy（同前两档）。"""
    tx, ty = Y.safe_xy(vr, vc)
    nx, ny = num_xy13(v)
    R.fast_tap(tx, ty)
    R.fast_tap(nx, ny)


# ---------- 读回校验（13×21 专用，前两档没有） ----------
# 字模取自实机标定图：把 1~9 依次打进 9 个已知格，按 (cx,cy)=(20+24c, 214+24r)
# 裁 19×19 深蓝笔画掩码，拼成一条 171×19 雪碧图。混淆矩阵 9/9 全对角、
# 交叉最小 0.125（命中门槛 0.09），可无歧义区分 0(空白)/1~9。
def _load_digits():
    a = _tpl(_TPL_DIGITS_B64)
    return [(a[:, i * 19:(i + 1) * 19] > 128).astype(np.uint8) for i in range(9)]


DIGITS = _load_digits()


def read_cell13(im, vr, vc, pad=9):
    """读下屏视口内 (vr,vc) 格显示的数字：0=空、1~9、-1=认不出。"""
    a = np.array(im.convert('RGB'))
    cx, cy = 20 + 24 * vc, 214 + 24 * vr
    seg = a[cy - pad:cy + pad + 1, cx - pad:cx + pad + 1]
    if seg.shape[0] != 19 or seg.shape[1] != 19:
        return -1
    r, g, b = seg[:, :, 0].astype(int), seg[:, :, 1].astype(int), seg[:, :, 2].astype(int)
    ink = ((r < 120) & (g < 130) & (b < 185)).astype(np.uint8)
    if ink.sum() < 25:
        return 0
    best = None
    for i, t in enumerate(DIGITS):
        d = float((ink ^ t).mean())
        if best is None or d < best[0]:
            best = (d, i + 1)
    return best[1] if best[0] < 0.09 else -1


def fill_view(todo, r0, c0, disk, tag, filled):
    """填当前视口内 todo 格（单遍 fast）+ 点击即记入 filled。

    === 12.14.7 第二次修复：删除读回补点 / 不要双遍 ===
    旧版填完 todo 后用 `view_off(im,disk) + lit_global` 读回判 miss，对 miss
    用 `Y.fill_cell(slow=True)` 补点（约 0.7s/格）。但 11×19 盘面渐满时亮格
    锚点变少、off2 漂移，lit_global 平移错位把【已填格误判成 miss】→ 每视口
    都触发十几格 slow 补点 → 162 格的 117 問实测 240s 只填到 113/162 超时。
    曾改成 fast 双遍（幂等），但 162 格 × 2 遍等于点击量翻倍 ≈ 250s，同样
    压垮超时。最终确认：单遍即可，偶发被吞的格由 record() 的补漏轮（已传
    filled、只补缺失格）秒级补齐，无需在单视口内重复点。filled 点击即记入、
    成败交给 real_result()，既不读回也不补点，最快且稳。
    """
    if not todo:
        return
    for r, c, v in todo:
        fill_cell13(r - r0, c - c0, v)
    filled |= {(r, c) for r, c, v in todo}

    # === 13×21 新增：字模读回校验 ===
    # 前两档（11×11 / 11×19）靠「填满即 CLEAR」兜底，本档实测第一次跑完
    # 196/196 却没 CLEAR —— 原因是触摸偶发被吞：格点击没生效时，紧跟着的
    # 数字键会把数字打到【上一个仍处于选中态的格】上，把已填对的格覆盖成
    # 错值，而本档的 filled 记账仍认为该格已填。这种「错值 + 不空」用
    # 亮格/暗格判据根本看不出来，只能逐格认字。故填完立刻按字模读回，
    # 值不符（含读成 0=空）就重打一遍，最多 2 轮。
    for rep in range(2):
        time.sleep(0.22)
        im = ds.shot()
        bad = []
        for r, c, v in todo:
            got = read_cell13(im, r - r0, c - c0)
            if got != v:
                bad.append((r, c, v, got))
        if not bad:
            return
        print('  [%s] 视口(%2d,%2d) 第%d轮读回纠正 %d 格 %s' %
              (tag, r0, c0, rep + 1, len(bad),
               [(r, c, v, g) for r, c, v, g in bad[:6]]), flush=True)
        for r, c, v, _g in bad:
            fill_cell13(r - r0, c - c0, v)


def _win_dist(r0, c0, r, c):
    """(r,c) 到当前 7×7 视口窗口的曼哈顿距离（窗口内为 0）。"""
    return (max(0, r - r0 - 6) + max(0, r0 - r)
            + max(0, c - c0 - 6) + max(0, c0 - c))


WIN = 7


def plan_windows():
    """用最少 7×7 窗口覆盖全盘：行 {1,8,15} × 列 {0,7}，蛇形 5 次滚动。

    答案盘 22 行 × 14 列，首行/首列是提示行列（全 0），答案格落在
    r=1..21 / c=1..13。纵向从 r=1 起每 7 行取一个起点：1-7 / 8-14 / 15-21
    正好吃下 21 行（起点取 0 则三屏只到 20 行，末行 21 掉队 —— 这就是旧版
    不得不加第 4 个行窗口的原因）；横向 0-6 / 7-13 两屏吃下 14 列。
    3×2=6 个窗口、5 次滚动，已是几何下界（ceil(21/7)=3、ceil(14/7)=2）。
    """
    starts_r, r = [], 1
    while r < ROWS:
        starts_r.append(min(r, ROWS - WIN))
        r += WIN
    starts_c = list(range(0, COLS, WIN))
    order = []
    for i, r0 in enumerate(starts_r):
        cs = starts_c if i % 2 == 0 else list(reversed(starts_c))
        for c0 in cs:
            order.append((r0, c0))
    return order


def window_cells(remain, r0, c0):
    return [t for t in remain
            if r0 <= t[0] <= r0 + WIN - 1 and c0 <= t[1] <= c0 + WIN - 1]


def sweep(cells, disk, tag, filled0=None):
    """按 6 窗口蛇形扫描：一次滚动到一屏，填满再走下一屏。

    === 为什么整体换掉旧贪心（12.17）===
    旧版每步只读 (r0,c0) 再朝最近未填格推【一格】，而一格按压 0.18s 只滚
    2 格，于是 15 个视口、二十余次按压，视频里视口碎步乱挪。新版先算出
    6 个能铺满全盘的窗口起点，逐个用 Scroller 一次按住滚到位（欠 1 格就补
    一次短按），滚完仍按【实读】位置填格 —— 即使微调没完全对上，也只会
    少填几格交给兜底，不会填错格。

    filled0：补漏轮的初始已填集合，只补真正缺的格。
    """
    filled = set(filled0) if filled0 else set()
    remain = [(r, c, v) for r, c, v in cells if (r, c) not in filled]
    n0 = SC.n
    print('  [%s] 窗口扫描开始，待填 %d/%d' % (tag, len(remain), len(cells)), flush=True)
    plan = plan_windows()
    for i, (tr, tc) in enumerate(plan):
        if not remain:
            break
        if not window_cells(remain, tr, tc):
            continue
        r0, c0 = SC.to(tr, tc, disk, tag)
        todo = window_cells(remain, r0, c0)
        if not todo:
            print('  [%s] 窗口(%d,%d) 实到(%d,%d) 内无待填格，跳过' %
                  (tag, tr, tc, r0, c0), flush=True)
            continue
        print('  [%s] 窗口 %d/%d (%d,%d)→(%d,%d) 待填 %2d 格 (累计 %d/%d)' %
              (tag, i + 1, len(plan), tr, tc, r0, c0, len(todo),
               len(filled), len(cells)), flush=True)
        fill_view(todo, r0, c0, disk, tag, filled)
        remain = [t for t in remain if (t[0], t[1]) not in filled]

    # 兜底：极少数情况（滚动被吞/窗口内实读偏差）会剩几格，按距离一次滚到
    # 该格所在窗口再填，不做逐格碎步（碎步正是本轮要消灭的东西）。
    guard = 0
    while remain:
        guard += 1
        if guard > 60:
            raise RuntimeError('兜底扫描迭代超限(60)，疑似盘面/视口异常')
        q = origin(ds.shot(), disk)
        if q is None:
            time.sleep(0.3)
            continue
        (r0, c0) = q[0]
        todo = window_cells(remain, r0, c0)
        if todo:
            fill_view(todo, r0, c0, disk, tag, filled)
            remain = [t for t in remain if (t[0], t[1]) not in filled]
            continue
        tr, tc = min(((t[0], t[1]) for t in remain),
                     key=lambda t: _win_dist(r0, c0, t[0], t[1]))
        SC.to(max(0, min(ROWS - WIN, tr)), max(0, min(COLS - WIN, tc)), disk, tag)
    print('  [%s] 扫描结束 %d/%d（本关按压 %d 次）' %
          (tag, len(filled), len(cells), SC.n - n0), flush=True)
    return filled


def enter_level13(k, tag):
    """回选关层 → 点第 k 問 → 校验上屏预览「マス：13×21」→ A 进关。

    13×21 档关号 21~80：第 1 窗口显示 1~40（4 行 × 10 列），故 k≤40 不需要
    翻页（問21 = row2/col0，实测点得中）；k>40 才走 ▼ 翻页。
    masu_ok 在点中关号后、按 A 前拦「滚动错位进别档」；盘面尺寸的硬校验
    放在 record() 里 wait_input_ready() 之后 —— START 演出期间左侧
    「13×21」文字还没绘制，此处判 size_ok 必然 False（实测连 3 次误判失败）。
    """
    for attempt in range(3):
        if not R.ensure_select(tag):
            continue
        time.sleep(0.8)
        if k <= 40:
            row, col = (k - 1) // 10, (k - 1) % 10
        else:
            row, col, _S = F.scroll_to_show(k)
        if not F.select_level_11(row, col, tag):
            continue
        ds.key('x', wait=1.0)
        time.sleep(1.0)
        if not R.on_select_screen():
            return True
        print('  [%s] 第%d次按 A 后仍在选关层 → 重试' % (tag, attempt + 1),
              flush=True)
    return False


def record(k):
    lv = LV0 + k
    tag = '%03d' % k
    disk = load_disk(lv)
    cells = [(r, c, disk[r * COLS + c])
             for r in range(ROWS) for c in range(COLS) if disk[r * COLS + c]]
    out = os.path.join(OUTDIR, 'Vol.4_数和_むずかしい13x21_%s_256x384.mp4' % tag)
    os.makedirs(OUTDIR, exist_ok=True)
    print('\n=== むずかしい13x21 %s (lv%d, %d行x%d列, %d 个数字格) ===' %
          (tag, lv, ROWS, COLS, len(cells)), flush=True)

    # 回选关层 → 确定性滚动进关（S 模板已弃用，见模块头 _scroll_to_show_11x19）
    R.ensure_select('boot')
    time.sleep(1.2)                    # 通关/存档刚回选关层时动画未稳，触摸易被吞
    F.force_top._tmpl = None
    if not enter_level13(k, tag):
        return False, '进关失败(盘面未就绪)'
    if not F.wait_input_ready(tag):
        return False, 'START演出未结束'
    # 进错关硬校验：滚动错位会落到 11×11 档关卡，空白盘面的 classify/match
    # 判据都会给出 1.000 拦不住，尺寸文字是唯一可靠证据。ffmpeg 尚未启动，
    # 直接失败让驱动快速重试（避免拿 20 行答案盘去填 12 行盘面死循环）。
    if not size_ok(ds.shot()):
        return False, '进关盘面尺寸不符(非13×21, 疑似滚动错位进错关)'
    _LAST_OFF[0] = 0
    q = origin(ds.shot(), disk)
    print('  [%s] 进关状态 off=%s rate=%s' %
          (tag, q[1] if q else None, round(q[3], 3) if q else None), flush=True)
    # 进错关兜底：正确关 view_off 逐格匹配率 1.000，错进 11×11 档关卡实测
    # 仅 0.667（067 进到第47問）。ffmpeg 尚未启动，直接失败让驱动快速重试，
    # 避免拿 20 行答案盘去填 12 行盘面造成 sweep 死循环 / 7 分钟超时。
    if q is None or q[3] < 0.95:
        return False, '进关盘面不符(rate=%s, 疑似滚动错位进错关)' % (
            round(q[3], 3) if q else None)

    p = R.ffmpeg_proc(out)
    t_vid0 = time.time()
    time.sleep(R.FFMPEG_WARM)
    time.sleep(LEAD_IN)
    t0 = time.time()

    filled = sweep(cells, disk, tag)
    # 最多再补三轮（应对盘面渐满时 r0 漂移漏掉个别视口）。
    # 传入 filled 作初值：补漏轮只点真正缺失的格，不再把整关重扫一遍
    # （12.14.7：162 格的 117 問曾因重扫吃满超时）。
    for rnd in range(3):
        if len(filled) >= len(cells):
            break
        print('  [%s] 第%d轮全盘补漏 (当前 %d/%d)' %
              (tag, rnd + 1, len(filled), len(cells)), flush=True)
        filled |= sweep(cells, disk, tag, filled)
    print('  [%s] 填数耗时 %.2fs，最终命中 %d/%d' %
          (tag, time.time() - t0, len(filled), len(cells)), flush=True)

    cleared = False
    for i in range(60):
        if real_result(ds.shot()):
            cleared = True
            break
        time.sleep(0.5)
    print('  [%s] 结算页 = %s (等待 %.1fs)' % (tag, cleared, i * 0.5), flush=True)
    # 注意：cleared=False 时【绝不按 A】。在盘面/演出/结算页按 A 会误填数字或
    # 误进关，把视频后半段搅成垃圾画面（065 实测：按 A 后重新进关录到 START
    # 演出）。直接收尾交给批量驱动标记失败，再用末尾裁切修复（视频里通常已有
    # 完整结算页，见 RESEARCH.md 12.13）。

    elapsed = time.time() - t_vid0
    hold = max(HOLD_MIN, min(HOLD_MAX, TARGET_TOTAL - elapsed))
    print('  [%s] 已录 %.2fs → 定格上限 %.2fs' % (tag, elapsed, hold), flush=True)
    # 结算页只停留约 2~3 s（重玩已通关关更短）就自动进「セーブ中…」蓝色存档
    # 画面；傻等 hold 会把末尾录成存档画面。只在 real_result() 为真时定格，
    # 一旦跳离立即收尾，保证最后一帧是 ★★★★★ 结算页。
    t_hold = time.time()
    last_result = None
    n_real = 0
    while time.time() - t_hold < hold:
        im = ds.shot()
        if not real_result(im) and n_real > 0:
            print('  [%s] 定格 %.2fs 后跳离结算页 → 收尾' %
                  (tag, time.time() - t_hold), flush=True)
            break
        if real_result(im):
            n_real += 1
            last_result = im
        time.sleep(0.2)
    print('  [%s] 定格阶段真结算页采样 %d 次' % (tag, n_real), flush=True)
    if last_result is not None:
        ds.save(last_result, '/tmp/mz13x21_end_%s.png' % tag)
    p.terminate()
    try:
        err = p.communicate(timeout=8)[1]
        if err:
            print('  [%s] ffmpeg stderr: %s' % (tag, err.decode('utf-8', 'ignore')[:200]), flush=True)
    except Exception:
        p.kill()

    if not os.path.exists(out) or os.path.getsize(out) < 5000:
        return False, '视频未生成/过小'
    time.sleep(0.6)
    flow_ok = R.ensure_select(tag)
    kb = os.path.getsize(out) // 1024
    if not cleared:
        return False, '未进入结算页(%d KB, 已复位, 命中%d/%d)' % (kb, len(filled), len(cells))
    if not flow_ok:
        return False, '通关后未回选关层(%d KB)' % kb
    return True, '%d KB, 命中 %d/%d 格' % (kb, len(filled), len(cells))


def main():
    k = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    ok, msg = record(k)
    print('\n=> むずかしい13x21 %03d %s %s' % (k, 'OK' if ok else 'FAIL', msg), flush=True)


if __name__ == '__main__':
    main()
