#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统一的动作序列仓库：`validation/plans.json`（**列表第 n 项 = rec n**）。

为什么合并成一个文件（2026-10-15）：
  原来动作序列散在三个目录里，各有各的命名与缓存语义：
    * `validation/plans/`        模式1，按「难度+关卡」命名 `<diff>_l<NN>.json`（160 个）
    * `validation/plans_mode2/`  模式2 beam，按 rec 命名 `rec%d.json`（7 个，带指纹）
    * `validation/plans_by_rec/` 按 rec 命名 `rec%03d.json`（255 个）
  三套目录 422 个文件、约 2.8 MB，命名还不统一（rec%d vs rec%03d），
  读一侧要先猜目录。合成一个 JSON 数组后：**下标即 rec**，`get(n)` 一行搞定。
  （§S52 起 `validation/plans_mode2/` 已删除，plans.json 为唯一权威。）

文件格式（`validation/plans.json`）—— **§S40 起只存动作序列本身**：
    [ null, "M3K01…", null, …, "MfK20…" ]      # 长度 300（定长步、无分隔符）
  * 长度固定 300（datasheet 记录数），下标 = rec 号；没有计划的 rec 存 `null`。
  * 有计划的项**就是 seq**：ASCII 定长编码字符串（§S43：每步定长、步间无分隔符；
    §S44/§S45：`M<x>`=2 字符（x=row*4+col 小写 hex）、`K<行><列>`=3 字符、其余
    kind=1 字符；字符集 `MK^v<>LRXPQ`，仅 page 用 P/Q、black 用 X）。
  * **§S52 起 300/300 全部为字符串**：45 条 mode2 beam 数组已由
    `mode2_fill.build_lr` 求出动作序列后转成 §S45 字符串，仓库内**不存在 list**。
  * **不存任何元数据**（2026-10-15 用户：「这个 json 只需要存储动作序列」）：
    W/H/nbadge/nkanji/arrows/n_touch/n_arrow/n_hop/n_page/n_black/pred_fill_s/
    diff/level/walls/stats/mode/rec/fingerprint 全部移除。执行只用 seq；
    统计由 `seq_codec.seq_stats(seq)` 从 seq **现算**；mode 分布由 `stats()`
    经 `kanji_common` 的 rec 映射表**反查**推导（单一事实来源，比存字段更不易漂移）。
  * 读写的编解码由 `seq_codec` 在本模块内**透明完成**——`get()` 返回的永远是
    4 元素动作 tuple list，生产方/消费方无需感知编码。
  * 保存时 value 可以是 dict（自动取 `['seq']`，生产方无感）或 seq 本身。

并发约定：
  * **读**无锁（进程内按 mtime+size 缓存，跨进程改动下一此 load 自动失效）。
  * **写**只允许单写者：批处理脚本在父进程汇总各并行任务结果后调用一次 `save()`，
    不要在多进程 worker 里直接 `save()`。`save()` 自身仍加 `flock` + 原子替换兜底。

用法：
    import plan_store as PS
    PS.get(160)                 # rec160 的 seq（4 元素 tuple list），无则 None
    PS.save({161: res, 162: None})   # 批量合并写回（res 为 dict 或 seq；None = 删除）
