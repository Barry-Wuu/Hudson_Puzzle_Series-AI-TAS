"""Nurikabe（数墙）CP-SAT 求解器 —— Vol.11 汉字解谜系列备用求解器。

适用场景：日后遇到没有现成答案的数墙题目，可用本脚本从零求解并验证唯一性。

建模思路（数墙标准 4 规则全部入模）：
- wall[i]=1 表示该格是黑格，否则属于某个白格区；region[c][i] 布尔：格 i 属于第 c 个线索区。
- 规则1 白岛大小=线索值：每区 sum(region)==v；候选格预剪枝为曼哈顿半径 v-1 球。
- 规则2 白岛互不正交相邻：rid 整数变量 + 相邻约束（rid 1-based，0 留给墙）。
- 规则3 黑格连通：黑格整体一棵「父指针+深度」生成树，唯一根 depth=0。
- 规则4 无 2x2 黑格：任意 2x2 块黑格数 ≤ 3。
- 白区连通：同样用「父指针+深度」生成树（每区根=线索格）。

关于 AddCircuit：实测不适用。AddCircuit/AddMultipleCircuit 强制每点入=出=1（度2 单环），
而连通块必含叶节点（度1），永不可能成环 => 模型恒 INFEASIBLE。连通性请用父指针+深度树
（等价于 Deepseek 所说的"白格要流量/树、黑格成森林"）。

关键编码坑（2026-10-19 实测修复）：父子变量必须按「有向对」建（u->v 与 v->u 各一个），
求和只数「本格选父」的那条。若按无向边建一个变量、求和却数了两个端点，树会退化成匹配，
配平方程 2*边数+根数=黑格数 在偶数黑格时直接无解（黑格数为奇数时会侥幸通过，极具迷惑性）。

仅用线索位置/数值与棋盘尺寸求解，不读入已知答案（除最后核对比对）。
实测：むずかしい 第80問（36x20, 82 线索）自由求解约 20 秒 OPTIMAL，与游戏答案逐格一致；
FORBID_GIVEN=1 后 INFEASIBLE，证明该题在全规则下解唯一。

数据文件 puzzles.json 结构：
  {"入門":[...], "やさしい":[...], "ふつう":[...], "むずかしい":[...]}
  每题 {"rec", "w", "h", "clue":[一维数组, 0=空白, >=1=线索], "wall":[0=白,1=黑], "ok":true}
  若无 wall 字段（无答案题目），本脚本同样可求解，只是跳过比对。

用法：
  python nurikabe_solver.py [难度] [序号(0起)] [秒数]
    例：python nurikabe_solver.py 入門 0 60
        python nurikabe_solver.py むずかしい 79 300
  环境变量：
    FORBID_GIVEN=1  禁止与已知答案相同（唯一性检验，INFEASIBLE=唯一）
    FIX_GIVEN=1     把 wall 钉死为已知答案（定位"哪条约束与答案矛盾"用）
    DEBUG_SKIP=conn,touch,bconn   跳过对应约束块（调试用）
    DEBUG_DUMP=1    打印求解后的 region id 网格
    PUZZLES_JSON=路径  指定数据文件（默认按下列候选自动查找）

作为库调用：
  import nurikabe_solver as g
  data = g.load_puzzles()
  sol = g.solve_level(data, "むずかしい", 79, time_limit=300)  # 返回 [0/1] 列表或 None
  ok, msg = g.validate(sol, w, h, clue)
  print(g.matrix_str(sol, w, h, clue))
"""
import json
import os
import sys
from ortools.sat.python import cp_model

HERE = os.path.dirname(os.path.abspath(__file__))

# 数据文件候选位置（按序取第一个存在的）
PUZZLES_CANDIDATES = [
    os.environ.get("PUZZLES_JSON", ""),
    os.path.join(HERE, "puzzles.json"),
    os.path.join(HERE, "..", "_vol11", "puzzles.json"),
    os.path.join(HERE, "..", "..", "_vol11", "puzzles.json"),
    r"D:/B++/WorkBuddy/2026-10-10-20-10-45/_vol11/puzzles.json",
]


def load_puzzles(path=None):
    """加载 puzzles.json；path 为空时按候选列表自动查找。"""
    if path is None:
        for cand in PUZZLES_CANDIDATES:
            if cand and os.path.isfile(cand):
                path = cand
                break
        else:
            raise FileNotFoundError(
                "找不到 puzzles.json，请用 PUZZLES_JSON=路径 指定。已尝试:\n  "
                + "\n  ".join(c for c in PUZZLES_CANDIDATES if c))
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def neighbors(r, c, W, H):
    for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        nr, nc = r + dr, c + dc
        if 0 <= nr < H and 0 <= nc < W:
            yield nr, nc


