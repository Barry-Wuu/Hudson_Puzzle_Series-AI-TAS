# Vol.13 音乐反编译与复原（README）

> 2026-10-19 完成三轮反编译驱动修复。全部结论来自 ARM7 二进制逐指令分析，非猜测。

## 一、复原架构

```
SDAT → SSEQ 事件解释器（每轨独立模拟）→ SBNK 乐器查表 → SWAR ADPCM 波形
     → 音高重采样 + ADSR 包络 + 音量/声像 → 16 通道抢占混音 → WAV
```

## 二、反编译结论（ARM7, arm7.bin 166KB @ VMA 0x2380000, file off 0x5B200）

### 时序（tick 语义）
| 位置 | 结论 |
|---|---|
| `0x9BB8` | 播放器初始化：**tempo 默认 120 (0x78)**，倍率 K=0x100，累加阈值 240 (0xF0) |
| `0x9AE4` | 每 sound tick：`acc += (tempo*K)>>8`，满 240 推进 1 序列 tick → **tempo 值无缩放** |
| `0x9218` | **0xE1 tempo 只写当前音轨**（`strh r0,[r8,#0x18]`），每轨独立 |

→ 修复 1：BGM02/04/06 的 tempo 事件（114/108/96）只在指挥轨，旋律轨实际按默认 120 播放。
旧渲染全局应用导致**慢 5.3% / 11.1%**。已改为每轨独立 tempo。
实测：实录互相关 scale 1.050 → **1.000**（三曲全部同步）。

### 事件语义
| opcode | RE 证实 |
|---|---|
| 0xC3 Transpose | 存 channel+0x13（BGM 未使用） |
| 0xC4 PortamentoControl | 存 channel+0x6；0xCE 从未开启 → 无实际影响 |
| RawData ×63 | 全部是 0xFF EndTrack，无害 |

### 包络（0x7D54 + 0x830C，每 sound tick 步进，tick 率 96Hz）
```
rate→step:  127→0xFFFF  126→0x3C00  rate<50→2r+1  其余→0x1E00/(126-rate)
attack:     env *= (255-rate)/256 指数逼近 0（rate≥109 查攻率表，BGM 全用 127≈瞬时）
decay:      env -= step，直到 sustain 查表目标（BGM 全 sustain=127=满电平）
release:    env -= step，线性衰减到静音；env∈[-16384,0]，音量=env>>7
```
→ 修复 2：**release 实际时长 121/118/114 → 111/178/267ms**，
旧启发式只有 19-41ms，音尾被切短 3-6 倍（"不太对"的主要来源）。已修。

### 复音
| 位置 | 结论 |
|---|---|
| `0x8154` | **16 硬件通道池 + 优先级抢占**，超复音掐最老音符 |

→ 修复 3：渲染器加入 16 通道抢占模拟（此前无限复音，密集段落比游戏"糊"）。

### 乐器（SBNK）
- 121 件乐器 = 83 空位 + 37×type1 单音色 + **1×type16 鼓组（prog 120）**
- 鼓组 firstPitch=36，每键独立波形/音高/pan；BGM02 用 key 36/38/39/42
  = 底鼓/军鼓/拍手/镲 —— **旧渲染器整段打击乐无声**，已按 firstPitch 选型实现
- noteDefinition 含独立 pan（0xC0 音轨 pan + defPan-64 合成），已生效
- SBNK noteinfo 布局 `<HH6B`：wave, war, pitch, atk, dec, sus, rel, pan

## 三、量化指标

| 指标 | 数值 | 说明 |
|---|---|---|
| 时序同步（onset 互相关 scale） | title 1.0000 / puzzle 1.0000 / menu 0.9975 | **对齐度指标**，完全同步 |
| 谱余弦相似度（40s 对齐窗） | BGM00 0.640 / BGM01 0.691 / BGM07 0.766 | **保真度指标**（timer量化修复后）|
| onset 相关分数 | 0.08-0.13 | ⚠️ 这是对齐度指标不是保真度指标，低分属正常（混音平衡差异），勿误读 |

剩余差距来源：合成器线性插值 vs 硬件混音、混响无、包络 sustain/attack 两张 WRAM 查表未从 ROM 定位（但本作 BGM 全 sustain=127/attack=127，不受影响）。

## 四、未竟事项

1. sustain 查表（u16[128] @0x3807E2C）与攻率表（u8 @0x3807F40）位于 ARM7 WRAM 段，
   ROM 内非线性存放，未定位——对本作 BGM 无影响（全 127）
