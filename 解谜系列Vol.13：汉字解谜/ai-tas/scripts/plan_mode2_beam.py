#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""plan_mode2_beam：模式2（ひりどりナンクロ／词语螺旋接龙）beam search 动作规划器。

与 runner v5（run_mode2_easy1_fast.py）**同构**的离线规划器：在 nav 之前算好
「组序 + 每组目标格」，游戏内只做闭环执行（每步读蓝框验窗口、橙框判组），
因此规划的动作数是期望值，实测只多不少（丢键自纠、免点击实时判定）。

模型（2026-10-14 逐帧标定，PITFALLS §S28/S29 + cal_blue/probe_* 系列）：
  * press(dir)：窗口原点朝 dir 滚 1 格（夹取 [0, size-4]），光标 board 坐标恒 +1；
  * click(槽)：光标跳到 原点+槽，窗口不动；
  * 点候选字：绑定到**光标当前所在组**（同槽号整组联动），每组只点一次；
  * 光标在某组格上时，该组所有在窗格画同色橙框 ⇒ **行走中光标落进目标组即免点击**
    （runner 用橙框检测实时判定，本规划器按同一口径模拟，故计数不保守）。

动作计数口径：方向键 + 点击 + 点字(每组1) + 翻页(候选>48 字时)。
用法：
  python3 plan_mode2_beam.py [rec_idx ...]     # 打印规划（默认 260 250 251）
  from plan_mode2_beam import beam_plan        # 返回 (seq, stats)
