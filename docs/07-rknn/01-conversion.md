# 07-1 YOLO26n 模型转换与 INT8 量化

> 建议时间：20—40 分钟，首次下载与模型转换另计。执行位置按每一段标注；板端使用普通用户。
>
> 先按[环境说明](../environment.md)设置 RKLAB_ROOT。实测组合与限制见[验证记录](../validation.md)。

## 这课完成什么

完成本课的具体产物，能解释每步作用，并区分环境检查、实际推理与结果质量验证。


## 跟着做：从一次成功到可解释的转换

先修是[环境与首次推理](00-environment.md)。本课命令在 **WSL 转换主机**执行，继续使用 ~/rk3576-convert/.venv。

### 1. 固定模型契约

| 项目 | 本项目约定 |
|---|---|
| 模型 | YOLO26n，官方 assets v8.4.0 权重 |
| 输入 | batch=1，RGB，640×640；ONNX 为 NCHW float32/255 |
| RKNN 输入 | NHWC uint8，除 255 由转换配置处理 |
| 目标 | rk3576，不能把 rk3588 文件直接当同一产物 |
| 输出节点 | /model.23/Sigmoid_output_0 与 /model.23/Mul_2_output_0 |
| 输出含义 | (1,80,8400) 类别分数与 (1,4,8400) xyxy 检测框 |

转换器检查输出节点和静态输入形状，不匹配明确失败。导出版本变化可能改变节点名，不能随便选择名字相近的分支。

### 2. 解释 FP16 转换

第一次运行的命令已集中在上一课。阅读[转换器](../../04-rknn-vision/convert.py)：config 指定 RGB 归一化，load_onnx 截取两个官方输出，build 生成目标计算图，export_rknn 保存产物。没有 dataset 时不量化。

本次 Toolkit2 2.5.0 的 SDPA 融合规则对该固定导出图触发 IndexError，SDK 日志建议禁用 `fuse_exmatmul_add_mul_exsoftmax13_exmatmul_to_sdpa`。代码只禁用这一条规则，不捕获失败后伪造模型；换版本需重新验证。

### 3. 准备校准数据，实际转换 INT8

```bash
cd ~/rk3576-convert
.venv/bin/python "$RKLAB_ROOT/04-rknn-vision/prepare_calibration.py" --output calibration
.venv/bin/python "$RKLAB_ROOT/04-rknn-vision/convert.py" --onnx models/yolo26n.onnx --output models/yolo26n-rk3576-int8.rknn --dataset calibration/dataset.txt
sha256sum models/yolo26n*.rknn
```

prepare_calibration 下载固定 Rockchip commit 的 COCO20 子集，保存来源与 hash；先按推理同样的黑边 letterbox 准备 640×640 图片，再写绝对路径列表。dataset 为空、路径失效时拒绝转换。不要把测试图片当成完整精度评估集，也不要把 20 张示例校准当成适用于任意业务的数据集。

**先预测：** 换一组不代表实际场景的校准图，程序仍可能成功导出吗？可以，但量化误差可能增加。导出成功与检测质量是不同验收项。

### 4. 对比三条路径

同样的输入与后处理比较 ONNX CPU、FP16 NPU 和 INT8 NPU。ONNX 基准也要取同样两个中间输出，不能拿已经经过另一套 TopK 的最终输出混作原始张量对比。

在转换主机生成参考结果：

```bash
cd ~/rk3576-convert
.venv/bin/python "$RKLAB_ROOT/04-rknn-vision/onnx_baseline.py" --onnx models/yolo26n.onnx --image inputs/bus.jpg --output run/onnx-bus.json
```

然后将两种 RKNN 模型传到板端，为每种模型复制配置，分别指定 model 与独立 output_dir，按推理课运行。逐项对比 JSON 中相同类别的框、置信度和目标数量；CPU 参考不是 NPU 通过证据。

本轮 bus、zidane、空图共六种 NPU 组合都通过；主目标类别一致。具体框差异、耗时与局限见验证记录，不能把 WSL CPU 与 NPU 测量直接当成公平硬件排名。

这里“通过”仅指转换与实际执行。INT8 部分框偏差明显，当前默认模型仍为 FP16；不要因调用更快就省略精度评估。查看[实测对照](../yolo26-validation.md)中的 IoU 结果。

### 排错

ReduceMax axes 错误先检查 opset 与 PyTorch；输出节点缺失检查导出版本；融合 IndexError 查第一处 SDK 诊断；INT8 失败检查校准列表与图片。不要通过更换系统驱动处理导出器错误。

参考：[固定 Model Zoo 示例](https://github.com/airockchip/rknn_model_zoo/tree/837db8e992815ff8647eadb709f07067f4bc3a71/examples/yolo26)。


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

上一课：[环境搭建](00-environment.md) · 下一课：[静态图片项目](02-inference.md)

[课程总目录](../README.md) · [知识点索引](../knowledge-index.md)
