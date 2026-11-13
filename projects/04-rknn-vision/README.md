# 04 — YOLO26n 静态图片检测

本项目已在 RK3576 完成 FP16 与 INT8 真实 NPU 推理，不依赖摄像头。按[环境搭建与首次推理](../../07-rknn/00-environment.md) → [转换与量化](../../07-rknn/01-conversion.md) → [静态图片项目](../../07-rknn/02-inference.md) → [服务部署](../../08-deployment/01-vision-service.md)学习。

## 运行

```bash
cd "$RKLAB_ROOT/projects/04-rknn-vision"
cp config.example.json config.json
bash run.sh --config config.json --check
bash run.sh --config config.json
```

先按环境课准备项目 Runtime、虚拟环境、模型和图片。--check 不初始化 NPU。入口只使用真实 RKNN Lite；加载后核对 /proc 映射，防止误用系统旧库。

## 最终视频版

唯一交付配置为 YOLO26n FP16 640×640。我在板端用已部署的 B 版完成了白天、夜间两段视频的全片复验；各轮速度、画质验收和选型见[结项记录](../../docs/validation/rk3576-results.md)。板端的 `run/delivery/night.mp4` 和 `day.mp4` 是最近验收的两段 B 版成片。

从新克隆复验时，先完成模型转换课，将 FP16 的 `yolo26n-rk3576-fp16.rknn` 和同名 `.json` 转换清单放到板端项目的 `models/`。板端还需要教程环境中的 Python、项目 Runtime，以及 BSP 提供的 Rockchip MPP 库和开发头文件。用以下命令获取固定版本的 RKNN C API 头文件，并执行下文的原生库构建。

```bash
.venv/bin/python fetch_sdk.py --role header
```

头文件的来源和 SHA256 见[SDK 头文件说明](third_party/README.md)。如果板端无法访问 GitHub，可在电脑端的项目目录运行 `python fetch_sdk.py --role header`，再把下载的 `third_party/rknn_api.h` 复制到板端同一位置。原生构建会再次核对文件哈希。

准备两段 H.264、YUV420、1280×720、30 FPS、各 1050 帧的输入。结项记录给出了原素材链接和截取位置。假设你已从原页面取得素材并存成 `night-source.mp4` 和 `day-source.mp4`，可在有 FFmpeg 的机器上用下面的命令准备输入，再放到板端相同的相对路径。

```bash
mkdir -p run/video-input
filters='fps=30,scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p'
ffmpeg -i night-source.mp4 -vf "$filters" -frames:v 1050 -an -c:v libx264 run/video-input/test-720p30.mp4
ffmpeg -ss 10 -i day-source.mp4 -vf "$filters" -frames:v 1050 -an -c:v libx264 run/video-input/day-720p30.mp4
```

在板端用独立的 OpenCV 解码和 RKNN Lite 推理为这两段输入生成本地参考。已有参照会保留。新参照记录视频和模型的 SHA256，供复验检查。更换输入或模型时，把旧参照移出 `run/reference/` 后重新生成。

```bash
.venv/bin/python prepare_video_reference.py
```

在板端进入本目录，以下命令会在新目录中写入复验结果。

```bash
.venv/bin/python experiment.py verify --output run/verify-YYYYMMDD-HHMMSS
```

复验按同一配置完整处理昼夜各 1050 帧。输出目录中的 `final.json` 记录帧数、逐帧结果、EOS、缓冲归还及吞吐。

以下命令在板端重建原生库。

```bash
.venv/bin/python -c 'import cpu_preprocess,native_mpp,native_post,native_rknn,native_output; cpu_preprocess.build(); native_mpp.build(); native_post.build(); native_rknn.build(); native_output.build()'
```

板端的 FFmpeg 源码压缩包供离线重建。历次性能和质量对照见 [结项记录](../../docs/validation/rk3576-results.md)。
