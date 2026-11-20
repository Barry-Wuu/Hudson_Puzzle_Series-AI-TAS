# むずかしい 合并版 / 公网直链 —— 归档工具（2026-11-19）

本目录归档本次「两个新合并版 + 公网直链」的可复现工具与清单。成品 mp4 不入库
（`/workspace/投稿合并版/`），这里只放脚本与 concat 清单。

## 一、两个合并版

| 成品 | 构成 | 时长 | 大小 |
|---|---|---|---|
| `07_むずかしい1-30_混合提速版_libx264防花屏.mp4` | 1~17 提速版(24x14) + 18~30 旧版(36x20) | 112.8 分 | 284 MB |
| `08_むずかしい31-50+认定_libx264防花屏.mp4` | 31~50 旧版(36x20) + 48s 认定 | 121.6 分 | 309 MB |

提速版来自 `vol5_recordings_muzukashii_24x14_fast`，旧版来自 `vol5_recordings_muzukashii_36x20`
（与旧上传合并版 05 时长吻合，差 0s，证实是同一套）。认定用 `06_段位认定_完整流程_含正解.mp4`（48.17s）。

## 二、合并命令（libx264 防花屏，固定 2s GOP）

```bash
/usr/bin/ffmpeg -f concat -safe 0 -i concat_1-30.txt \
  -c:v libx264 -g 60 -keyint_min 60 -sc_threshold 0 -crf 18 -preset veryfast \
  -pix_fmt yuv420p -c:a aac -b:a 128k -movflags +faststart \
  -y '/workspace/投稿合并版/07_むずかしい1-30_混合提速版_libx264防花屏.mp4'
# 31-50+认定 同理，输入改 concat_31-50_nintei.txt
```

必须用 `/usr/bin/ffmpeg`（有 libx264）；`/usr/local/bin/ffmpeg` 无 libx264 会失败。

## 三、验收工具

```bash
python3.11 verify_merge.py <视频1> <视频2>
# 输出：时长/大小/分辨率、解码错误数、最大GOP、首尾帧截图
```

本轮实测两版均：解码错误 0、最大 GOP 2.00s、关键帧 3385/3650 个，花屏不复现。

## 四、公网直链

- 发布：`node /root/.codebuddy/skills/sites/scripts/publish.js --dir /workspace/muzu_publish --language python --start-cmd 'python3.11 /workspace/muzu_publish/server.py'`
- 链接（复用账号固定链接，**会覆盖**同链接旧内容）：
  `https://ac8a1c5bb2ca8017b.app.workbuddy.host/?sharecode=GCQ2OVAP3X`
- 视频直链：`<链接根>/muzu_1-30.mp4?sharecode=GCQ2OVAP3X` 与 `muzu_31-50_nintei.mp4?...`
- `server_range.py` 是带 Range（断点续传）的静态服务，避免大视频在线播放被截断；监听 `$PORT`、绑定 `0.0.0.0`。
- **已知运维点**：沙箱休眠/重连后发布通道 runtime 绑定会失效，公网返回 000/504，
  本地服务仍正常。重跑上面发布命令重绑即可，链接不变。排查时 `curl` 走代理会假报 000，用 `curl --noproxy '*'` 测本地。
