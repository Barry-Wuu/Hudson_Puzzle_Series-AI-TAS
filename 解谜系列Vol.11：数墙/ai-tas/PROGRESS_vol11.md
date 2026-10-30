# Vol.11 数墙 — 进度交接（2026-10-27 19:25）

## 已完成
- **seg2（やさしい）**：已交付
- **seg3（ふつう 30 关）**：已裁剪交付 → `/workspace/_publish/seg3.mp4`（202MB）
- **seg4（むずかしい 80 关）**：已裁剪+拼接交付
  - 成品 `/workspace/数墙_seg4_final.mp4`（287MB / 6205.4s = 1:43:25 / 256×384@30 / AAC 44.1k）
  - 校验：音视频总长一致（6205.333 vs 6205.339）、音频 267327 包 0 非单调、全片解码 0 错误、
    4 个拼接点（含 lv40→41 尺寸切换）画面干净、随机 6 点抽帧正常
  - 外链 `https://aa434dc3de40707a7.app.workbuddy.host/数墙_seg4_final.mp4?sharecode=OVRAFMDSE2`
    （seg3 同域名 `/seg3.mp4?sharecode=OVRAFMDSE2`）

## 关键结论（可复用到其它 vol）
1. **36×20 剂量已优化**：`TAP_MEGA` 由 `0.04/0.07/0.03`(0.14s) 改为 **`0.03/0.07/0.035`(0.135s)**，
   lvl41 实测 100% ×3，fill 92.3s（旧档 96.5s）。硬边界在 0.130~0.135，低于边界会漏 ~9% 且 fill 涨 2.5 倍。
   分界线是**静默期 hold+after ≥ 0.105**，不是总时长 → gap 让位给 after。
2. **vol11 无全通贺动画**：第 080 問 结算与普通关完全同构（完成 → クリアタイム + ★★★★★ → 得分滚动 → 淡出）。
   「全通贺动画」是 **vol13 白金认证**专属。不必为片尾补素材。
3. 录制架构（本 vol 定型，可复用）：
   - 每关一段 mp4 + 每关 `pkill desmume` 落盘（`game.dsv.bak_lvN`），断点续录，最坏只丢当前关
   - **BGM3 只在开头设一次**（pkill 会刷 SRAM，BGM 作为全局设置被继承），省 ~3 小时
   - 逐关裁剪：`trim_select_save.py`（删 save 橙盒屏、选关压至 0.5s）→ concat demuxer 拼接

## 待办
- [x] **むずかしい 80 关通关截图已更新**（2026-10-27 19:47）：
      `validation/mode4_hard/l001_clear.png` ~ `l080_clear.png`，均为「上屏答案板 + 下屏クリアタイム/六星/总分」
      - 工具：`ai-tas/extract_clear_shots.py`（从原始片段末尾 45s 扫描，10fps，取连续 3 帧稳定 6 星 + 亮度>=93%峰值）
      - 旧版问题：git 里仅 50 张（l001~l050），其中 **49 张不是结算页**（下屏被暂停菜单遮挡、上屏停在「完成」大字），
        且为慢版时长（l001 0:01:13、l030 0:02:11、l045 0:05:38）；新版 l001=0:00:33、l030=0:00:31
      - 新版为 RGB 未量化（约 134KB/张，共 11MB）；如需压体积可 256 色量化（PSNR 33.6dB，60KB/张）
- [ ] 等夜间 HY3/HY4 免费额度恢复后，继续录其它 vol（vol13 需注意有白金认证贺动画，别当 save 屏剪掉）
- [ ] B 站多 P 合集发布完成后，可回收本地母版：
      `/workspace/数墙_seg4_lv*.mp4`（80 段）、`/workspace/_seg4_trim/`、`/workspace/_publish/`

## 环境现状
- Xvfb :99 / pulse（`/tmp/pulse_native`）仍在，desmume 已退出，`game.dsv` 已还原为剂量测试前状态
- 剂量测试脚本：`seg4_dose_test.py` / `seg4_dose_test2.py` / `seg4_dose_test3.py`，日志 `/tmp/dose_test*.log`
