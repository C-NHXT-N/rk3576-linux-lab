# RK3576 + Linux：从零基础操作到边缘视觉服务

这是我围绕 RK3576 开发板编写的 Linux 实践教程，面向会一点编程、Linux 零基础的学习者。我希望你能从独立操作开发板开始，逐步完成系统巡检、服务管理、C++ 系统编程和边缘视觉项目。

每课都有必要解释、动手操作、现象观察、独立练习、分层提示、验收和清理。教程正文按章节放在仓库根目录，完整源码放在 `projects/`，可以边学边对照。

**第一课：[从电脑连接到开发板](00-start/01-connect.md)** · **准备：[实验环境](docs/reference/environment.md)** · **随时查：[知识点索引](docs/reference/knowledge-index.md)**

## 学习前准备

- 一块运行 Linux 的 RK3576 开发板、一台可通过 SSH 连接它的电脑。
- 先完成连接与仓库克隆，再按[环境说明](docs/reference/environment.md)设置 `RKLAB_ROOT`；用户名、IP 和路径使用自己的实际值。
- 课程命令默认在板端 Bash 执行；电脑端和转换主机命令会单独标注。
- 没有摄像头也可以完成基础课程和静态图片推理。安装依赖、模型转换和准备外设可能另需时间。
- 已有 Linux 基础时，可以用[知识点索引](docs/reference/knowledge-index.md)检查缺口，再从综合项目开始。

## 课程总目录

我按下面的顺序组织课程。表格中的每个课程名称都可以直接打开对应课文。

| 阶段 | 课程 | 学完后能做什么 |
|---|---|---|
| 0 连接开发板 | [连接与克隆](00-start/01-connect.md) · [帮助与编辑](00-start/02-help-editor.md) | 独立连接开发板、读懂命令并编辑文件 |
| 1 文件与目录 | [目录与路径](01-files/01-paths.md) · [文件操作](01-files/02-file-operations.md) · [目录职责](01-files/03-directory-map.md) · [类型、权限与链接](01-files/04-types-permissions.md) · [挂载与接口](01-files/05-mounts-interfaces.md) | 管理练习文件，解释权限、目录和文件系统的关系 |
| 2 Shell 与文本 | [流、变量与状态](02-shell/01-streams-variables.md) · [文本报告](02-shell/02-text-report.md) · [控制流](02-shell/03-control-flow.md) | 编写第一版身份巡检，使用判断、循环和函数 |
| 3 进程与系统观察 | [CPU、内存与负载](03-process/01-system-observation.md) · [作业与信号](03-process/02-jobs-signals.md) | 结合系统证据观察资源，管理自己启动的进程 |
| 4 服务与网络 | [综合巡检](04-services/01-inspector.md) · [持续监控](04-services/02-monitor.md) · [网络观察](04-services/03-network.md) · [systemd 部署](04-services/04-systemd.md) | 完成巡检、监控和可管理的 Linux 服务 |
| 5 系统编程 | [构建与进程](05-programming/01-build-process.md) · [描述符与 strace](05-programming/02-fd-strace.md) · [IPC 与共享内存](05-programming/03-ipc-memory.md) | 编译并解释 process、write、pipe、mmap 四个 C++ 实验 |
| 6 RK3576 硬件 | [启动、设备树与驱动](06-hardware/01-boot-devices.md) · [相机与 NPU 检查](06-hardware/02-camera-npu.md) | 找到硬件接口，区分设备、驱动和应用依赖 |
| 7 RKNN 视觉 | [环境与首次推理](07-rknn/00-environment.md) · [转换与量化](07-rknn/01-conversion.md) · [静态图片检测](07-rknn/02-inference.md) | 完成 YOLO26n 模型转换和真实 NPU 图片推理 |
| 8 工程化部署 | [视觉服务](08-deployment/01-vision-service.md) | 管理配置、健康状态、故障恢复和性能观察 |