"""
import fcntl
import json
import os
import threading

import seq_codec as SC

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))

STORE = os.path.join(REPO, 'validation', 'plans.json')
LOCK = STORE + '.lock'
N_REC = 300                     # datasheet 记录数（文件头 300 个 u32 偏移表）

_lock = threading.Lock()
_mem = {'key': None, 'data': None}


def path():
    """统一仓库文件路径。"""
    return STORE


def _as_seq(v):
    """save() 的 value → seq：dict 取 ['seq']（生产方无感），其余视为 seq 本身。"""
    if v is None:
        return None
    if isinstance(v, dict):
        return v.get('seq')
    return v


def load():
    """读整表并返回 list（长度补齐到 N_REC，缺的补 None）。

    进程内缓存 key = (st_mtime_ns, st_size)：别的进程改了什么，
    本进程下一次 load() 自动看到新内容，无需重启。
    §S40：每项就是 seq——落盘是 ASCII 编码字符串，读盘后透明解码回
    4 元素 tuple list；beam 的 list 原样返回。
    """
    try:
        st = os.stat(STORE)
        key = (st.st_mtime_ns, st.st_size)
    except OSError:
        key = None
    with _lock:
        if _mem['data'] is not None and _mem['key'] == key:
            return _mem['data']
    data = None
    if key is not None:
        try:
            with open(STORE, encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            data = None
    if not isinstance(data, list):
        data = []
    if len(data) < N_REC:
        data = data + [None] * (N_REC - len(data))
    # §S39/§S40：seq 落盘是 ASCII 编码字符串，读盘后透明解码回 4 元素 tuple list
    for i, d in enumerate(data):
        if isinstance(d, str):
            try:
                data[i] = SC.decode_seq(d)
            except Exception:
                pass          # 坏行保留原样，让消费方报错定位
    with _lock:
        _mem['key'] = key
        _mem['data'] = data
    return data


def get(rec):
    """取 rec 的动作序列（4 元素 tuple list；beam 为 [k,[r,c]] list）；无则 None。"""
    try:
        rec = int(rec)
    except (TypeError, ValueError):
        return None
    if rec < 0 or rec >= N_REC:
        return None
    d = load()[rec]
    return d if d is not None else None


def has(rec):
    """该 rec 是否已有计划。"""
    return get(rec) is not None


def save(updates):
    """把 {rec: plan|seq} 合并进仓库并原子落盘（value 为 None 表示删除该项）。

    value 可以是 dict（自动取 ['seq']——生产方照旧返回完整计划对象，无感）
    或 seq 本身。返回写入后的非空项数。读—改—写全程持 `plans.json.lock`
    排他锁，防止两个进程同时合并时互相覆盖。
    """
    if not updates:
        return sum(1 for x in load() if x is not None)
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    with open(LOCK, 'w') as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        try:
            # 拷贝一份再改：万一是写失败，进程内缓存不会被"抢跑"污染
            data = list(load())
            while len(data) < N_REC:
                data.append(None)
            for rec, plan in updates.items():
                rec = int(rec)
                if not 0 <= rec < N_REC:
                    raise ValueError('rec %d 越界（0..%d）' % (rec, N_REC - 1))
                seq = _as_seq(plan)
                data[rec] = None if seq is None else seq
            tmp = STORE + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                # §S39：写盘前把 seq 编为 ASCII 字符串（不可编码的 beam 原样存 list）
                json.dump([SC.encode_seq(d) if isinstance(d, (list, tuple)) else d
                           for d in data], f, ensure_ascii=False)
            os.replace(tmp, STORE)
        finally:
            fcntl.flock(lf, fcntl.LOCK_UN)
    # 落盘后让进程内缓存**失效**（而非直接缓存 data）：迁移场景下写入前的
    # 解码态可能还是旧格式（dict），直接缓存会让同进程 save→get 与跨进程
    # 读盘不同构。失效后下次 load() 重新读盘解码，两端永远一致（§S39）。
    with _lock:
        _mem['key'] = None
        _mem['data'] = None
    return sum(1 for x in data if x is not None)


def _rec_mode_map():
    """rec → mode，经 kanji_common 的映射表反查（§S40，单一事实来源）。

    模式1 经 `rec_for(1, diff, level)` 遍历 160 关；模式2/3 直接展开
    `MODE2_REC` / `MODE3_REC`。不在任何表内的 rec（認定题库、模式3 額外段）
    不进映射——统计里归 None，与旧「存储 mode=null」口径一致。
    """
    import kanji_common as KC
    m = {}
    for diff, cnt in (('yasashii', 35), ('futsuu', 60), ('muzukashii', 65)):
        for L in range(1, cnt + 1):
            try:
                m[KC.rec_for(1, diff, L)] = 1
            except Exception:
                pass
    for mode, table in ((2, KC.MODE2_REC), (3, KC.MODE3_REC)):
        for recs in table.values():
            for r in recs:
                m[r] = mode
    return m


def stats():
    """仓库统计 —— 文档里引用的数字一律以本函数输出为准，**不要手数**。

    返回 {n, cached, missing, by_mode, modes}：
      by_mode  已缓存项按 mode 键的分布（None = 認定题库/模式3 額外段等无登场关卡的 rec）
      modes    每个模式的「已规划 / 总 rec 数」，总数为 0 表示该模式无 rec 映射表
    §S40：mode 不再落盘，这里经 `_rec_mode_map()` 反查推导。
    """
    data = load()
    rm = _rec_mode_map()
    by_mode = {}
    for i, x in enumerate(data):
        if x is not None:
            m = rm.get(i)
            by_mode[m] = by_mode.get(m, 0) + 1
    filled = sum(by_mode.values())
    modes = {}
    try:
        import kanji_common as KC
        totals = {1: 35 + 60 + 65,
                  2: sum(len(v) for v in KC.MODE2_REC.values()),
                  3: sum(len(v) for v in KC.MODE3_REC.values())}
        for m in (1, 2, 3):
            done = sum(1 for i, x in enumerate(data)
                       if x is not None and rm.get(i) == m)
            modes[m] = {'done': done, 'total': totals[m], 'todo': totals[m] - done}
    except Exception:
        pass
    return {'n': N_REC, 'cached': filled, 'missing': N_REC - filled,
            'by_mode': by_mode, 'modes': modes}
