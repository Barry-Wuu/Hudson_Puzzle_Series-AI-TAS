# -*- coding: utf-8 -*-
"""录「ふつう」11×19 关卡（第 61~120 問 → lv = 109 + k，lv170~229）。

=== 与 11×11 档的唯一结构差异（实机破译 2026-11-07，见 RESEARCH.md 12.12）===
* 选关页写「マス：11×19」；答案盘 = body[-240:]，形状 **20 行 × 12 列**，
  首行/首列全 0，取值 0..9（0=斜线格，1..9=该格应填数字），共 144 个数字格。
  （11×11 档是 body[-144:] = 12 行 × 12 列。）
* 上屏是 **12×12 的迷你全盘视图**，格心仍是 TOPX=63+16*(c+.5) / TOPY=16*(r+.5)；
  但全盘有 20 行，视图会整体下滚 offset ∈ 0..8（= 20-12）。
  以答案盘逐行 classify 匹配可唯一确定 offset（实测 rate=1.000）。
* 红框 = 下屏 7×7 视口在【当前上屏视图】中的位置 (r_view,c_view)。
  全局视口起点 r0 = offset + r_view；c0 = c_view（横向 12 列不滚动，同 11×11）。
  ▼ 序列可落在 r0 = 0/2/5/7/10/13，到底 13 = 20-7。
* 下屏 7×7 视口 + 1~9 数字键盘布局与 11×11 完全相同，Y.fill_cell / R.num_xy 可直接复用
  （实测试填 3/3 命中）。

=== 录制策略：动态视口扫描（不依赖精确滚动步数）===
纵向从 r0=0 单向按 ▼ 推到 r0=13，每个 r0 下横向从 c0=0 按 ▶ 推到 c0>=5；
每到一处读实际 (r0,c0)，把落在 [r0,r0+6]×[c0,c0+6] 内的未填答案格填掉，
按上屏 offset 平移判读补点。20 行 × 12 列全覆盖，无需精确到达指定视口。
"""
import os
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
import scroll_win as SW

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
REF_PATH = os.path.join(HERE, 'ref_11x19.png')   # 上屏「11×19」尺寸文字模板
MASU_PATH = os.path.join(HERE, 'ref_masu_11x19.png')
OUTDIR = '/workspace/Vol.4_ふつう11x19录播'


def masu_ok(im):
    """选关层上屏固定 UI「マス：11×19」文字条校验（进错档硬判据）。

    点中关号后、按 A 进关前，上屏预览会显示该关的尺寸文字条：
    11×19 档为「マス：11×19」，11×11 档为「マス：11×11」。
    实测同档不同关 xor=0.000、跨档 xor=0.073，是唯一能 100% 区分档位
    的判据 —— size_ok() 与 view_off rate 只比斜线格布局，11×11 与 11×19
    前 12 行布局相似时会同时给出 1.000，拦不住「滚动错位落到第47問」。
    """
    ref = np.array(Image.open(MASU_PATH).convert('L')) < 130
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
        print('  [%s] !! 选中关预览非 11×19（滚动错位进错档），拒绝进关' % tag,
              flush=True)
        return False
    return True


F.select_level_11 = _select_level_11x19

LV0 = 109                # 第 k 問 → lv = LV0 + k
ROWS, COLS = 20, 12      # 答案盘形状（含提示行列）
TOPX = lambda c: int(63 + 16 * (c + .5))
TOPY = lambda r: int(16 * (r + .5))
LEAD_IN = 2.0
TARGET_TOTAL = 60.0
HOLD_MIN, HOLD_MAX = 5.0, 15.0


def load_disk(lv):
    rep = json.load(open(DATA, encoding='utf-8'))
    body = bytes.fromhex(rep['levels'][lv]['body_hex'])
    disk = body[-(ROWS * COLS):]
    return disk


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
            for c in range(12):
                if R.classify(im, TOPX(c), TOPY(r)) != 1:   # 只取亮格锚点
                    continue
                jd += 1
                if disk[(r + off) * COLS + c]:
                    ok += 1
        if best is None or ok > best[0]:
            best = (ok, off, jd)
    return best[1], best[0] / max(1, best[2])


def origin(im, disk):
    """当前下屏视口的全局起点 (r0,c0) + 上屏视图偏移 off。"""
    o = F.red_origin_11(im)
    if o is None:
        return None
    off, rate = view_off(im, disk)
    return (off + o[0], o[1]), off, o, rate


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
    ref = np.array(Image.open(REF_PATH).convert('L')) < 130
    q = np.array(im.convert('L'))[90:110, 8:46] < 130
    return (ref ^ q).mean() < 0.02


