#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""鲁棒解析器 v2：从 datasheet.bin 解析《漢字パズル Vol.13》谜题记录。

设计依据 PITFALLS.md §E / §J：
- 记录结构：
    [rec_len u16][cnt u16][cnt 条目: 汉字SJIS**低字节在前** + (r,c)坐标若干 + FF FF]
    ... 词区(81 40 全角句号分隔) ... 徽章区(FF分隔数字，含 2 字节 00 00 头)
    ... [count 1B][count*2 汉字 SJIS **高字节在前**][CC...终止符]
- 字节序：条目区汉字 = LE（人=`77 8a`）；末尾汉字表 = BE 标准 SJIS（人=`8a 77`）。
- 终止符：可能在记录末尾被截断，**不能** rfind(CC CC CC)。
  正确做法：在记录末尾 512 字节内扫描「count∈1..64 且其后 count*2 字节全部可解码为
  单个 SJIS 汉字」的候选块，取**最靠后**者。
- 徽章区：紧邻汉字表 count 字节之前，实际起点比 count 位置更靠左（弹性回退 ~160 字节），
  开头有 2 字节 00 00 前导需剥离；数字 0=提示格，>=1=待填徽章号。
- 对齐：坐标按列优先 `c*8+r` 排序后与徽章区顺序一一对应。
- 关卡号 ↔ 记录号：やさしい No.N 恒对应记录 (N-1)。No.01~15 = rec0~14（8x8 小盘），
  No.16~35 = rec15~34（15x15 大盘）。

