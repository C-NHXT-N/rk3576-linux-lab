# 04 — YOLO26n 静态图片检测

本项目已在 RK3576 完成 FP16 与 INT8 真实 NPU 推理，不依赖摄像头。按[环境搭建与首次推理](../docs/07-rknn/00-environment.md) → [转换与量化](../docs/07-rknn/01-conversion.md) → [静态图片项目](../docs/07-rknn/02-inference.md) → [服务部署](../docs/08-deployment/01-vision-service.md)学习。

## 运行

```bash
cd "$RKLAB_ROOT/04-rknn-vision"
cp config.example.json config.json
bash run.sh --config config.json --check
bash run.sh --config config.json
```

先按环境课准备项目 Runtime、虚拟环境、模型和图片。--check 不初始化 NPU。入口只使用真实 RKNN Lite；加载后核对 /proc 映射，防止误用系统旧库。

## 源码与产物

- fetch_sdk.py：固定 SDK 下载与 SHA256 校验，不安装。
- export_model.py：固定 YOLO26n 权重、Ultralytics 版本和 opset 17，CPU 导出。
- convert.py：固定 rk3576、640×640 和官方两路输出，--dataset 指定 INT8 校准列表，否则 FP16。
- prepare_calibration.py：固定 COCO20 来源、letterbox 和校准清单。
- detector.py：RGB/letterbox、one-to-one 阈值与 TopK、坐标还原及画框。
- vision.py：配置、真实 NPU、JSON/标注图、健康状态和资源释放。

默认结果为 run/vision/result.jpg、result.json，心跳为 run/health.json。有限处理结束为 stopped；持续模式只重复同一静态图片，不是实时视频。旧 labels/camera 配置需迁移，类别使用内置 COCO80。

真实环境、模型哈希、转换问题与测试限制见[验证记录](../docs/validation.md)。模型、SDK、虚拟环境和个人输出不提交 Git。相机和跨重启未验证，不属于当前通过项。