"""
import hashlib
import os
import struct
import sys
import time

DATA = '/workspace/Kanji/validation/datasheet.bin'
CANDS_PER_PAGE = 48          # 列表 6 列 × 8 行（2026-10-14 实测）
# §S56：翻页的时间权重。一次翻页 = 点箭头 tap(≈0.06s) + PAGE_TURN_WAIT(0.15s) ≈ 0.21s，
#   而单次箭头/点击 press ≈ 0.06s ⇒ 翻页比走位贵 ~3.5 倍。旧成本把翻页与走位等权(+1)，
#   导致 beam 随便用翻页换走位（rec250 15×15 竟翻 6 次，2 页候选本应 ≤1 次，白耗 ~1s）。
#   改为时间加权后 beam 会主动聚类同页组、把翻页压到最少（用户要求「每关至多一次翻页」）。
TURN_W = float(os.environ.get('AI_TAS_TURN_W', '3.0'))


def load_plan(idx):
    """从 datasheet 读解答表：组序按槽号，附带候选表索引 li 与分组格坐标。"""
    D = open(DATA, 'rb').read()
    off = list(struct.unpack_from('<300I', D, 0))
    # ★ 偏移表恰好 300 项（1200B）；最后一条记录（rec299）无尾偏移，延伸到文件尾
    rec = D[off[idx]:off[idx + 1] if idx + 1 < len(off) else len(D)]
    rl, cnt = struct.unpack_from('<HH', rec, 0)
    i = 4
    for _ in range(cnt):
        i += 2
        while i + 1 < len(rec) and rec[i:i + 2] != b'\xff\xff':
            i += 2
        i += 2
    N1, N2 = rec[i], rec[i + 1]            # ★ N1=列数(25) N2=行数(20)——盘为 N2行×N1列
    ROWS, COLS = N2, N1
    base = i + 2                           # ★ 解盘起点（2 字节 SJIS 解，行优先 row*COLS+col）
    sb = base + 2 * ROWS * COLS + 2        # ★ 槽位区（每格 1 字节，&0x7f 还原槽号）
    # ★★★ 布局（2026-10-15 与实机下屏缩略图 16/16 格逐格比对锁定）：
    #   * 记录头两字节 = (列数, 行数)，棋盘 = 20行×25列（rec270）——非「25行×20列」；
    #   * sol/槽位区均按 行优先 idx = row*COLS + col 存储；
    #   * entries 区坐标对 = (列, 行)。
    # 旧代码把 (25,20) 当 (行,列) 且按 k//C,k%C 索引 → 方盘(R==C)无差别易关全过，
    # 矩形盘整体转置 → 分组散点、槽号错位，怎么重跑都不出正解（唯一根因）。
    def _idx(rw, cl):
        return rw * COLS + cl
    sol = {_idx(rw, cl): rec[base + 2 * _idx(rw, cl): base + 2 * _idx(rw, cl) + 2].decode(
        'cp932', 'replace') for rw in range(ROWS) for cl in range(COLS)}
    slots = {_idx(rw, cl): rec[sb + _idx(rw, cl)] & 0x7f
             for rw in range(ROWS) for cl in range(COLS)}
    # 候选表：槽位区后 1 字节 = 候选字数，其后 2×N 字节为候选汉字，末字节 0xCC 终止
    hdr = sb + ROWS * COLS
    n_cand = rec[hdr]
    cands = [rec[hdr + 1 + 2 * k: hdr + 1 + 2 * k + 2].decode('cp932', 'replace')
             for k in range(n_cand)]
    by_slot = {}
    for rw in range(ROWS):
        for cl in range(COLS):
            b = slots[_idx(rw, cl)]
            if b:
                by_slot.setdefault(b, []).append((rw, cl))
    plan = []
    for n in sorted(by_slot):
        cells = by_slot[n]
        kanji = sol[_idx(*cells[0])]
        assert all(sol[_idx(rw, cl)] == kanji for rw, cl in cells), '槽%d 解不一致' % n
        assert kanji in cands, '槽%d 的 %s 不在候选表' % (n, kanji)
        plan.append({'slot': n, 'kanji': kanji, 'cells': cells,
                     'li': cands.index(kanji),
                     'page': cands.index(kanji) // CANDS_PER_PAGE})
    slots_mat = [[slots[_idx(rw, cl)] != 0 for cl in range(COLS)] for rw in range(ROWS)]
    return plan, (ROWS, COLS), slots_mat, cands


class Win:
    """盘面窗口状态机（标定模型 A）。"""
    __slots__ = ('cur', 'org', 'R', 'C')

    def __init__(self, cur, org, R, C):
        self.cur, self.org, self.R, self.C = list(cur), list(org), R, C

    def in_win(self, t):
        return (self.org[0] <= t[0] < self.org[0] + 4 and
                self.org[1] <= t[1] < self.org[1] + 4)

    def copy(self):
        return Win(self.cur, self.org, self.R, self.C)


_WALK_MEMO = {}


def walk_cost(w, tgt, cells, gid=None):
    """从状态 w 开始，朝导航目标格 tgt（目标组的某一格）行走。

    方向规则与 runner v5 **完全一致**（org 违反量规则，runner 闭环只认蓝框真值）：
      行违反 rv = tgt_r - (org_r + 3)（>0 需按 DOWN / <0 需按 UP），列同理；
      取 |违反| 大的轴；每按一步：org 朝该向滚 1 格（夹取），光标 board 坐标恒 +1。
    停止条件（与 runner 同构）：
      * 光标落进该组任一格 ⇒ 免点击（runner 用橙框实时判定）；
      * 或 tgt 进窗 ⇒ 点击 tgt 所在槽（runner 点的就是它）。
    返回 (presses, 新状态, 免点击?)。

    ★ 记忆化：结果只依赖 (R,C,org,cur,组,tgt)，与「已填哪些组」无关 ⇒ beam 里同一
      (org,cur) 会被不同 mask 反复请求同一目标，memo 命中率很高（数倍提速）。
    """
    if gid is None:
        gid = tuple(cells)
    mkey = (w.R, w.C, w.org[0], w.org[1], w.cur[0], w.cur[1], gid, tgt)
    hit = _WALK_MEMO.get(mkey)
    if hit is not None:
        n, org, cur, free = hit
        return n, Win(cur, list(org), w.R, w.C), free
    w = w.copy()
    cells_set = set(cells)
    if tuple(w.cur) in cells_set:
        res = (0, w, True)
    else:
        n = 0
        while tuple(w.cur) not in cells_set:
            if w.in_win(tgt):
                break
            rv = tgt[0] - (w.org[0] + 3)    # >0: tgt 在窗下方 ⇒ DOWN
            cv = tgt[1] - (w.org[1] + 3)    # >0: tgt 在窗右方 ⇒ RIGHT
            if abs(rv) >= abs(cv):
                step = 1 if rv > 0 else -1
                no = w.org[0] + step
                if 0 <= no <= w.R - 4:
                    w.org[0] = no
                w.cur[0] = min(max(w.cur[0] + step, 0), w.R - 1)
            else:
                step = 1 if cv > 0 else -1
                no = w.org[1] + step
                if 0 <= no <= w.C - 4:
                    w.org[1] = no
                w.cur[1] = min(max(w.cur[1] + step, 0), w.C - 1)
            n += 1
            if n > 4 * (w.R + w.C):
                break
        res = (n, w, tuple(w.cur) in cells_set)
    _WALK_MEMO[mkey] = (res[0], tuple(res[1].org), tuple(res[1].cur), res[2])
    return res


HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import plan_store as PS   # noqa: E402  （统一动作序列仓库 validation/plans.json）


def _code_fingerprint():
    """本模块源码 + datasheet 的指纹（§S32.3 / §S34.3）。

    解析器或数据一变，指纹即变 ⇒ 旧规划缓存自动作废重算。
    只认 mtime 不够（改代码不碰数据时，mtime 型 key 虽能变，但仓库内缓存按
    rec 固定下标提交，必须靠内容指纹防「提交了陈旧规划」）。
    """
    h = hashlib.sha256()
    h.update(open(os.path.abspath(__file__), 'rb').read())
    h.update(b'|')
    st = os.stat(DATA)
    h.update(('%x' % int(st.st_mtime)).encode())
    return h.hexdigest()[:16]


def beam_plan(idx, beam=400, verbose=False, use_cache=True):
    """beam search（**自算，不再以 plans.json 为缓存**）。

    ★ 2026-10-15：缓存从 `validation/plans_mode2/rec%d.json`（7 个单文件）挪进
      统一仓库 `validation/plans.json`（下标即 rec，见 plan_store.py）。
    ★ §S40：仓库只存 seq——`fingerprint` 防陈旧门随字段移除，改依仓库惯例
      （改规划器/datasheet 后重跑，与模式1/3 一致，见 PITFALLS §S34.3/§S40）；
      stats 由 seq 现算（total/groups = 步数），成本分解不再落盘。
    ★ §S52：plans.json 已彻底字符串化（45 条 mode2 也转成 §S45 **动作序列**字符串，
      `PS.get` 返回的是 `(kind,a,b,note)` 动作 4-tuple，**不是** beam 路径）。
      beam 路径 `[(组号,[x,y])]` 是规划器/实机 runner 的内部表示，与动作序列
      语义不同，**不再读写 plans.json**——仓库只存动作字符串，beam 每次现算
      （规划在进游戏前完成，不计入游戏内计时器，见 run_mode2_easy1_fast.py）。
    """
    if use_cache:
        blob = PS.get(idx)
        # 仅当 blob 是旧 beam 数组（元素 [组号,[x,y]] 或 (组号,(x,y))）才命中；
        # §S52 后仓库是动作 4-tuple，形状不符 → 视为未命中，走现算。
        if isinstance(blob, list) and blob:
            try:
                k0, t0 = blob[0]
                if isinstance(k0, int) and isinstance(t0, (list, tuple)) and len(t0) == 2:
                    seq = [(k, tuple(t)) for k, t in blob]
                    return seq, {'total': len(seq), 'groups': len(seq)}
            except Exception:
                pass
    """beam search 求近似最优「组序 + 目标格」序列。

    状态 = (剩余组 mask, org, cur, 候选页)。返回 (seq, stats)：
      seq   = [(组下标 k, 导航目标格 (r,c)), ...] 按执行序
      stats = dict(总动作/方向/点击/点字/翻页)
    """
    plan, (R, C), _, cands = load_plan(idx)
    n = len(plan)
    full = (1 << n) - 1
    states = {(full, (0, 0), (0, 0), 0): (0, [])}
    for step in range(n):
        new = {}
        for (mask, org, cur, page), (cost, path) in states.items():
            w = Win(cur, list(org), R, C)
            for k in range(n):
                if not (mask >> k) & 1:
                    continue
                cells = plan[k]['cells']
                for tgt in cells:
                    pr, w2, free = walk_cost(w, tgt, cells, gid=(idx, k))
                    turn = abs(plan[k]['page'] - page)
                    c = cost + pr + (0 if free else 1) + 1 + TURN_W * turn
                    # 点击后光标 = 点击格(tgt)；免点击则保持行走终点
                    ncur = tuple(w2.cur) if free else tuple(tgt)
                    key = (mask & ~(1 << k), tuple(w2.org), ncur, plan[k]['page'])
                    if key not in new or new[key][0] > c:
                        new[key] = (c, path + [(k, tgt)])
        states = dict(sorted(new.items(), key=lambda kv: kv[1][0])[:beam])
        if not states:
            raise SystemExit('beam 搜索失败（step %d）' % step)
        if verbose:
            print('  step %2d/%d：%d 状态，最优 %d 动作'
                  % (step + 1, n, len(states),
                     min(v[0] for v in states.values())), file=sys.stderr)
    cost, path = min(states.values(), key=lambda v: v[0])
    # 分解统计（与 runner 口径一致）
    w = Win((0, 0), (0, 0), R, C)
    pr_tot = clk_tot = turn_tot = 0
    page = 0
    for k, tgt in path:
        cells = plan[k]['cells']
        pr, w2, free = walk_cost(w, tgt, cells)
        pr_tot += pr
        if not free:
            clk_tot += 1
            w2.cur = list(tgt)
        turn_tot += abs(plan[k]['page'] - page)
        page = plan[k]['page']
        w = w2
    stats = dict(total=pr_tot + clk_tot + n + turn_tot, press=pr_tot, click=clk_tot, tap=n, turn=turn_tot,
                 groups=n, R=R, C=C, cands=len(cands))
    # §S52：不再把 beam 路径写回 plans.json——仓库只存 §S45 动作序列字符串，
    # beam 路径是规划器/runner 内部表示，每次现算（规划不计入游戏内计时）。
    return path, stats


def main():
    idxs = [int(a) for a in sys.argv[1:]] or [260, 250, 251]
    names = {260: '易1', 250: '易6', 251: '易7'}
    for idx in idxs:
        t0 = time.time()
        path, st = beam_plan(idx)
        plan, (R, C), _, _ = load_plan(idx)
        print('=== %s (rec%d)：%d 组 / %dx%d / 候选 %d 字 ==='
              % (names.get(idx, 'rec%d' % idx), idx, st['groups'], R, C, st['cands']))
        print('  总动作 %d = 方向键 %d + 点击 %d + 点字 %d + 翻页 %d（规划耗时 %.1fs）'
              % (st['total'], st['press'], st['click'], st['tap'], st['turn'],
                 time.time() - t0))
        print('  组序：%s' % ' '.join(str(plan[k]['slot']) for k, _ in path))
        print('  目标格：%s' % ' '.join('%s@%s' % (plan[k]['kanji'], t)
                                        for k, t in path[:10]), '...' if len(path) > 10 else '')


if __name__ == '__main__':
    main()