静态图片完成后，可以继续[视频复验](projects/04-rknn-vision/README.md#最终视频版)，对照[结项记录](docs/validation/rk3576-results.md)了解视频流水线和性能取舍。

我已在 RK3576 上完成 YOLO26n FP16/INT8 静态图片推理、临时服务生命周期及视频复验。INT8 部分框偏差明显，当前交付采用 FP16；摄像头和跨重启部署仍待验证。具体环境、结果和边界见[基础实验记录](docs/validation/validation.md)、[YOLO26n 实测](docs/validation/yolo26-validation.md)和[视频结项记录](docs/validation/rk3576-results.md)。

## 教程项目入口

项目 README 说明运行方式，课程负责逐步解释知识和实验过程。

| 项目 | 对应教程 | 源码入口 |
|---|---|---|
| [系统巡检](projects/01-system-inspector/README.md) | [文本报告](02-shell/02-text-report.md) → [综合巡检](04-services/01-inspector.md) | [system_report.sh](projects/01-system-inspector/system_report.sh) |
| [systemd 监控](projects/02-systemd-monitor/README.md) | [持续监控](04-services/02-monitor.md) → [服务部署](04-services/04-systemd.md) | [监控脚本](projects/02-systemd-monitor/rk3576-monitor.sh) · [服务模板](projects/02-systemd-monitor/rk3576-monitor.service) |
| [Linux 系统编程](projects/03-linux-system-programming/README.md) | [构建与进程](05-programming/01-build-process.md) → [IPC 与内存](05-programming/03-ipc-memory.md) | [process](projects/03-linux-system-programming/01-process-lab.cpp) · [write](projects/03-linux-system-programming/02-write-lab.cpp) · [pipe](projects/03-linux-system-programming/03-pipe-lab.cpp) · [mmap](projects/03-linux-system-programming/04-mmap-lab.cpp) |
| [RKNN 视觉](projects/04-rknn-vision/README.md) | [环境与推理](07-rknn/00-environment.md) → [视觉服务](08-deployment/01-vision-service.md) | [运行入口](projects/04-rknn-vision/run.sh) · [推理程序](projects/04-rknn-vision/vision.py) · [检测器](projects/04-rknn-vision/detector.py) |

## 目录说明

| 位置 | 用途 |
|---|---|
| 根目录的编号章节 | 教程正文，按上面的[课程总目录](#课程总目录)学习 |
| `projects/` | 四个教程项目的完整源码、配置示例和服务模板，见[教程项目入口](#教程项目入口) |
| [docs/](docs/README.md) | 环境、知识索引、排错、验证记录、维护和许可说明 |
| [tests/](tests/README.md) | 自动回归测试和测试夹具，用于检查脚本、配置、推理与视频处理逻辑 |
| [tools/](tools/README.md) | 文档检查、C++ 构建、实验成果检查和服务配置生成工具 |
| `build/`、`run/` | 本地构建产物、日志和临时结果，由命令按需创建，不提交仓库 |

## 检查与验证

在 Linux 环境的仓库根目录执行。自动测试的依赖与跳过条件见[测试说明](tests/README.md)。

```bash
python3 tools/check_docs.py
bash tools/build_labs.sh
python3 -m unittest discover -s tests -v
python3 tools/check_lab.py programming
```

在开发板上还可以按课程运行环境、巡检、监控和视觉健康检查，具体命令见[工具说明](tools/README.md)。自动测试和自评清单各有用途，真实 NPU、摄像头及服务部署要按课程单独验收。课程服务统一使用带 `-lab` 的名称，源码中的服务模板先渲染、审阅，再安装。

遇到问题先查[排错索引](docs/reference/troubleshooting.md)。后续专题和建设状态见[学习路线](docs/maintenance/roadmap.md)。已有旧目录环境时，请先阅读[迁移说明](docs/reference/environment.md#已有环境迁移)。

## 开源协议

原创代码与代码示例采用 **AGPL-3.0-only**，原创教程正文采用 **CC BY-SA 4.0**。允许按许可进行商业或非商业使用；文档转载、改编需署名并按相同方式共享。详见[许可范围](docs/licensing/LICENSING.md)、[代码许可](LICENSE)、[文档许可](LICENSE-DOCS)和[第三方声明](docs/licensing/THIRD_PARTY_NOTICES.md)。模型、SDK、Runtime、数据集和外部照片不随源码发布，仍受上游各自条款约束。