def and_lit(model, lits):
    """构造与 lits 等价的布尔变量（双向蕴含，缺一不可）。"""
    if len(lits) == 1:
        return lits[0]
    b = model.NewBoolVar("")
    for lit in lits:
        model.AddImplication(b, lit)                   # b => 每个 lit
    model.AddBoolOr([lit.Not() for lit in lits] + [b])  # (所有 lit) => b
    return b


# 调试开关：设成集合可跳过对应约束块，例如 {"conn","touch","bconn"}
DEBUG_SKIP = set()


def solve_level(data, diff, idx, time_limit=180, workers=8):
    """求解单关。返回 [0/1] 列表（1=黑格）或 None（未解出）。"""
    p = data[diff][idx]
    W, H = p["w"], p["h"]
    clue = p["clue"]
    N = W * H
    idc = lambda r, c: r * W + c

    clues = [(r, c, v) for r in range(H) for c in range(W)
             if (v := clue[r * W + c]) > 0]
    C = len(clues)
    print(f"[{diff} 第{idx+1}問] 尺寸 {W}x{H}，线索数 {C}")

    model = cp_model.CpModel()

    # 每个区的候选格：曼哈顿半径 v-1 内（连通块尺寸 v 必落在该球内）
    cand = {}
    for ci, (r, c, v) in enumerate(clues):
        root = idc(r, c)
        seen = {root}
        frontier = [(r, c, 0)]
        cells = [root]
        while frontier:
            rr, cc, dist = frontier.pop(0)
            if dist >= v - 1:
                continue
            for nr, nc in neighbors(rr, cc, W, H):
                nn = idc(nr, nc)
                if nn not in seen:
                    seen.add(nn)
                    cells.append(nn)
                    frontier.append((nr, nc, dist + 1))
        cand[ci] = cells

    region = {}
    for ci in range(C):
        for cell in cand[ci]:
            region[(ci, cell)] = model.NewBoolVar(f"r{ci}_{cell}")

    # 线索格必在自己区
    for ci, (r, c, v) in enumerate(clues):
        model.Add(region[(ci, idc(r, c))] == 1)

    # 区大小 = 线索值
    for ci, (r, c, v) in enumerate(clues):
        model.Add(sum(region[(ci, cell)] for cell in cand[ci]) == v)

    # wall + rid
    wall = {}
    rid = {}
    for cell in range(N):
        rs = [region[(ci, cell)] for ci in range(C) if (ci, cell) in region]
        wv = model.NewBoolVar(f"w{cell}")
        rv = model.NewIntVar(0, C, f"rid{cell}")
        if rs:
            model.Add(wv + sum(rs) == 1)
            model.Add(rv == sum((ci + 1) * region[(ci, cell)]
                                for ci in range(C) if (ci, cell) in region))
        else:
            model.Add(wv == 1)
            model.Add(rv == 0)
        wall[cell] = wv
        rid[cell] = rv

    # 黑格：任意 2x2 块黑格数 ≤ 3
    for r in range(H - 1):
        for c in range(W - 1):
            cells4 = [idc(r, c), idc(r, c + 1), idc(r + 1, c), idc(r + 1, c + 1)]
            model.Add(sum(wall[x] for x in cells4) <= 3)

    # 黑格连通性（数墙标准规则第3条：所有黑格连通）。
    # 黑格构成一棵「父指针 + 深度」生成树，唯一根 depth=0，
    # 每非根黑格恰选一个黑邻居作父且深度严格小于自身 => 无环 => 全黑格连通。
    # 注意：父子变量必须按「有向对」建（u->v 与 v->u 各一个），求和只数
    # 「本格选父」的那条；若按无向边建一个变量、求和却数了两个端点，
    # 树会退化成匹配，配平 2*边数+根数=黑格数 在偶数黑格时直接无解。
    if "bconn" not in DEBUG_SKIP:
        root_b = {}
        par = {}    # (u, v) -> 格 u 选邻居 v 作父
        par_of = {cell: [] for cell in range(N)}
        for cell in range(N):
            root_b[cell] = model.NewBoolVar(f"br{cell}")
        for r in range(H):
            for c in range(W):
                i = idc(r, c)
                for nr, nc in neighbors(r, c, W, H):
                    j = idc(nr, nc)
                    b = model.NewBoolVar(f"bp{i}_{j}")
                    par[(i, j)] = b
                    par_of[i].append(j)
        for cell in range(N):
            model.Add(sum(par[(cell, j)] for j in par_of[cell])
                      + root_b[cell] == wall[cell])
        for (i, j), b in par.items():
            model.AddImplication(b, wall[i])
            model.AddImplication(b, wall[j])
        dep = {cell: model.NewIntVar(0, N, f"bd{cell}") for cell in range(N)}
        for cell in range(N):
            model.Add(dep[cell] == 0).OnlyEnforceIf(root_b[cell])
            model.Add(dep[cell] >= 1).OnlyEnforceIf(root_b[cell].Not())
        for (i, j), b in par.items():
            model.Add(dep[i] >= dep[j] + 1).OnlyEnforceIf(b)
        total_clue = sum(v for _, _, v in clues)
        if total_clue < N:  # 全盘皆白（无黑格）时不需要根
            model.Add(sum(root_b[cell] for cell in range(N)) == 1)

    # 不同白区正交相邻禁止：若 i、j 都非墙则须同区
    if "touch" not in DEBUG_SKIP:
        nz = {}
        for cell in range(N):
            b = model.NewBoolVar(f"nz{cell}")
            model.Add(rid[cell] != 0).OnlyEnforceIf(b)
            model.Add(rid[cell] == 0).OnlyEnforceIf(b.Not())
            nz[cell] = b
        for r in range(H):
            for c in range(W):
                i = idc(r, c)
                for nr, nc in ((r, c + 1), (r + 1, c)):  # 只取右、下避免重复
                    if nr >= H or nc >= W:
                        continue
                    j = idc(nr, nc)
                    b = and_lit(model, [nz[i], nz[j]])
                    model.Add(rid[i] == rid[j]).OnlyEnforceIf(b)

    # 白格区连通性：父指针 + 深度 的「生成树」编码（非 AddCircuit）。
    # 每个非根区格恰选一个「在区邻居」作父，深度严格递增 => 无环 = 连通树。
    # （AddCircuit 强制每点入=出=1，即度2单环，无法表示含叶节点的连通块，故不适用。）
    if "conn" not in DEBUG_SKIP:
        for ci, (r, c, v) in enumerate(clues):
            cells = cand[ci]
            root = idc(r, c)
            par = {}          # (u, j) -> 格 u 的父为邻居 j 的布尔
            par_of = {u: [] for u in cells if u != root}
            for u in cells:
                if u == root:
                    continue
                rr, cc = divmod(u, W)
                for nr, nc in neighbors(rr, cc, W, H):
                    j = idc(nr, nc)
                    if (ci, j) in region:
                        b = model.NewBoolVar(f"par{ci}_{u}_{j}")
                        par[(u, j)] = b
                        par_of[u].append(j)
            for u in cells:
                if u == root:
                    continue
                inr = region[(ci, u)]
                if par_of[u]:
                    model.Add(sum(par[(u, j)] for j in par_of[u]) == inr)
                else:
                    model.Add(inr == 0)  # 无候选邻居 -> 不能在区间内
            for (u, j), b in par.items():
                model.AddImplication(b, region[(ci, u)])
                model.AddImplication(b, region[(ci, j)])
            d = {u: model.NewIntVar(0, v - 1, f"d{ci}_{u}") for u in cells}
            model.Add(d[root] == 0)
            for (u, j), b in par.items():
                model.Add(d[u] >= d[j] + 1).OnlyEnforceIf(b)

    # 可选：把 wall 钉死为已知答案（用于定位“哪条约束与已知答案矛盾”）
    if os.environ.get("FIX_GIVEN") and p.get("wall"):
        given = p["wall"]
        for cell in range(N):
            model.Add(wall[cell] == (1 if given[cell] == 1 else 0))

    # 可选：禁止与已知答案完全相同（用于检验唯一性）
    if os.environ.get("FORBID_GIVEN") and p.get("wall"):
        given = p["wall"]
        diffs = []
        for cell in range(N):
            d = model.NewBoolVar(f"dg{cell}")
            if given[cell] == 1:
                model.Add(d == 1).OnlyEnforceIf(wall[cell].Not())
                model.Add(d == 0).OnlyEnforceIf(wall[cell])
            else:
                model.Add(d == 1).OnlyEnforceIf(wall[cell])
                model.Add(d == 0).OnlyEnforceIf(wall[cell].Not())
            diffs.append(d)
        model.Add(sum(diffs) >= 1)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_search_workers = workers
    solver.parameters.log_search_progress = False
    print("  建模完成，求解中...")
    st = solver.Solve(model)
    status = solver.StatusName(st)
    print("  状态:", status)
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None

    sol = [1 if solver.Value(wall[cell]) == 1 else 0 for cell in range(N)]
    if os.environ.get("DEBUG_DUMP"):
        print("--- solved rid grid (region id; 0=wall) ---")
        for r in range(H):
            print(" ".join(f"{solver.Value(rid[r*W+c]):2d}" for c in range(W)))
    return sol