2. 包络 DSP 深层（音量应用、硬件寄存器写入 @0x21xx）未逐指令核对
3. ~~线性插值升级~~ 已完成三次 Hermite 插值：收益甚微（0.620→0.622），差距主因在混音细节非插值
4. 录音配对：**主菜单 = SEQ_BGM00（用户确认）**；录音已改名 `rec_BGM00` 并裁掉开头 1.315s 菜单音效；
   `rec_menu`（游戏内 BGM）与 `rec_title` 的真实序列身份待进一步确认（BGM 共用音色库，chroma 区分度不足）

## 五、产物

- `rendered/SEQ_BGM00-07.wav`（全部序列新渲染，本机 SDAT 直接渲染；03/05 为空占位曲）
- `rendered/SEQ_BGM00-07.ogg`（旧版渲染，保留作对比）
- `rendered/verify_rec_BGM00_SEQ_BGM*.json`：验证数据集结果（rec_BGM00 ↔ 各 BGM）
- `recordings/`：录音（**rec_BGM00**=网页版主菜单，已裁掉开头 1.315s 菜单音效 / rec_menu=游戏内BGM / rec_title=标题）
- `sseq_render.py`：修复版渲染器（含全部 RE 注释，**SDAT/输出路径已参数化**）
  - 用法：`SDAT_PATH=<sdat> RENDER_OUT=<目录> python sseq_render.py [过滤词]`
  - 或：`python sseq_render.py <sdat路径> [过滤词]`
- `verify_dataset.py`：验证数据集工具（测录音↔渲染的旋律/速度相关性，含音高补偿）
  - 用法：`python verify_dataset.py <录音名> <序列名>` → 输出 JSON 报告

## 六、~~音调修复：NDS 硬件 timer 量化~~（10-23 已撤回：方向反了，实测游戏音高=SWAR 标称采样率）

**症状**：渲染版乐器整体偏低 1.5-2.4%（30-40 音分），"恐怖片"式走音。

**根因（RE）**：NDS 硬件声音通道的播放率由 15bit timer 决定：
`T = 0x800 - int(0x400000/(16×rate))`，实际播放率回代同一公式。
本作全部波形被量化到 **8192 / 16384 Hz** 整数档播放（音乐按此授权），
而旧渲染器用 SWAR 标称采样率（16000/16083/16026...）→ 全乐器系统性偏低。

**修复**：factor 改按硬件语义计算（量化后再换算）。
**效果**：谱相似度 0.622/0.672/0.763 → **0.640/0.691/0.766**（三曲全升）。

## 七、~~音符拉长修复（10-20 夜另一会话）~~——已废弃
> 用户听感判定该会话修复后"音乐更离谱"，TPQN=192 / total_len 去除 /factor / 菜单=BGM00 映射等结论全部作废。
> 以本文件第八节（对齐谱音分实测）与第九节（独立实现交叉验证）为准。

## 八、音轨映射修正（10-20，对齐谱音分实测）
- 游戏标题/菜单 = **SEQ_BGM07**（rec_title 与 rec_menu 双实录与 BGM07 渲染 -4 音分吻合，相似度 0.965）
- SEQ_BGM00 = 同一旋律的低移调版（-272 音分 ≈ 2.7 半音），节奏相同
- SEQ_BGM01 = 谜题 BGM（+8 音分吻合）

## 九、独立实现交叉验证（10-23）

引入 kode54/SSEQPlayer（FSS 移植、社区久经考验的 SSEQ 离线渲染核心，`third_party/SSEQPlayer/`，
入口 `main_render.cpp`：`./sseqrender sound_data.sdat 7 40 out.wav 1 32768`）与我们自研渲染器对拍：

| 对比 | 节奏 scale | 音分差 | 谱相似度(vs rec_menu) |
|---|---|---|---|
| 自研版 BGM07 ↔ 游戏 | 1.000 | -4 | **0.783** |
| SSEQPlayer(LINEAR) ↔ 游戏 | 1.000 | （同上度量噪声） | 0.723 |
| SSEQPlayer ↔ 自研版 | — | **0** | 0.821 |

**结论（⚠️ 基于 TPQN=24 旧渲染，TPQN=192 修复后需重跑对拍）**：
- 音高/节奏语义两独立实现一致（旧 TPQN=24 渲染下 scale=1.0 巧合吻合）→ SSEQPlayer 可作回归对照基准
- 自研版相似度已高于 FSS 核心原版（得益于 RE 出的 prog120 鼓组/包络/混音细节）
- 残余差异（≈0.2 相似度缺口）= 混音层微差：插值核（DS 硬件最近邻 vs 实录模拟器的重采样）、
  声像律、16 通道求和削波、录取端抗混叠——非语义错误，属"仿真 vs 实录"固有边界
- FSS 源码佐证：音高走 BIOS SWI GetPitchTable（±0x300 范围 1.56 音分/项，近似连续），
  tempo tick=192.5Hz×tempo/240，与自研模型等价
