# 07-0 RKNN 板端环境搭建与首次推理

> 建议时间：20—40 分钟，首次下载与模型转换另计。执行位置按每一段标注；板端使用普通用户。
>
> 先按[环境说明](../environment.md)设置 RKLAB_ROOT。实测组合与限制见[验证记录](../validation.md)。

## 这课完成什么

完成本课的具体产物，能解释每步作用，并区分环境检查、实际推理与结果质量验证。


## 跟着做：先知道每层负责什么

这次直接使用 YOLO26n，检测整张图片中的目标并画框，不依赖摄像头。Toolkit2 在转换主机生成 RKNN；Lite 提供板端 Python 接口；Runtime 调用内核 NPU 驱动。

| 位置 | 本次实测组合 |
|---|---|
| 转换主机 | WSL2 Ubuntu 22.04 / x86_64 / Python 3.10.12 |
| 导出与转换 | Ultralytics 8.4.192 / torch 2.2.0+cpu / Toolkit2 2.5.0 / ONNX opset 17 |
| 开发板 | LubanCat-3 / Ubuntu 22.04.5 / aarch64 / Python 3.10.12 |
| 板端 SDK | Lite2 2.5.0 / 项目内 Runtime 2.5.0 / 原有驱动 0.9.8 |

本轮系统 /usr/lib/librknnrt.so 保持 2.1.0。可复现包清单见项目 requirements 文件，具体模型与 SDK 来源记录在验证页。

### 1. 板端：先检查，再建立虚拟环境

```bash
uname -m
python3 --version
cat /sys/module/rknpu/version
strings /usr/lib/librknnrt.so | grep -m 1 'librknnrt version'
cd "$RKLAB_ROOT/04-rknn-vision"
python3 -m venv .venv
```

**先预测：** Lite 可以导入，是否就证明 NPU 能运行？不能，还需真实模型初始化与推理。

实际遇到的 ensurepip 缺失可这样修复，再重新运行 venv：

```bash
sudo apt update
sudo apt install python3.10-venv
python3 -m venv .venv
```

### 2. 板端：下载并核对独立 SDK

```bash
python3 fetch_sdk.py --role board --output runtime
.venv/bin/python -m pip install -r requirements-board.txt
.venv/bin/python -m pip install runtime/rknn_toolkit_lite2-2.5.0-cp310-cp310-manylinux_2_17_aarch64.manylinux2014_aarch64.whl
.venv/bin/python -c 'import numpy, cv2; from rknnlite.api import RKNNLite; print(numpy.__version__, cv2.__version__)'
```

fetch_sdk 只下载固定官方文件并核对 SHA256，不安装，不复制到 /usr/lib。不要将 Android、x86_64 或其他 Python ABI 包放到这里。

本次 files.pythonhosted.org 下载很慢，临时指定 `--index-url https://pypi.tuna.tsinghua.edu.cn/simple` 后安装成功。仅在自己的网络确有需要时使用命令参数，不必修改全局 pip 配置。

### 3. 转换主机：为首次运行准备一个 FP16 模型

以下命令在 **WSL2 Ubuntu 22.04 的 Bash** 执行。RKLAB_ROOT 要设置成该环境看到的课程仓库路径，例如 /mnt/c/Lab/Linux-lab/rk3576-linux-lab，不能照搬 Windows 路径。虚拟环境放在 WSL 用户目录。

```bash
sudo apt update
sudo apt install python3-venv python3-pip libgomp1
mkdir -p ~/rk3576-convert
cd ~/rk3576-convert
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
python3 "$RKLAB_ROOT/04-rknn-vision/fetch_sdk.py" --role host --output runtime
.venv/bin/python -m pip install torch==2.2.0+cpu torchvision==0.17.0+cpu --index-url https://download.pytorch.org/whl/cpu
.venv/bin/python -m pip install -r "$RKLAB_ROOT/04-rknn-vision/requirements-host.txt"
.venv/bin/python -m pip install runtime/rknn_toolkit2-2.5.0-cp310-cp310-manylinux_2_17_x86_64.manylinux2014_x86_64.whl
.venv/bin/python "$RKLAB_ROOT/04-rknn-vision/export_model.py" --weights models/yolo26n.pt --output models/yolo26n.onnx
.venv/bin/python "$RKLAB_ROOT/04-rknn-vision/convert.py" --onnx models/yolo26n.onnx --output models/yolo26n-rk3576-fp16.rknn
```

这里只完成最小首次准备，下一课集中解释转换与量化。export_model 固定使用官方 YOLO26n 权重并核对 hash；不会把 n 换成 s。PyTorch 2.2 的导出器不能正确处理这里的 opset 19，实测改用 17 后成功。

下载配套静态图片，在 WSL 执行：

```bash
mkdir -p inputs
curl -fL https://raw.githubusercontent.com/ultralytics/ultralytics/v8.4.192/ultralytics/assets/bus.jpg -o inputs/bus.jpg
read -r -p '板端 user@实际IP: ' board_target
ssh "$board_target" 'mkdir -p ~/rk3576-linux-lab/04-rknn-vision/models'
scp models/yolo26n-rk3576-fp16.rknn inputs/bus.jpg "$board_target:rk3576-linux-lab/04-rknn-vision/models/"
```

如果板端仓库不在默认家目录，修改传输目标。不要将模型权重、SDK 二进制或个人地址提交 Git。

### 4. 板端：真正执行第一次 NPU 推理

```bash
cd "$RKLAB_ROOT/04-rknn-vision"
cp config.example.json config.json
bash run.sh --config config.json --check
bash run.sh --config config.json
cat run/vision/result.json
```

--check 不初始化 NPU。实际运行应在日志看到 Runtime 2.5.0、驱动 0.9.8，以及 Runtime mapped 指向项目 runtime/librknnrt.so。bus.jpg 实测检测到公交车与行人，标注图为 run/vision/result.jpg。

**一个重要实测问题：** Lite2 2.5 的编译模块固定使用系统库，仅设置 LD_LIBRARY_PATH 或环境变量不够。项目在当前进程内覆盖该固定版本的库路径解析方法，随后检查 /proc/self/maps；没有改 SDK 安装文件或系统库。如果换 SDK 版本，必须重新验证这一适配，不能假定接口稳定。

### 常见失败

| 现象 | 先检查 |
|---|---|
| ensurepip unavailable | 安装 python3.10-venv 后重建虚拟环境 |
| wheel not supported | Python ABI、aarch64/x86_64、是否选对安装角色 |
| 仍然输出 Runtime 2.1.0 | 是否运行课程入口，mapped 是否指向项目文件 |
| init_runtime 失败 | 模型 target、库版本、设备权限和驱动诊断 |
| Query dynamic range 警告 | 本模型为固定形状；以初始化返回、真实推理和输出验证判断 |
| 没有窗口 | 正常，本项目无 GUI，查看保存的标注图片 |


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

上一课：[硬件检查](../06-hardware/02-camera-npu.md) · 下一课：[模型转换与量化](01-conversion.md)

[课程总目录](../README.md) · [知识点索引](../knowledge-index.md)
