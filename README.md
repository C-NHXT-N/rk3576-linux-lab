# RK3576 + Linux：从零基础操作到边缘视觉服务

面向会一点编程、Linux 零基础的学习者。保留“老师带着做”的节奏，同时用明确的先修关系连接知识；每课都有预测、操作、独立任务、分层提示、验收和清理。

**开始学习：[课程总目录](docs/README.md)** · **随时查：[知识点索引](docs/knowledge-index.md)**

## 学习前准备

- 一块运行 Linux 的 RK3576 开发板、一台可通过 SSH 连接它的电脑。
- 先阅读[环境说明](docs/environment.md)；用户名、IP 和路径使用自己的实际值。
- 课程命令默认在板端 Bash 执行；电脑端和转换主机命令会单独标注。
- 完成清单属于自评，本地检查工具验证可观察结果，二者都不能替代独立理解。

## 一条主线，逐步交付

| 阶段 | 形成的能力 | 成果 |
|---|---|---|
| 0 连接开发板 | SSH、帮助、编辑与执行 | 能独立开始实验 |
| 1 文件与目录 | 路径、操作、目录职责、权限、链接、挂载 | 完整的文件系统基础认识 |
| 2 Shell 与文本 | 引号、流、变量、管道、判断、循环、函数 | 第一版身份巡检 |
| 3 进程与系统观察 | CPU、内存、负载、PID、作业、信号 | 有证据地观察系统 |
| 4 服务与网络 | 综合巡检、监控、接口、端口、systemd、日志 | 可管理的监控服务 |
| 5 系统编程 | 编译、系统调用、描述符、进程、管道、映射 | 四个可运行 C++ 实验 |
| 6 RK3576 硬件 | 启动链、设备树、驱动、节点、相机、NPU 边界 | 硬件与依赖检查记录 |
| 7 RKNN 视觉 | 模型转换、预处理、推理与后处理 | YOLO26n 静态图片目标检测 |
| 8 工程化部署 | 配置、日志、健康、恢复、性能 | 受 systemd 管理的视觉服务 |

**YOLO26n 转换、FP16/INT8 静态图片 NPU 推理和临时服务生命周期已实测**。INT8 部分框偏差明显，默认使用 FP16；摄像头和跨重启部署尚未实测。完整结果与边界见[验证记录](docs/yolo26-validation.md)。

## 保留的项目入口

- [系统巡检](01-system-inspector/README.md)：从身份信息逐步增加系统观察。
- [systemd 监控](02-systemd-monitor/README.md)：有限采集、温度缺失处理、信号与生命周期。
- [Linux 系统编程](03-linux-system-programming/README.md)：process、write、pipe 与 mmap。
- [RKNN 视觉参考项目](04-rknn-vision/README.md)：静态图片 → 量化对比 → 服务。

## 在板上检查

先在仓库根目录运行，详细含义见对应课程：

```bash
python3 tools/check_docs.py
bash tools/build_labs.sh
python3 -m unittest discover -s tests -v
python3 tools/check_lab.py inspector
python3 tools/check_lab.py programming
```

文件与服务等检查入口见[工具说明](tools/README.md)。课程服务统一使用带 `-lab` 的名称，避免覆盖原有业务服务。源码模板必须先渲染，不能直接安装。

贡献前阅读[写作与验证规范](CONTRIBUTING.md)。后续专题与建设状态见[路线图](docs/roadmap.md)。本仓库当前只使用 Markdown，没有网站构建或发布流程。


## 开源协议

原创代码与代码示例采用 **AGPL-3.0-only**，原创教程正文采用 **CC BY-SA 4.0**。允许按许可进行商业或非商业使用；文档转载/改编需署名并按相同方式共享。详见[许可范围](LICENSING.md)、[代码许可](LICENSE)、[文档许可](LICENSE-DOCS)和[第三方声明](THIRD_PARTY_NOTICES.md)。模型、SDK、Runtime、数据集和外部照片不随源码发布，仍受上游各自条款约束。