def validate(wall, W, H, clue):
    """独立校验一个解是否满足数墙全部 4 条标准规则。"""
    N = W * H
    idc = lambda r, c: r * W + c
    # 1) 线索格是白格
    for r in range(H):
        for c in range(W):
            if clue[idc(r, c)] > 0 and wall[idc(r, c)] == 1:
                return False, f"线索格({r},{c})是黑格"
    # 2) 白格区：从每个线索 BFS，检查尺寸/连通/不夹带别的线索
    seen = [False] * N
    for r in range(H):
        for c in range(W):
            i = idc(r, c)
            if wall[i] == 1 or seen[i]:
                continue
            # 新白区
            comp = []
            stack = [i]
            seen[i] = True
            while stack:
                x = stack.pop()
                comp.append(x)
                rr, cc = divmod(x, W)
                for nr, nc in neighbors(rr, cc, W, H):
                    j = idc(nr, nc)
                    if wall[j] == 0 and not seen[j]:
                        seen[j] = True
                        stack.append(j)
            clues_in = [x for x in comp if clue[x] > 0]
            if len(clues_in) != 1:
                return False, f"白区含 {len(clues_in)} 个线索（须恰好1）"
            if len(comp) != clue[clues_in[0]]:
                return False, f"白区尺寸 {len(comp)} != 线索 {clue[clues_in[0]]}"
    # 3) 黑格无 2x2
    for r in range(H - 1):
        for c in range(W - 1):
            if sum(wall[idc(r + dr, c + dc)] for dr in (0, 1) for dc in (0, 1)) == 4:
                return False, f"存在 2x2 黑格块 @({r},{c})"
    # 4) 黑格连通（标准规则第3条：所有黑格必须连通成一个区）
    seen_b = [False] * N
    ncomp = 0
    for r in range(H):
        for c in range(W):
            i = idc(r, c)
            if wall[i] == 1 and not seen_b[i]:
                ncomp += 1
                if ncomp > 1:
                    return False, "黑格不连通（存在多个黑格连通块）"
                stack = [i]
                seen_b[i] = True
                while stack:
                    x = stack.pop()
                    rr, cc = divmod(x, W)
                    for nr, nc in neighbors(rr, cc, W, H):
                        j = idc(nr, nc)
                        if wall[j] == 1 and not seen_b[j]:
                            seen_b[j] = True
                            stack.append(j)
    return True, "OK"