输出：solve(idx) 返回 dict 或 None，含 fill(徽章->汉字)、kanji_order(リスト字序)、
badges、entries 等，供 plan_fast / fill_fast_any 使用。
"""
import os
import struct

DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         'validation', 'datasheet.bin')
NREC = 300

# 字节序：条目区汉字 = 低字节在前（LE）；汉字表 = 高字节在前（BE）
def _sjis_le(code):
    """条目区汉字：u16 低字节在前 → 组装为 BE 后按 cp932 解码。"""
    try:
        return struct.pack('>H', code).decode('cp932')
    except Exception:
        return '?'


def _sjis_be(code):
    """汉字表汉字：已是 BE 标准 SJIS。"""
    try:
        return struct.pack('>H', code).decode('cp932')
    except Exception:
        return '?'


def _load_data():
    with open(DATA_PATH, 'rb') as f:
        return f.read()


DATA = _load_data()
OFFS = list(struct.unpack_from('<%dI' % NREC, DATA, 0))
OFFS.append(len(DATA))


def get_record(idx):
    """返回第 idx 条记录的原始字节。"""
    if not (0 <= idx < NREC):
        return None
    # ★ 偏移表恰好 300 项；最后一条记录（rec299）无尾偏移，延伸到文件尾
    end = OFFS[idx + 1] if idx + 1 < NREC else len(DATA)
    return DATA[OFFS[idx]:end]


def parse_entries(rec):
    """解析条目区。

    返回 (entries, end_pos)：
      entries: [(汉字str, [(r,c),...])]
      end_pos: 条目区结束位置（词区开始）
    """
    rec_len, cnt = struct.unpack_from('<HH', rec, 0)
    i = 4
    entries = []
    for _ in range(cnt):
        code = struct.unpack_from('<H', rec, i)[0]
        i += 2
        ks = _sjis_le(code)
        coords = []
        while i + 1 < len(rec) and rec[i:i + 2] != b'\xff\xff':
            coords.append((rec[i], rec[i + 1]))
            i += 2
        i += 2  # skip FF FF
        entries.append((ks, coords))
    return entries, i


def find_table(rec):
    """在记录末尾扫描汉字表。

    返回 (kanji_list, count_pos, table_pos) 或 None。
    汉字表布局： [count 1B][count*2 字节 SJIS 高字节在前][CC...]
    count 可能 1..64；终止符可能被截断。在末尾 512 字节内扫描。
    """
    n = len(rec)
    lo = max(0, n - 1024)
    # 从后往前扫 count 候选
    # 上限 128（2026-10-11 放宽）：25x20 巨盘（rec55~159）汉字表达 74 字，
    # 旧上限 64 会把它们全部判非法 —— 这正是 105 条巨盘解析失败的**唯一根因**。
    # ★ 2026-10-12：改为收集**全部**候选、取 count 最大者（而非最靠后者）。
    #   个别结构异常记录（rec119/157/238/271）在真表之前多出一段「更短伪表」
    #   （count=64/67 等，与真表共享同一 CC 尾），旧代码取最靠后者 = 伪表 → 表偏短
    #   → 徽章→汉字映射越界。取最长者即真表。全部 300 条中仅这 4 条有多个候选，
    #   其余 296 条单一候选，本改动对其零影响。
    best = None
    best_cnt = 0
    for p in range(n - 1, lo - 1, -1):
        cnt = rec[p]
        if not (1 <= cnt <= 128):
            continue
        end = p + 1 + cnt * 2
        if end > n:
            continue
        # 剩余部分必须全是 CC（终止符）或空
        tail = rec[end:]
        if tail and any(b != 0xCC for b in tail):
            continue
        # count*2 字节全部可解码为单个 SJIS 汉字
        ok = True
        kanji = []
        for q in range(p + 1, end, 2):
            code = (rec[q] << 8) | rec[q + 1]
            try:
                ch = struct.pack('>H', code).decode('cp932')
            except Exception:
                ok = False
                break
            if not ch or len(ch) != 1:
                ok = False
                break
            kanji.append(ch)
        if ok and kanji:
            if cnt > best_cnt:
                best = (kanji, p, p + 1)
                best_cnt = cnt
    if best is not None:
        return best
    return None


def parse_badges(rec, entries, count_pos, N=None):
    """从汉字表 count 字节之前解析徽章区。

    徽章区布局： [00 00 头][数字 0..n 以 FF 分隔][...] 直到 count 字节。
    数字 0=提示格（已给汉字），>=1=待填徽章号；FF 是数字间的分隔符。
    返回 (badges_list, start_pos) 或 None。

    判界依据（PITFALLS §E2.3 原文）：**取使「非 0xff 字节数 == 格子总数」的那个起点**。

    ⚠️ 2026-10-11 修正（25x20 巨盘 rec55~159 全灭的真因）：
    旧实现用「遇 >=0x40 的非 FF 字节即停」的启发式判界，其隐含前提是
    **徽章号恒 < 0x40(64)**。这对 やさしい（徽章 <=40）成立，但巨盘汉字表达
    74 字、徽章号可到 **73**，64~73 这些字节 >=0x40 被误判成「词区边界」，
    导致徽章区被提前截断（rec55 只解出 27 个数字，实需 346 个）→ 全盘解析失败。
    现改为按 §E2.3 的**格子数反推**判界，与徽章号大小无关，彻底根治。

    N: 格子总数（条目区唯一坐标数）。给 None 时退回旧启发式（不推荐）。
    """
    if N is not None:
        # 从 count 字节往前扫起点，取使「非 FF 字节数 == N」的最靠后者。
        # 回退窗口 2500 字节：巨盘徽章区实测 500 字节，留足余量。
        #
        # ★ 2026-10-15：新增「原样」变体（不剥离 00 头）。真因：徽章区**首个格子本身
        #   就可能是提示格（徽章值 0）**，此 0 与 §J2.3 说的「00 头」在字节上无法区分。
        #   旧实现无条件剥离最多 2 个前导 0x00，于是把这类记录的合法首值 0 一并吃掉，
        #   非 FF 计数少 1~2 → 定位失败（模式3 13 条 + 未发掘记录 6 条，共 19 条）。
        #   修法：每个起点先试「原样」，再试「剥零」；两者在每个起点互斥（计数相差
        #   被剥掉的 0 个数），故不会引入歧义。全库 300 条实测：新增变体**只**在原本
        #   失败的 19 条上命中，对其余 281 条（含已解 236 条）结果完全不变。
        for start in range(count_pos - 1, max(0, count_pos - 2500), -1):
            # 变体 A：原样（首值可能就是 0=提示格）
            nums = [b for b in rec[start:count_pos] if b != 0xFF]
            if len(nums) == N:
                return nums, start
            # 变体 B：剥离最多 2 字节 00 头（PITFALLS §J2.3）
            s = start
            n00 = 0
            while s < count_pos and rec[s] == 0x00 and n00 < 2:
                s += 1
                n00 += 1
            if s > start:
                nums = [b for b in rec[s:count_pos] if b != 0xFF]
                if len(nums) == N:
                    return nums, s
        return None

    # —— 旧启发式（仅 N 未知时兜底）——
    p = count_pos - 1
    while p > 0:
        b = rec[p]
        if b != 0xFF and b >= 0x40:
            break
        p -= 1
    start = p + 1
    # 剥离开头 2 字节 00 00 头（PITFALLS §J2.3）
    s = start
    n00 = 0
    while s < count_pos and rec[s] == 0x00:
        s += 1
        n00 += 1
    if n00 >= 2:
        start += 2
    elif n00 == 1:
        start += 1
    if start >= count_pos:
        return None
    badge_all = [b for b in rec[start:count_pos] if b != 0xFF]
    if not badge_all:
        return None
    return badge_all, start


def _align_fallback(rec, entries, uniq, N, GRID_R, GRID_C, count_pos, kanji_order):
    """徽章区起点判定失败时的兜底对齐（仅个别结构异常记录触发）。

    背景（2026-10-12）：绝大多数记录可用 parse_badges 的「非 FF 字节数 == N」定位
    徽章区起点；但 rec119（むずかしい No.05）、rec238（No.49）的徽章区起点会偏几字节，
    导致对齐失败（解出 max 值 >100 明显越界的徽章号）。对这两条，真值区窗口在
    count_pos-524 .. count_pos-476 内、且需对称裁剪若干字节。此处在该范围内穷举
    (start, 对称裁剪 t, 两种矩形排序)，取首个满足「词内徽章一致 + 徽章号 1..max 连续」者。

    ★ 只在 solve() 标准路径**未对齐**（best is None）时调用，故对已可解的 250+ 记录零影响。
    验证：rec119 解回 可填格子数=275，与实机 No.05 的 口の数 完全一致。
    """
    ORDERS = [
        ('c*GRID_C+r', lambda p: p[1] * GRID_C + p[0]),
        ('c*GRID_R+r', lambda p: p[1] * GRID_R + p[0]),
    ]
    for start in range(count_pos - 524, count_pos - 476):
        if start < 0:
            continue
        s = start
        n00 = 0
        while s < count_pos and rec[s] == 0x00 and n00 < 2:
            s += 1
            n00 += 1
        nums = [b for b in rec[s:count_pos] if b != 0xFF]
        if len(nums) < N:
            continue
        for name, order in ORDERS:
            u = sorted(uniq, key=order)
            c2i = {c: k for k, c in enumerate(u)}
            idxs = [[c2i[c] for c in cs] for _, cs in entries]
            for t in range(0, 15):
                if len(nums) - 2 * t != N:
                    continue
                bs = nums[t:len(nums) - t]
                multi = 0
                b2k = {}
                for e, (ks, _) in enumerate(entries):
                    bset = set(bs[i] for i in idxs[e])
                    if len(bset) != 1:
                        multi += 1
                    else:
                        b2k[list(bset)[0]] = ks
                used = sorted(b for b in b2k if b >= 1)
                exp = list(range(1, max(used) + 1)) if used else []
                if multi == 0 and used == exp and len(used) >= 5:
                    return (name, t, t, b2k, kanji_order, bs)
    return None


def solve(idx, verbose=False):
    """解析第 idx 条记录，返回 dict 或 None。

    返回:
      fill: {徽章号: 汉字} （仅 >=1 的徽章）
      kanji_order: リスト面板汉字顺序（含干扰字）
      nbadge: 徽章数
      fillable: 可填汉字列表（不含干扰字）
      entries: 原始条目
      badges: 徽章数组
      grid: 非墙格列表
    """
    rec = get_record(idx)
    if rec is None:
        return None
    entries, _ = parse_entries(rec)
    t = find_table(rec)
    if t is None:
        return None
    kanji_order, count_pos, table_pos = t

    # 坐标对齐：条目区所有坐标（先算格子总数 N，徽章区判界要用）
    allc = [c for _, cs in entries for c in cs]
    uniq = sorted(set(allc))
    N = len(uniq)
    # 动态确定网格尺寸（小盘 8x8、大盘 15x15、巨盘 25x20）：坐标范围 + 1
    max_r = max(c[0] for c in uniq)
    max_c = max(c[1] for c in uniq)
    GRID_R = max_r + 1
    GRID_C = max_c + 1

    # 徽章区：按「非 FF 字节数 == N」反推起点（§E2.3），与徽章号大小无关
    got = parse_badges(rec, entries, count_pos, N)
    if not got:
        # 兜底：N 反推失败时退回旧启发式（徽章号 <0x40 的小盘仍可能命中）
        for tt in range(count_pos, max(0, count_pos - 200), -1):
            got = parse_badges(rec, entries, tt)
            if got:
                break
    if not got:
        return None
    badges, _ = got

    # 尝试多种对齐方式，找使每个词内徽章号一致且徽章号连续 1..max 的方式
    ORDERINGS = [
        ('c*GRID_C+r', lambda p: p[1] * GRID_C + p[0]),
        # 2026-10-11 新增：矩形盘（25x20 巨盘 rec55~159）的正确对齐。
        # 方阵（8x8 / 15x15）下 GRID_R == GRID_C，本式与上式等价、不会先命中，
        # 故对已验证的 やさしい 35 关零影响；矩形盘下只有它能让
        # 「词内徽章号一致(multi=0) 且 徽章号 1..max 连续」成立（rec55 实测 multi=0、max=73）。
        ('c*GRID_R+r', lambda p: p[1] * GRID_R + p[0]),
        ('r*GRID_C+c', lambda p: p[0] * GRID_C + p[1]),
        ('r*GRID_C+(GRID_C-1-c)', lambda p: p[0] * GRID_C + (GRID_C - 1 - p[1])),
        ('(GRID_R-1-r)*GRID_C+c', lambda p: (GRID_R - 1 - p[0]) * GRID_C + p[1]),
        ('c*GRID_C+(GRID_R-1-r)', lambda p: p[1] * GRID_C + (GRID_R - 1 - p[0])),
        ('rev r*GRID_C+c', lambda p: -(p[0] * GRID_C + p[1])),
    ]

    best = None
    for tl in range(0, 8):
        for tr in range(0, 8):
            bs = badges[tl:len(badges) - tr] if tr else badges[tl:]
            if len(bs) != N:
                continue
            for name, order in ORDERINGS:
                u = sorted(uniq, key=order)
                c2i = {c: k for k, c in enumerate(u)}
                multi = 0
                b2k = {}
                for ks, cs in entries:
                    bset = set(bs[c2i[c]] for c in cs)
                    if len(bset) != 1:
                        multi += 1
                    else:
                        b2k[list(bset)[0]] = ks
                used = sorted(b for b in b2k if b >= 1)
                exp = list(range(1, max(used) + 1)) if used else []
                if multi == 0 and used == exp:
                    best = (name, tl, tr, b2k, kanji_order, badges)
                    break
            if best:
                break
        if best:
            break
    if not best:
        # 兜底：结构异常记录（rec119/238）的徽章区起点定位（仅失败时触发）
        best = _align_fallback(rec, entries, uniq, N, GRID_R, GRID_C,
                               count_pos, kanji_order)
    if not best:
        return None

    name, tl, tr, b2k, kanji_order, badges = best
    fillable = [c for c in kanji_order if c in set(b2k.values())]

    # 构建 徽章号 -> 棋盘坐标列表（供缩略图选格 / 光标导航使用）
    # 对齐后的坐标序列 u 与 badges 顺序一一对应（屏幕逐行非墙格顺序）
    u = sorted(uniq, key=dict(ORDERINGS)[name])
    badge_cells = {}
    for k, coord in enumerate(u):
        b = badges[k]
        if b >= 1:
            badge_cells.setdefault(b, []).append(coord)

    return {
        'idx': idx,
        'align': name,
        'trim': (tl, tr),
        'fill': {b: k for b, k in b2k.items() if b >= 1},
        'kanji_order': kanji_order,
        'nbadge': len([b for b in b2k if b >= 1]),
        'fillable': fillable,
        'entries': entries,
        'badges': badges,
        'grid': uniq,
        'badge_cells': badge_cells,
    }


def scan_all():
    """列出所有可解记录。"""
    res = []
    for idx in range(NREC):
        r = solve(idx, verbose=False)
        if r:
            res.append(r)
    return res


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        idx = int(sys.argv[1])
        r = solve(idx)
        if r:
            print('记录%d 对齐=%s trim=%s' % (idx, r['align'], r['trim']))
            print('  徽章数   : %d' % r['nbadge'])
            print('  徽章->汉字: %s' % {k: r['fill'][k] for k in sorted(r['fill'])})
            print('  リスト字序: %s' % ''.join(r['kanji_order']))
        else:
            print('记录%d 无法解析' % idx)
    else:
        res = scan_all()
        print('=== 可解记录 %d 条 ===' % len(res))
        k = 0
        for r in res:
            k += 1
            print('No.%02d <- 记录%-4d 徽章%-3d %s'
                  % (k, r['idx'], r['nbadge'], ''.join(r['fillable'])))