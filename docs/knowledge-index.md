# 随时查：知识点索引

[跟着学](README.md) · [排错索引](troubleshooting.md)

“首次学习”提供当前阶段必需认识，“集中讲解”是主要解释位置，“再次应用”增加实践深度。引用同一篇课文，避免平行维护多个解释。

| 知识点 | 首次学习 | 集中讲解 | 再次应用 |
|---|---|---|---|
| 用户、主机、发行版与内核 | [连接](00-start/01-connect.md) | [连接](00-start/01-connect.md) | [巡检](04-services/01-inspector.md) |
| 帮助、参数与编辑器 | [操作入门](00-start/02-help-editor.md) | [操作入门](00-start/02-help-editor.md) | [文本报告](02-shell/02-text-report.md) |
| 根、家目录、当前目录、绝对/相对路径 | [路径](01-files/01-paths.md) | [路径](01-files/01-paths.md) | [服务工作目录](04-services/04-systemd.md) |
| 文件创建、复制、移动与删除 | [文件操作](01-files/02-file-operations.md) | [文件操作](01-files/02-file-operations.md) | [部署](08-deployment/01-vision-service.md) |
| /etc、/usr、/var、/tmp 等职责 | [目录地图](01-files/03-directory-map.md) | [目录地图](01-files/03-directory-map.md) | [systemd](04-services/04-systemd.md) |
| 权限、文件类型、链接、inode 初识 | [权限与链接](01-files/04-types-permissions.md) | [权限与链接](01-files/04-types-permissions.md) | [设备观察](06-hardware/01-boot-devices.md) |
| 设备、分区、文件系统、挂载 | [挂载](01-files/05-mounts-interfaces.md) | [挂载](01-files/05-mounts-interfaces.md) | [巡检](04-services/01-inspector.md) |
| /dev、/proc、/sys 整体关系 | [挂载与接口](01-files/05-mounts-interfaces.md) | [挂载与接口](01-files/05-mounts-interfaces.md) | [设备与驱动](06-hardware/01-boot-devices.md) |
| stdout/stderr、引号、变量、$()、$? | [流与变量](02-shell/01-streams-variables.md) | [流与变量](02-shell/01-streams-variables.md) | [描述符](05-programming/02-fd-strace.md) |
| grep、cut、awk、字段 | [文本处理](02-shell/02-text-report.md) | [文本处理](02-shell/02-text-report.md) | [监控](04-services/02-monitor.md) |
| if/for/while、函数、参数、算术 | [控制流](02-shell/03-control-flow.md) | [控制流](02-shell/03-control-flow.md) | [监控源码](../02-systemd-monitor/rk3576-monitor.sh) |
| CPU、available、缓存、load | [系统观察](03-process/01-system-observation.md) | [系统观察](03-process/01-system-observation.md) | [性能排查](08-deployment/01-vision-service.md) |
| PID/PPID、jobs/ps、后台、信号、trap | [进程](03-process/02-jobs-signals.md) | [进程](03-process/02-jobs-signals.md) | [systemd](04-services/04-systemd.md) |
| /proc/PID、进程生命周期 | [进程](03-process/02-jobs-signals.md) | [C++ 进程](05-programming/01-build-process.md) | [IPC 与回收](05-programming/03-ipc-memory.md) |
| sysfs 温度、按 type 查找 | [挂载与接口](01-files/05-mounts-interfaces.md) | [监控](04-services/02-monitor.md) | [硬件检查](06-hardware/02-camera-npu.md) |
| 接口、IP、路由、监听、回环地址 | [巡检](04-services/01-inspector.md) | [网络](04-services/03-network.md) | [部署边界](08-deployment/01-vision-service.md) |
| unit、User、WorkingDirectory、ExecStart | [监控](04-services/02-monitor.md) | [systemd](04-services/04-systemd.md) | [视觉服务](08-deployment/01-vision-service.md) |
| active/enabled、reload/restart、journal | [systemd](04-services/04-systemd.md) | [systemd](04-services/04-systemd.md) | [视觉服务](08-deployment/01-vision-service.md) |
| 编译、可执行文件、进程映像 | [脚本运行](00-start/02-help-editor.md) | [C++ 构建](05-programming/01-build-process.md) | [系统调用](05-programming/02-fd-strace.md) |
| 文件描述符、write、短写、strace | [标准流](02-shell/01-streams-variables.md) | [描述符](05-programming/02-fd-strace.md) | [pipe](05-programming/03-ipc-memory.md) |
| fork、pipe、waitpid、mmap | [进程观察](03-process/02-jobs-signals.md) | [IPC 与内存](05-programming/03-ipc-memory.md) | [后续专题](roadmap.md) |
| 启动链、设备树、驱动绑定 | [目录与接口](01-files/05-mounts-interfaces.md) | [硬件机制](06-hardware/01-boot-devices.md) | [相机/NPU 检查](06-hardware/02-camera-npu.md) |
| Toolkit2、Lite、Runtime、模型目标 | [NPU 检查](06-hardware/02-camera-npu.md) | [模型转换](07-rknn/01-conversion.md) | [板端推理](07-rknn/02-inference.md) |
| RGB/NHWC、letterbox、阈值、TopK、坐标还原 | [模型约定](07-rknn/01-conversion.md) | [推理链路](07-rknn/02-inference.md) | [服务](08-deployment/01-vision-service.md) |
| 配置、健康、故障恢复、性能指标 | [监控服务](04-services/04-systemd.md) | [视觉部署](08-deployment/01-vision-service.md) | [最终验收](validation.md) |
| RKNN 板端安装、私有 Runtime、首次检测 | [硬件检查](06-hardware/02-camera-npu.md) | [环境搭建](07-rknn/00-environment.md) | [YOLO26n 实测](yolo26-validation.md) |