def matrix_str(wall, W, H, clue):
    """盘面可视化：█=墙, □=空岛, 数字=线索。"""
    lines = []
    for r in range(H):
        row = []
        for c in range(W):
            i = r * W + c
            if wall[i] == 1:
                row.append("█")
            elif clue[i] > 0:
                row.append(str(clue[i]))
            else:
                row.append("□")
        lines.append("".join(row))
    return "\n".join(lines)


if __name__ == "__main__":
    DEBUG_SKIP.update(set(os.environ.get("DEBUG_SKIP", "").split(",")) - {""})
    data = load_puzzles()
    # 默认跑最后一关；可传参 入門 0 / やさしい 5 等
    if len(sys.argv) >= 3:
        diff, i = sys.argv[1], int(sys.argv[2])
    else:
        diff, i = "むずかしい", len(data["むずかしい"]) - 1  # 最后一关
    tl = int(sys.argv[3]) if len(sys.argv) >= 4 else 180

    p = data[diff][i]
    sol = solve_level(data, diff, i, time_limit=tl)
    if sol is None:
        print("未求解成功。")
        sys.exit(1)
    ok, msg = validate(sol, p["w"], p["h"], p["clue"])
    print("独立校验:", "通过 ✅" if ok else f"失败 ❌ ({msg})")
    # 与已知答案比对
    if p.get("wall"):
        same = all(sol[k] == p["wall"][k] for k in range(p["w"] * p["h"]))
        print("与已知答案完全一致:", "是 ✅" if same else "否（但可能是另一合法解）")
        if not same:
            diffs = sum(1 for k in range(p["w"] * p["h"]) if sol[k] != p["wall"][k])
            print(f"  差异格数: {diffs}")
    print("—— 解（█=墙, □=空, 数字=线索） ——")
    print(matrix_str(sol, p["w"], p["h"], p["clue"]))
