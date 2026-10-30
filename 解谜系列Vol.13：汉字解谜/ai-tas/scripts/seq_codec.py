#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""动作序列的 ASCII 紧凑编码（2026-10-15，§S39–§S43）。

**动机（用户）**：「json 没那么大。每个操作都可以仅用一个字符，甚至 ascii 字符表示。」
→ §S40「这个 json 只需要存储动作序列」→ §S41/§S42 单字符化 page/arrow/hop
→ §S43 去掉 m/k/b 的逗号与步间分隔符、black→X、page→P/Q。

格式：整关 seq 编为**单个字符串**，步间**无分隔符**（每步定长自限定），
每步 = kind 单字符 + 定长参数（字符集全小写，仅 page 用大写 P/Q、black 用 X 便于辨识）：

    kind   编码                      定长   例          解码后（与旧 4 元素 tuple 同构）
    map    `m<行><列><徽章2位>`       5     `m0101`      ('map', 0, 1, '1')   # 徽章1→"01"定长，解码规整回 '1'
    kanji  `k<行><列>`                3     `k02`        ('kanji', 0, 2, '')
    arrow  `^`上/`v`下/`<`左/`>`右     1     `>`          ('arrow', ARROW['R']…, '缩略图→')
    hop    `L`(L肩,q)/`R`(R肩,w)       1     `R`          ('hop', 'w', 0, '跳跃R')
    black  `X`（涂黑按钮，坐标恒定）    1     `X`          ('black', 111, 168, '黒マス')
    page   `P`(下一页)/`Q`(上一页)     1     `P`          ('page', LIST_NEXT_D, 'リスト次') / ('page', LIST_PREV_D, 'リスト前')

**为什么能去掉分隔符**：每种 kind 长度固定（m=5、k=3、其余=1），解码时从左到右
按 kind 取定长切片即可，无需步间分隔符。徽章恒为 2 位定长（范围 1–99，数据实测
max=99）；行/列在数据中 map 为 0–3、kanji 为 0–7/0–5，均单位数，故各占 1 位。
arrow 只存方向字符（坐标由 `plan_fast.ARROW` 现查还原）；page 由 P/Q 方向还原；
black 按钮坐标恒定（lr_plan.BLACK_XY，实机标定 111,168），只存标记 `X`。
不可编码的步（模式2 beam 的 `[组号,[x,y]]`）原样保留，此时 `encode_seq` 返回原 list、
`decode_seq` 原样返回。

