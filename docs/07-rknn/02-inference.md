# 07-2 YOLO26n 静态图片检测项目

> 建议时间：20—40 分钟，首次下载与模型转换另计。执行位置按每一段标注；板端使用普通用户。
>
> 先按[环境说明](../environment.md)设置 RKLAB_ROOT。实测组合与限制见[验证记录](../validation.md)。

## 这课完成什么

完成本课的具体产物，能解释每步作用，并区分环境检查、实际推理与结果质量验证。


## 跟着做：从图片到可检查的检测结果

本课在 **RK3576** 执行，环境安装集中在[07-0](00-environment.md)，模型准备见[转换课](01-conversion.md)。无需摄像头，无需图形桌面。

### 1. 先读配置

```bash
cd "$RKLAB_ROOT/04-rknn-vision"
cat config.example.json
bash run.sh --config config.json --check
bash run.sh --config config.json
```

资源相对路径以配置文件所在目录为基准。model 指向 RKNN 文件，image 是静态图；frames=1 默认单次，0 为持续重复处理同一张图；interval 是处理间隔，不能当作模型极限 FPS。

score_threshold 默认 0.25，topk 默认 300，output_dir 默认 run/vision，health 默认 run/health.json。旧 labels、camera 配置会明确提示迁移；本主线固定 COCO80 类，不接受旧分类配置。

### 2. 逐段阅读源码

[detector.py](../../04-rknn-vision/detector.py) 负责预处理与后处理，[vision.py](../../04-rknn-vision/vision.py) 负责配置、NPU 生命周期和产物写入。

1. 解码 BGR 图片，按比例缩放并补黑边到 640×640。
2. 转 RGB，组织 uint8 NHWC；不在板端重复除以 255。
3. 在 NPU 上推理，读取类别分数与 xyxy 两路输出。
4. 对每个候选取最大类别，筛选置信度，再按分数取 TopK。官方 one-to-one 分支不额外执行传统 NMS。
5. 扣除 padding、除以缩放比例，裁剪到原图范围，画框并保存。

**先预测：** 直接把 810×1080 图片拉伸成正方形，再按 letterbox 还原坐标，会怎样？预处理和坐标逆变换必须使用同一个契约。

### 3. 输出与验收

- result.jpg：原图尺寸的标注图。
- result.json：包含 detections 列表，每项是 class_id、name、confidence、xyxy；还记录原图尺寸和分项耗时。
- stdout：每次检测的 JSON 行，SDK 初始化也可能输出自己的日志，机器处理优先读取 result.json。
- health.json：starting/running/stopped/error；单次完成为 stopped，不属于异常。

无目标输出空 detections，同时保存未画框的图片。结果保存失败不能更新成成功心跳。持续模式覆盖最新结果，不无限产生图片；同一输出目录只运行一个实例。

### 4. 自己调整阈值与模型

复制 config.json 到自己的配置，将 model 改为已传到板上的 INT8 文件，使用独立 output_dir，再比较结果。阈值提高通常减少低分框，但不会提高模型本身精度。

### 排错

图像无法解码先检查文件内容；分类张量或其他通道数先检查模型；非有限输出明确失败；输出目录不可写会非零退出。程序 finally 释放 Runtime，TERM/INT 正常停止，并检查实际映射库来自项目。


## 自己完成一次

换一张非正方形静态图片，先预测 padding 位置，再运行检测，检查类别、框的位置和结果文件。保留命令、图片来源与模型 hash。

<details>
<summary>提示一：方向</summary>

分别检查解释器、SDK、模型、图像预处理和输出解释，不把所有失败都归为驱动问题。

</details>

<details>
<summary>提示二：关键工具</summary>

使用 --check 检查配置与依赖，实际运行后查看 result.json、result.jpg 和日志中的 Runtime mapped。修改 image 后无需重新转换模型。

</details>

<details>
<summary>参考思路与解释</summary>

相同模型可接受不同尺寸的原图，但实际模型输入固定为 640×640；通过 letterbox 保持比例，再把框映射回原图。程序正常退出只证明执行结束，还要检查结果与预期是否一致。

</details>

## 完成标准

- [ ] 本课命令成功，记录版本、hash 与关键输出。
- [ ] 实际识别与标注图符合输入；空目标图片允许输出空列表。
- [ ] 能解释一次失败及定位方法，完成自己的变式。

勾选为自评，不代替真实 NPU 验证或数据集精度评估。

## 清理与回顾

有限推理自然退出；持续模式按 Ctrl+C 或发送 TERM。只清理自己创建的结果目录；保留模型和版本记录供下一课。退出虚拟环境用 deactivate，不删除或替换系统 Runtime。

---

上一课：[模型转换](01-conversion.md) · 下一课：[视觉服务](../08-deployment/01-vision-service.md)

[课程总目录](../README.md) · [知识点索引](../knowledge-index.md)
