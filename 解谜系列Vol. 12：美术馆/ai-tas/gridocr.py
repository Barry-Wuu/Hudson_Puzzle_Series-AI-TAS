"""选关网格数字 OCR（模板匹配）。

背景：重启 desmume 后，本存档（ふう 110/110 全清）网格整片绿色，
cursor_cell 的绿色判据失效、方向键到边界会环绕、✕ 退出后光标位置不保证，
因此「靠光标/计数定位关卡」全部不可靠。唯一稳定的是网格里印着的关卡数字。

做法：
  1) 从一张已知窗口的截图（t0.png，首行 31..40）按位置标注自动生成 0-9 数字模板；
  2) 运行时把 5×10 个格子的数字逐个切分、归一化成 5×9 位图，与模板比对，
     得到窗口里 50 个关号 ⇒ 窗口原点已知 ⇒ 目标格 (r,c) 可直接触摸。

几何（实测 t0.png 逐列/逐行扫描）：列中心 x = 20 + 24c，行中心 y = 279 + 16r。
"""
import json
import os

import numpy as np

CELL_X0, CELL_DX = 20, 24
CELL_Y0, CELL_DY = 279, 16
ROWS, COLS = 5, 10
DW, DH = 5, 9          # 归一化数字尺寸


def _white_mask(a, cx, cy, half_w=9, half_h=6):
    """取格子内白色数字掩码（返回 (h,w) bool）。"""
    sub = a[cy - half_h:cy + half_h + 1, cx - half_w:cx + half_w + 1]
    return (sub[:, :, 0] > 190) & (sub[:, :, 1] > 190) & (sub[:, :, 2] > 190)


def _split_digits(mask):
    """按空列把数字掩码切成若干位（返回每个位的 (r0,r1,c0,c1)）。"""
    colhas = mask.any(axis=0)
    runs, s = [], None
    for x, v in enumerate(colhas):
        if v and s is None:
            s = x
        elif not v and s is not None:
            runs.append((s, x - 1))
            s = None
    if s is not None:
        runs.append((s, len(colhas) - 1))
    boxes = []
    for c0, c1 in runs:
        rows = np.nonzero(mask[:, c0:c1 + 1].any(axis=1))[0]
        if len(rows) == 0:
            continue
        boxes.append((rows.min(), rows.max(), c0, c1))
    return boxes


def _norm(mask, box):
    """把某个数字位归一化成 DH×DW 的二值位图（最近邻重采样）。"""
    r0, r1, c0, c1 = box
    sub = mask[r0:r1 + 1, c0:c1 + 1]
    h, w = sub.shape
    out = np.zeros((DH, DW), dtype=bool)
    for y in range(DH):
        sy = int(y * h / DH)
        sy = min(sy, h - 1)
        for x in range(DW):
            sx = min(int(x * w / DW), w - 1)
            out[y, x] = sub[sy, sx]
    return out


def build_templates(png_path, first_row_value=31, out_json=None):
    """从已知窗口截图生成 0-9 模板（首行最左格 = first_row_value）。"""
    from PIL import Image
    a = np.asarray(Image.open(png_path).convert("RGB")).astype(int)
    store = {}
    for r in range(ROWS):
        for c in range(COLS):
            want = first_row_value + 10 * r + c
            if want > 110:
                continue
            cx, cy = CELL_X0 + CELL_DX * c, CELL_Y0 + CELL_DY * r
            boxes = _split_digits(_white_mask(a, cx, cy))
            digits = str(want)
            if len(boxes) != len(digits):
                continue
            for box, ch in zip(boxes, digits):
                store.setdefault(ch, []).append(_norm(_white_mask(a, cx, cy), box))
    # 每种数字取像素众数，压成单一模板
    tpl = {}
    for ch, arrs in store.items():
        st = np.stack(arrs)
        tpl[ch] = (st.mean(axis=0) >= 0.5).astype(np.uint8).reshape(-1).tolist()
    if out_json:
        with open(out_json, "w") as f:
            json.dump(tpl, f)
    return tpl


def load_templates(json_path):
    with open(json_path) as f:
        raw = json.load(f)
    return {k: np.array(v, dtype=bool).reshape(DH, DW) for k, v in raw.items()}


def read_cell(mask, tpl):
    """识别单个格子的关号；失败返回 -1。"""
    boxes = _split_digits(mask)
    if not 1 <= len(boxes) <= 3:
        return -1
    s = ""
    for box in boxes:
        n = _norm(mask, box)
        best, bestd = None, 1e9
        for ch, t in tpl.items():
            d = int((n ^ t).sum())
            if d < bestd:
                bestd, best = d, ch
        if best is None or bestd > 4:
            return -1
        s += best
    try:
        return int(s)
    except ValueError:
        return -1


def read_grid(a, tpl):
    """读整屏 5×10 关号矩阵；不可读的格子为 -1。"""
    grid = [[-1] * COLS for _ in range(ROWS)]
    for r in range(ROWS):
        for c in range(COLS):
            cx, cy = CELL_X0 + CELL_DX * c, CELL_Y0 + CELL_DY * r
            grid[r][c] = read_cell(_white_mask(a, cx, cy), tpl)
    return grid


if __name__ == "__main__":
    import sys
    png = sys.argv[1] if len(sys.argv) > 1 else "t0.png"
    here = os.path.dirname(os.path.abspath(__file__))
    js = os.path.join(here, "grid_digits.json")
    build_templates(png, 31, js)
    tpl = load_templates(js)
    from PIL import Image
    a = np.asarray(Image.open(png).convert("RGB")).astype(int)
    g = read_grid(a, tpl)
    for row in g:
        print(row)
