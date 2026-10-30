# ai-tas 脚本索引

72 个文件的用途与状态对照。**按"现役 / 历史 / 一次性"分三类**，接手时只需读 A~D。

---

## A. 现役 · 公用层

| 文件 | 用途 |
|---|---|
| `ds.py` | DeSmuME 操作公用层：抓屏 / 按键 / **按压式触摸**（mousemove→40ms→mousedown→60ms→mouseup）/ 单进程批量触摸 / 光标框检测 |
| `state2.py` | 页面状态检测 v3：实测 RGB 签名 + 通用「单元格掩码」（兼容已通关变绿） |
| `play_common.py` | 入門 6×6 盘面公用层：几何 + 扫描 |
| `guide.py` | 照抄攻略：从 `攻略.md` 解析每关官方答案黑格坐标（去求解器） |
| `extract_nurikabe.py` | 题库提取器：arm9 → `validation/puzzles.json`（300 题 + 规则自检） |

## B. 现役 · 跑批（纯通关，不录制）

| 文件 | 用途 |
|---|---|
| `mode2_fast.py` | **难度参数化执行器**：`V11_DIFF` 切四难度。含全部剂量常量 `TAP` / `TAP_WIDE` / `TAP_HUGE` / `TAP_MEGA`，以及 `fill_wide` / `fill_huge` 滚动连涂、`verify_*` 补漏、`stars_gold` / `wait_clear` |
| `mode1_fast.py` | 入門 3★ 执行器（4.8s 白涂窗口 + 盲发连涂） |

## C. 现役 · 录制链

| 文件 | 用途 |
|---|---|
| `seg1_run.py` | seg1 驱动：入門 20 关（第 1 关 tut 引导 + 其余 play 解题） |
| `seg2_run.py` | seg2 驱动：やさしい 1..100 |
| `seg3_run.py` | seg3 驱动：ふつう 1..100（`fill_level` / `enter_and_prepare` 被 seg4 复用） |
| `seg4_run.py` | seg4 驱动：むずかしい 1..80 |
| `rec_seg4_perlevel.sh` | **分关录制（现役）**：每关一段 mp4 + 每关 `pkill` 落盘 + 断点续录；BGM 只在段首设一次 |
| `seg4_assemble.sh` | **装配（现役）**：逐关 `trim_select_save.py` → concat demuxer 拼接 |
| `trim_select_save.py` | 关间裁剪：选关界面只留末 0.5s、「セーブしています…」橙盒屏整段删除 |
| `bgm3_setup.py` / `bgm2_setup.py` | 段首 BGM 切换（进选项菜单设定 → 靠 SRAM 继承到后续关卡） |
| `boot_to_select.py` | 冷启动导航：title `tap(128,40)` → 存档1 → 选关页 |
| `check_evidence.py` | 证据校验：逐张读金星数 + TIME 横幅 + 连续性（`total/bad`） |
| `extract_clear_shots.py` | **从实况抽通关页截图**（2026-10-27 新增）：末尾 45s / 10fps / 连续 3 帧稳定 6★ / 亮度≥93% 峰值；内含 `stars_robust()` 修星星碎块误判 |

## D. 剂量标定（结论已固化进 `mode2_fast.py` 常量注释）

| 文件 | 用途 |
|---|---|
| `seg4_dose_test.py` | むずかしい 两尺寸基础档（24×14 对照 + 36×20 三档） |
| `seg4_dose_test2.py` | 36×20 的 0.13~0.14 夹缝（0.135 三种配比） |
| `seg4_dose_test3.py` | 0.135 稳定性重复验证 + 0.14 基线噪声（**定案依据**） |
| `seg3_dose_test.py` | ふつう 两尺寸剂量快测 |
| `exp_dose_grid.py` | 18×10 宽盘剂量网格：分离 gap / hold / after 三因子 |

## E. 历史脚本（使命已完成，保留备查）

| 文件 | 说明 |
|---|---|
| `rec_seg4.sh` | seg4 早期**整段长进程**录制版 —— 被 `rec_seg4_perlevel.sh` 的分关方案取代（长进程会被沙箱回收整段打断） |
| `seg4_pipeline.sh` | supervisord 托管版（killasgroup）—— 因孤儿进程误判 Backoff，已弃用 |
| `seg4_prep.sh` / `seg4_post.sh` | 早期录制前后处理 |
| `rec_seg1_v2.sh` / `rec_seg2.sh` / `rec_seg3.sh` / `rec_seg3_dose.sh` / `rec_single_limiter_on.sh` / `seg1_record.sh` | 各段早期录制脚本 |
| `rec_movie.py` | dsm 影片录制探针（DeSmuME movie 格式分析） |
| `seg1_driver.py` | seg1 早期驱动（import mode2_fast） |
| `nyumon_play.py` / `tut.py` / `tut_test.py` / `tut_grid_test.py` | 入門教学关早期实现（闪烁格引导 / 网格检测回归） |
| `seg3_probe.py` / `seg3_probe.sh` | 探针：确认ふつう第 1 关是否有教程 |
| `test_single_guide.py` / `test_single_lvl.py` | 单关测试（限速器 ON + 有声录像） |

## F. 一次性诊断/实验（结论已并入 `PITFALLS.md`，无需重跑）

| 文件 | 说明 |
|---|---|
| `diag51.py` `diag51b~e` `diag51h~j` `diag_coords.py` | 第 51 关异常与坐标标定的诊断分支 |
| `exp_check18.py` | lvl18 多涂 2 格之谜 |
| `exp_drag_test.py` / `exp_drag_wide.py` | 拖动连涂可行性（实测仅 27~34% 命中，已排除） |
| `exp_fill_diag.py` | `fill_wide` 分阶段插桩，定位 81-100 丢击段 |
| `exp_gap.py` / `exp_wide_fast.py` / `exp_wide_full.py` | 连涂参数剂量-反应实验 |
| `exp_slowmo.py` / `exp_slowmo2.py` | SIGSTOP/CONT 降速实验 |
| `exp_turbo.py` | `--disable-limiter` 全速实验 |
| `exp_ipc.py` | IPC 触摸结构逆向（共享内存 diff） |
| `explore_bgm.py` / `explore_bgm.sh` / `seg4_explore.py` | BGM 选项定位 / 选项菜单原分辨率截图探索 |
| `rsp.py` / `rsp2.py` / `rsp_proxy.py` | GDB Remote Serial Protocol 客户端（arm9gdb stub 读内存） |

## 文档

| 文件 | 内容 |
|---|---|
| `MODE2_PROGRESS.md` | やさしい 攻关交接（满星 n+2、体験版陷阱、选关页滚动、18×10 横滚） |
| `MODE3_PROGRESS.md` | ふつう 攻关交接（24×14 滚动机制标定：红框 7px/格、光标推边纵滚、黄▶按住横滚） |
| `PROGRESS_vol11.md` | むずかしい 收尾交接（成品路径、剂量结论、录制架构、待办） |
| `../PITFALLS.md` | 踩坑清单 + 数据层规格（**接手必读**） |
| `../README.md` | 项目总览：战果、涂墙节奏、目录、复现命令 |