def real_result(im):
    """真正的 ★★★★★ 结算页（排除存档画面 / 选关层误判）。

    结算页与选关层的 _blue_bottom 都 >0.4；结算页关号按钮行几乎无红色
    （_sel_red ≤7），选关层已通关关号整片红（>1000），据此可区分。
    """
    return (R._blue_bottom(im) > 0.4
            and not save_screen(im)
            and R._sel_red(im) < 60)


def arrow(name):
    ds.click_touch(*R.V8_ARROW[name], wait=0.7)
    time.sleep(0.15)


def c0_now():
    o = F.red_origin_11(ds.shot())
    return o[1] if o else None


def to_c0(target):
    for _ in range(14):
        c = c0_now()
        if c is None:
            time.sleep(0.3)
            continue
        if c == target:
            return True
        arrow('R' if target > c else 'L')
    return False


def to_top(disk):
    for _ in range(16):
        q = origin(ds.shot(), disk)
        if q and q[0][0] == 0:
            return True
        arrow('U')
    return False


# 6 窗口扫描用的闭环滚动器（跨关保留速率学习；见 scroll_win / RESEARCH 12.17）
SC = SW.Scroller(lambda disk: origin(ds.shot(), disk), ROWS, COLS)


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
        Y.fill_cell(r - r0, c - c0, v)
    # filled 记录「已按几何点击过的格」，单调收敛到全盘；真正填对与否交给
    # real_result()（结算页），点错/漏点由补漏轮补、仍不 CLEAR 则 FAIL 重录。
    filled |= {(r, c) for r, c, v in todo}


def sweep(cells, disk, tag, filled0=None):
    """6 窗口蛇形扫描（行 1/8/13 × 列 0/5，5 次换屏；实现见 scroll_win.sweep_windows）。

    === 12.18：从「单向 ▼ 逐段 + 横向往返」换成最少窗口（同 13×21）===
    答案盘 20 行 × 12 列，首行/首列是提示行列，答案格 r=1..19、c=1..11。
    行窗口从 r=1 起每 7 行一个（1-7 / 8-14 / 13-19，最后钳到 rows-7=13），
    列窗口 0-6 / 5-11，合起来 6 个窗口 5 次换屏。旧版纵向每次 ▼ 只滚 2 行，
    要 7~8 段 × 每段 2~3 个横向位置 ≈ 16 个视口。视口位置仍全部实读，
    不依赖步长精确值；填不完整的格由 record() 的补漏轮兜底。
    """
    return SW.sweep_windows(
        cells, SC, disk, ROWS, COLS,
        lambda todo, r0, c0, filled: fill_view(todo, r0, c0, disk, tag, filled),
        tag, filled0, row_start=0)


def record(k):
    lv = LV0 + k
    tag = '%03d' % k
    disk = load_disk(lv)
    cells = [(r, c, disk[r * COLS + c])
             for r in range(ROWS) for c in range(COLS) if disk[r * COLS + c]]
    out = os.path.join(OUTDIR, 'Vol.4_数和_ふつう11x19_%s_256x384.mp4' % tag)
    os.makedirs(OUTDIR, exist_ok=True)
    print('\n=== ふつう11x19 %s (lv%d, %d行x%d列, %d 个数字格) ===' %
          (tag, lv, ROWS, COLS, len(cells)), flush=True)

    # 回选关层 → 确定性滚动进关（S 模板已弃用，见模块头 _scroll_to_show_11x19）
    R.ensure_select('boot')
    time.sleep(1.2)                    # 通关/存档刚回选关层时动画未稳，触摸易被吞
    F.force_top._tmpl = None
    if not F.enter_level_11(k, disk[:144], tag):
        return False, '进关失败(盘面未就绪)'
    if not F.wait_input_ready(tag):
        return False, 'START演出未结束'
    # 进错关硬校验：滚动错位会落到 11×11 档关卡，空白盘面的 classify/match
    # 判据都会给出 1.000 拦不住，尺寸文字是唯一可靠证据。ffmpeg 尚未启动，
    # 直接失败让驱动快速重试（避免拿 20 行答案盘去填 12 行盘面死循环）。
    if not size_ok(ds.shot()):
        return False, '进关盘面尺寸不符(非11×19, 疑似滚动错位进错关)'
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
        ds.save(last_result, '/tmp/fu11x19_end_%s.png' % tag)
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
    k = int(sys.argv[1]) if len(sys.argv) > 1 else 61
    ok, msg = record(k)
    print('\n=> ふつう11x19 %03d %s %s' % (k, 'OK' if ok else 'FAIL', msg), flush=True)


if __name__ == '__main__':
    main()
