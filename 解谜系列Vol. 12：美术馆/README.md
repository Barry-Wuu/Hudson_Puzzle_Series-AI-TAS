# 《解谜系列Vol.12：美術館 / AKARI（点灯）》AI-TAS 战线

> Hudson「解谜系列」第 12 作。NDS 日版，ROM 名 `vol12.nds`，存档 `vol12.dsv`（按 ROM 名由 DeSmuME 落盘于 `~/.config/desmume/vol12.dsv`）。
> 玩法：Akari（点灯）逻辑谜题，在黑墙上放置灯泡，使每个白格能被照亮且灯泡互不直射。

## 四模式与规模

| 模式 | 题量 | 盘面 | 满星上限 |
|---|---|---|---|
| 入門（tutorial） | 20 | 6×6 | — |
| やさしい（easy） | 100 | 10×10（1–80）/ 18×10（81–100 大盘） | 4 |
| ふつう（medium） | 100 | — | — |
| むずかしい（hard） | 70 | 24×14（×50）+ 36×20（×20） | 6 |

## 当前进度

- **やさしい Q81–Q100**：已录制成品 + 逐关取证（19/20 满星，Q91 偏慢 1/4）。
- **むずかしい Q01–Q70**：已录制成品 + 逐关取证（69/70 满星，Q46 偏慢 5/6）。
- 入門 / ふつう：尚未录制。
- 存档 `saves/vol12.dsv`（全模式进度铁证）。
- 取证截图 `validation/`（四模式结构已建，与 Vol.11 约定一致）。

## 目录

| 路径 | 内容 |
|---|---|
| `ai-tas/` | 求解 / 规划 / 录制全管线（`play_yasashii.py`、`play_akari_muzu.py`、`rec_*_limiter.sh`、`trim_*`、`MUZU_RUN.md`、`YASA_PROGRESS.md`…） |
| `validation/` | 逐关通关证据截图 + `puzzles.json`（四模式官方解答） |
| `saves/` | 实机存档 `vol12.dsv` |
| `攻略.md` | 全关卡官方解答（Markdown 表格） |

## 取证约定（validation/）

每关一张 `lNNN_clear.png` = 上屏已解盘面 + 下屏クリアタイム + 星级。
判据：下屏蓝面板密度定位通关页 → 取星级定格的「稳定尾帧」。详见 `validation/README.md`。

> 游戏 ROM 版权归 Hudson / 版权方所有。本仓库仅存放 AI-TAS 工具链、动作序列与取证截图，**不含任何 ROM 文件**。
