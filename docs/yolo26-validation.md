# YOLO26n 实机验证记录（2026-10-30）

[课程总目录](README.md) · [首次推理](07-rknn/00-environment.md) · [总体验证](validation.md)

## 环境与真实执行范围

转换：WSL2 Ubuntu 22.04、Python 3.10.12、torch 2.2.0+cpu、torchvision 0.17.0+cpu、Ultralytics 8.4.192、ONNX 1.18.0、ONNX Runtime 1.23.2、Toolkit2 2.5.0。板端：LubanCat-3、Ubuntu 22.04.5、内核 6.1.99-rk3576、驱动 0.9.8、Lite2 2.5.0、NumPy 1.26.4、OpenCV headless 4.10.0。

板端原 /usr/lib/librknnrt.so 保持 2.1.0；通过进程内路径解析适配使用项目 Runtime 2.5.0，并核对 /proc/self/maps。仅设置环境变量或模块常量不足以改变该编译模块的固定路径。未更改 SDK 文件、内核和系统库。

权重来源：Ultralytics assets v8.4.0 的 yolo26n.pt。导出 batch=1、640×640、opset=17、dynamic=False、simplify=False、nms=False，CPU 执行。使用 Model Zoo commit 837db8e992815ff8647eadb709f07067f4bc3a71 的 YOLO26 输出约定及 COCO20 校准图片，校准前与推理同样 letterbox。完整主机依赖见项目 requirements-host-lock.txt。

## 结果对照

对同样两个中间输出使用相同预处理和后处理；ONNX 基准在 WSL CPU 执行。下面是每组重复三次后的最后一帧 NPU 调用耗时，不包含加载、解码、画框、写盘或节流等待，不是性能基准或视频 FPS。

高分参考目标指 ONNX confidence≥0.5 的目标，按同类别最大 IoU 匹配。这里只是少量样例一致性检查，不是 COCO mAP 或部署精度保证。

| 模型 | 图片 | ONNX/NPU 检测数 | 高分参考框最小 IoU | 最后一帧 NPU ms |
|---|---|---|---|---|
| FP16 | bus | 5 / 5 | 0.9976 | 44.452 |
| FP16 | zidane | 3 / 3 | 0.9944 | 49.934 |
| FP16 | blank | 0 / 0 | 不适用 | 43.300 |
| INT8 | bus | 5 / 5 | 0.6776 | 23.859 |
| INT8 | zidane | 3 / 3 | 0.7673 | 25.386 |
| INT8 | blank | 0 / 0 | 不适用 | 37.244 |

bus.jpg 为 810×1080，zidane.jpg 为 1280×720，验证两个方向的补边与原图坐标还原；blank.png 是生成的 800×360 纯黑图。公交车/行人主目标类别一致，空图两种模型都返回空列表并保存图像。每种模型每张图连续处理三次，共 18 次真实 NPU 推理。

**质量结论：** FP16 高分目标框与 ONNX 很接近；INT8 最低 IoU 分别约 0.678 和 0.767，部分框偏差明显。本次仅证明 INT8 转换和运行链路通过，不能标为检测精度达标。默认配置保留 FP16；使用 INT8 前需评估更有代表性的校准数据、量化误差及完整验证集。

独立 rk3576-vision-check 临时服务已验证持续真实推理、KILL 后自动恢复（PID 938282 → 938346）、正常 TERM 停止及 stopped 心跳；测试后移除 unit。原 rk3576-monitor 仍为 active、PID=702。没有执行整板重启。

## 产物 SHA256

| 文件 | SHA256 |
|---|---|
| yolo26n.pt | 9b09cc8bf347f0fc8a5f7657480587f25db09b34bf33b0652110fb03a8ad4fef |
| yolo26n.onnx | 61612d8cdf02cf97568751109e3d3b50e8ee01a29cbd16fc573b8255cd792f77 |
| yolo26n-rk3576-fp16.rknn | 24992fbdfb161f2380b67a58ac3b028d0832de5afd81868adaea987a278d4b24 |
| yolo26n-rk3576-int8.rknn | 3e0ac305ba3985e4a61666f16890139135f9284df35eff733fba8c773abb2cda |
| 项目 librknnrt.so | 4b6cc575bedf8952b13db4b1190fa3b3d2ac213f00be774ff6ccd19d651970c0 |

FP16 文件 10,134,849 字节，INT8 文件 7,812,136 字节。具体大小不能代替精度验证。

表中的 ONNX hash 对应首次转换所用文件。正式导出脚本也已单独执行通过；再次导出时文件路径、日期等元数据可能改变字节 hash，必须记录自己本次导出的实际值，不把字节完全相同作为模型语义一致的证明。

## 已遇到的问题与自动检查

- 板端缺 ensurepip，安装 python3.10-venv 后解决。
- 下载 NumPy 很慢，使用单次 pip 参数指定镜像后完成，不修改全局配置。
- PyTorch 2.2 的 opset 19 导出触发 ReduceMax axes 错误，固定为 17。
- Toolkit2 2.5 的 SDPA 融合触发 IndexError，按 SDK 建议只禁用该规则后转换通过。
- Lite 默认加载系统旧 Runtime，程序识别并拒绝；加入进程内解析适配后确认加载项目 2.5.0，真实推理通过。
- 静态图的 dynamic range 查询警告仍会出现；初始化及实际推理返回成功，记录原始日志，不把警告隐藏。
- 14 项回归覆盖既有脚本、配置迁移、坐标还原、形状、阈值、TopK、空输出、非有限数值、损坏图片、写入失败、释放与错误心跳。夹具不是硬件推理证据；上面的真实执行单独记录。

## 未完成项

摄像头未安装，未做采集验证；未重启整块板卡，未验证跨重启启动；未进行完整 mAP、代表性业务数据评估或长期稳定性测试。不要将 3 张图片的结果推广成精度或实时性能结论。