**转码只在 `plan_store` 落盘/读盘时发生**——所有生产方（plan_fast / lr_plan /
precompute / plan_by_rec）与消费方（do_fill / order 提取）继续用 4 元素 tuple，
无需感知编码。体积：0.81 MB → 0.26 MB（§S39 编码）→ 0.20 MB（§S40 只存 seq）
→ 207,634 B（§S41 p/q）→ 198,493 B（§S42 arrow/hop）→ **119,153 B（§S43 去逗号
+ 去步分隔符 + black→X + page→P/Q；198,493 → 119,153，−40%）**。
"""
import os

KIND_CHAR = {'map': 'm', 'kanji': 'k', 'arrow': '^v<>',
             'hop': 'LR', 'black': 'X', 'page': 'PQ'}
_ENCODABLE = frozenset(KIND_CHAR)

# 涂黑按钮坐标（与 lr_plan.BLACK_XY 同源；实机标定 2026-10-15：底屏相对 (111,168)）。
# 数据中 880 条 black 步坐标恒为 (111,168)，故编码只存标记 `X`，解码回此常量。
_BLACK_XY = (int(os.environ.get('AI_TAS_BLACK_X', 111)),
             int(os.environ.get('AI_TAS_BLACK_Y', 168)))

# 每步定长（字符数）：m=5、k=3、M=2、K=3，其余 kind 均为 1。解码据此从左到右切片。
# ★ §S45（2026-10-15）：最终落盘格式用大写 M/K（M<x> 2 字符、K<row><col> 3 字符，
#   徽章不落盘、map 行列压成 1 位 hex），与 convert_plans_mk 产出、以及本模块编码同口径。
_STEP_LEN = {'m': 5, 'k': 3, 'M': 2, 'K': 3}


def _arrow_tables():
    """(坐标→方向, 方向→坐标) —— 延迟 import，与执行侧同源（ARROW 支持环境变量覆盖）。"""
    import plan_fast as P
    fwd = {v: k for k, v in P.ARROW.items()}
    return fwd, P.ARROW


def encode_step(step):
    """4 元素 (kind,a,b,note) → 定长编码字符串；不可编码返回 None。

    ★ §S45（2026-10-15）：map → `M<x>`（x=row*4+col 小写 hex、徽章不落盘）、
    kanji → `K<row><col>`，与最终落盘格式一致（convert_plans_mk 同口径）。
    """
    if not isinstance(step, (tuple, list)) or len(step) != 4:
        return None
    kind, a, b, note = step
    if kind not in _ENCODABLE:
        return None
    if kind == 'map':
        # ★ §S45：行/列 ∈ 0..3 → x = row*4+col ∈ 0..f，压成 1 位小写 hex；徽章不落盘
        x = a * 4 + b
        if not (0 <= x <= 15):
            return None
        return 'M%x' % x
    if kind == 'kanji':
        return 'K%01d%01d' % (a, b)
    if kind == 'arrow':
        fwd, _ = _arrow_tables()
        d = fwd.get((a, b))
        # 缩略图箭头用图形字符单字符表示：^上 v下 <左 >右（坐标恒定，查表还原）
        return {'U': '^', 'D': 'v', 'L': '<', 'R': '>'}.get(d, 'a%d,%d' % (a, b))
    if kind == 'hop':
        # 肩键用 L/R 单字符表示：w=R 肩键(前进) q=L 肩键(后退)
        return {'w': 'R', 'q': 'L'}.get(a, 'h%s' % a)
    if kind == 'black':
        return 'X'                       # 涂黑按钮坐标恒定，只存标记
    if kind == 'page':
        import plan_fast as P
        # 翻页按钮坐标恒定（LIST_NEXT_D / LIST_PREV_D），存方向字符（大写便于辨识）
        if (a, b) == (P.LIST_NEXT_D[0], P.LIST_NEXT_D[1]):
            return 'P'                   # 下一页
        if (a, b) == (P.LIST_PREV_D[0], P.LIST_PREV_D[1]):
            return 'Q'                   # 上一页
        return 'p%d,%d' % (a, b)         # 未知坐标，降级保坐标不丢信息
    return None


def decode_step(s):
    """单个定长编码步 → 4 元素 tuple (kind,a,b,note)。s 不含步间分隔符。

    ★ §S45：M<x>（x=row*4+col 小写 hex）→ ('map', row, col, '')；徽章不落盘，
    执行侧按 rec 的 badge_cells 现场反查。K<row><col> → ('kanji', row, col, '')。
    """
    c, rest = s[0], s[1:]
    if c == 'm':
        # 定长 5：m + 行(1) + 列(1) + 徽章(2)；徽章规整回整数串（'01'→'1'）
        return ('map', int(rest[0]), int(rest[1]), str(int(rest[2:4])))
    if c == 'M':
        # ★ §S45 定长 2：M + hex(x)；x = 行*4+列
        x = int(rest[0], 16)
        return ('map', x // 4, x % 4, '')
    if c == 'k':
        # 定长 3：k + 行(1) + 列(1)
        return ('kanji', int(rest[0]), int(rest[1]), '')
    if c == 'K':
        # ★ §S45 定长 3：K + 行(1) + 列(1)
        return ('kanji', int(rest[0]), int(rest[1]), '')
    if c in ('^', 'v', '<', '>'):                          # 缩略图箭头（单字符）
        sym = {'^': 'U', 'v': 'D', '<': 'L', '>': 'R'}[c]
        _, ARROW = _arrow_tables()
        x, y = ARROW[sym]
        glyph = {'L': '←', 'R': '→', 'U': '↑', 'D': '↓'}[sym]
        return ('arrow', x, y, '缩略图%s' % glyph)
    if c in ('L', 'R'):                                    # 肩键（单字符）L=L肩(q) R=R肩(w)
        rec = 'q' if c == 'L' else 'w'
        return ('hop', rec, 0, '跳跃%s' % ('L' if c == 'L' else 'R'))
    if c == 'X':                                           # 涂黑按钮：坐标恒定
        return ('black', _BLACK_XY[0], _BLACK_XY[1], '黒マス')
    if c == 'P':
        import plan_fast as P
        return ('page', P.LIST_NEXT_D[0], P.LIST_NEXT_D[1], 'リスト次')   # 下一页（大写）
    if c == 'Q':
        import plan_fast as P
        return ('page', P.LIST_PREV_D[0], P.LIST_PREV_D[1], 'リスト前')   # 上一页（大写）
    raise ValueError('无法解码的步: %r' % s)


def encode_seq(seq):
    """tuple list → 定长字符串直接拼接（无步间分隔符）；含不可编码步时原样返回 list。"""
    if not isinstance(seq, (list, tuple)):
        return seq
    parts = []
    for step in seq:
        e = encode_step(step)
        if e is None:
            return list(seq)                # beam 等混合格式：整体放弃编码
        parts.append(e)
    return ''.join(parts)


def decode_seq(s):
    """定长字符串 → tuple list；非字符串（beam 旧格式）原样返回。

    每步定长（m=5/k=3/其余=1），从左到右按 kind 取定长切片，无需分隔符。
    """
    if not isinstance(s, str):
        return s
    out = []
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        ln = _STEP_LEN.get(c, 1)
        if c in ('m', 'k', 'M', 'K', '^', 'v', '<', '>', 'L', 'R', 'X', 'P', 'Q'):
            out.append(decode_step(s[i:i + ln]))
            i += ln
        else:
            raise ValueError('无法解码的步: %r (at %d)' % (s, i))
    return out


def encode_plan(plan):
    """落盘前：dict 的 seq 编码（其余字段不动）。不可编码则原样。"""
    if not isinstance(plan, dict):
        return plan
    seq = plan.get('seq')
    if not isinstance(seq, (list, tuple)):
        return plan
    enc = encode_seq(seq)
    if enc is seq or isinstance(enc, list) and enc == list(seq):
        return plan
    out = dict(plan)
    out['seq'] = enc
    return out


def seq_stats(seq):
    """从解码后的 seq 现算执行统计（§S40：仓库只存 seq，统计一律现算）。

    返回 {steps, n_touch, n_arrow, n_hop, n_page, n_black, arrows}——
    与旧存储字段同义（n_touch = map+kanji 步数，arrows = 方向计数）。
    方向取自 plan_fast.ARROW 反查（与解码同源），查不到退回 note 字形。
    """
    st = {'steps': 0, 'n_touch': 0, 'n_arrow': 0, 'n_hop': 0,
          'n_page': 0, 'n_black': 0, 'arrows': {'R': 0, 'L': 0, 'U': 0, 'D': 0}}
    fwd = None
    for s in seq:
        if not isinstance(s, (list, tuple)) or len(s) != 4:
            continue                      # beam 的 [k,[r,c]] 不参与（另有权衡）
        st['steps'] += 1
        kind, a, b, note = s
        if kind in ('map', 'kanji'):
            st['n_touch'] += 1
        elif kind == 'arrow':
            st['n_arrow'] += 1
            if fwd is None:
                try:
                    fwd, _ = _arrow_tables()
                except Exception:
                    fwd = {}
            d = fwd.get((a, b))
            if d is None:                 # 降级坐标模式：退回 note 字形
                d = {'←': 'L', '→': 'R', '↑': 'U', '↓': 'D'}.get(
                    next((ch for ch in str(note) if ch in '←→↑↓'), ''), None)
            if d:
                st['arrows'][d] += 1
        elif kind == 'hop':
            st['n_hop'] += 1
        elif kind == 'page':
            st['n_page'] += 1
        elif kind == 'black':
            st['n_black'] += 1
    return st
