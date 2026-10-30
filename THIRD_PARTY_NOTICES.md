# 第三方来源与许可

## Ultralytics YOLO26

- 上游：https://github.com/ultralytics/ultralytics/tree/v8.4.192
- 许可：https://github.com/ultralytics/ultralytics/blob/v8.4.192/LICENSE （AGPL-3.0；另有上游商业授权渠道）
- 使用范围：export_model.py 调用上游 API 导出官方 YOLO26n；测试权重来自 Ultralytics assets v8.4.0。
- 权重、上游 Python 包与 bus/zidane 示例照片未包含在本次提交。其下载与再分发遵守各自适用条款，不能仅依据本仓库许可判断。

## Rockchip RKNN Model Zoo

- 上游固定 commit：837db8e992815ff8647eadb709f07067f4bc3a71。
- 来源：https://github.com/airockchip/rknn_model_zoo/tree/837db8e992815ff8647eadb709f07067f4bc3a71/examples/yolo26
- 上游许可：Apache License 2.0，完整文本保留在 [LICENSES/Apache-2.0.txt](LICENSES/Apache-2.0.txt)。上游权利归其作者及贡献者。
- 本项目 detector.py、convert.py 参照并适配了该示例的两路输出契约、预处理与 one-to-one 后处理流程；本地修改包括独立配置、输入校验、坐标还原检查、产物与生命周期管理。改动日期：2026-10-30。
- prepare_calibration.py 按固定上游清单下载 COCO20 子集。未将图片或数据集复制进发布目录；数据及照片权利不因 Model Zoo 的代码许可自动改变。

## Rockchip RKNN SDK

- 来源：https://github.com/airockchip/rknn-toolkit2/tree/v2.5.0
- 许可：https://github.com/airockchip/rknn-toolkit2/blob/v2.5.0/LICENSE （RKNN SDK License，包含专有条款，不能当作 Apache/MIT 开源许可）
- 使用范围：Toolkit2、Lite2、librknnrt.so 由使用者从上游下载和安装；fetch_sdk.py 仅核对固定文件哈希，未附带 SDK 文件。
- Runtime 适配只在当前进程内改变固定版本库解析，不修改 SDK 安装文件或系统库。遵守 SDK 原许可，本文不重新授权 SDK，也不授权逆向或移除上游声明。

## 通用依赖与标准协议

PyTorch、Torchvision、NumPy、OpenCV、ONNX、ONNX Runtime 及其他包均未随源码打包，继续遵循各自许可证。requirements 文件是依赖/验证记录，不是第三方软件的再许可。

AGPL、CC BY-SA 和 Apache 许可证正文是标准法律文本，分别保留原发布方声明。自有内容的许可范围见 [LICENSING.md](LICENSING.md)。
