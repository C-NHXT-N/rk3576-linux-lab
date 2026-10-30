# 排错索引：先确认事实，再定位层次

[课程目录](README.md) · [知识点索引](knowledge-index.md)

先保存原始命令、当前位置、退出状态和错误输出。明确执行主机与账户；一次只改变一个条件。下表链接到原课文，不维护另一套完整知识解释。

| 现象 | 先检查 | 课程 |
|---|---|---|
| SSH 名称不能解析、超时、拒绝或认证失败 | 区分名称、网络、端口与凭据 | [连接](00-start/01-connect.md) |
| command not found、参数错误、编辑器退不出 | 拼写、command -v、帮助、q/Esc | [基本操作](00-start/02-help-editor.md) |
| No such file or directory | pwd、父目录、相对路径、大小写 | [路径](01-files/01-paths.md) |
| 文件名有空格、复制目标不对 | 引号、源与目标、已有文件 | [文件操作](01-files/02-file-operations.md) |
| Permission denied、链接失效 | id、父目录 x、文件权限、readlink | [权限](01-files/04-types-permissions.md) |
| df 与 lsblk 不一致 | 块设备与挂载关系 | [挂载](01-files/05-mounts-interfaces.md) |
| 看不到错误、退出码意外变成 0 | stderr 去向、立即保存 $?、pipefail | [流与状态](02-shell/01-streams-variables.md) |
| grep/awk 没有结果 | 先看原始输出、字段、语言环境 | [文本](02-shell/02-text-report.md) |
| 内存似乎不足、负载高 | available、CPU/进程/I/O 证据 | [系统观察](03-process/01-system-observation.md) |
| jobs 看不到进程、/proc/PID 消失 | 当前 Shell、PID、生命周期 | [进程](03-process/02-jobs-signals.md) |
| 温度为 N/A | type、路径、权限、原始数值 | [监控](04-services/02-monitor.md) |
| 服务启动但连接不到 | 监听地址、端口、本机请求、路由 | [网络](04-services/03-network.md) |
| unit 启动失败或配置不生效 | journal、User、路径、渲染/安装/reload/restart | [systemd](04-services/04-systemd.md) |
| C++ 编译或执行失败 | 首条编译诊断、build 路径、架构 | [构建](05-programming/01-build-process.md) |
| pipe 不结束 | 是否所有无用写端均关闭 | [IPC](05-programming/03-ipc-memory.md) |
| video 节点无法采集 | Capture 能力、格式、权限、占用 | [硬件检查](06-hardware/02-camera-npu.md) |
| 转换失败、Runtime 初始化失败 | 当前阶段、版本、目标、驱动、库 | [转换](07-rknn/01-conversion.md) |
| 推理运行但结果不合理 | 模型约定、颜色、布局、归一化、标签 | [推理](07-rknn/02-inference.md) |
| active 但没有近期结果 | 日志、输入、心跳时间、资源 | [部署](08-deployment/01-vision-service.md) |

提问时不要只贴“失败了”。提供可复现命令、版本、预期、实际、已检查事项；分享日志前去掉凭据和个人敏感信息。
