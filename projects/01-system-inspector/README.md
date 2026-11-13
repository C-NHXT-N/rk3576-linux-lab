# 01 — 系统巡检项目

这里是系统巡检项目的完整源码。跟随课程从身份信息开始，逐步增加资源、进程、网络和设备观察。

先从[连接与编辑](../../00-start/01-connect.md)和[文件基础](../../01-files/01-paths.md)开始，再完成[第一版身份报告](../../02-shell/02-text-report.md)、[系统观察](../../03-process/01-system-observation.md)与[综合巡检](../../04-services/01-inspector.md)。

## 运行与增量学习

在仓库根目录执行：

```bash
bash projects/01-system-inspector/system_report.sh --section identity
bash projects/01-system-inspector/system_report.sh --section memory
bash projects/01-system-inspector/system_report.sh --section storage
bash projects/01-system-inspector/system_report.sh --section process
bash projects/01-system-inspector/system_report.sh --section network
bash projects/01-system-inspector/system_report.sh --section devices
bash projects/01-system-inspector/system_report.sh
python3 tools/check_lab.py inspector
```

memory 部分包含 CPU 与内存。默认输出全部模块；必需命令失败返回非零，可选设备缺失显示 N/A。网络与服务字段在[网络](../../04-services/03-network.md)和[systemd](../../04-services/04-systemd.md)课程集中解释。

源码：[system_report.sh](system_report.sh)。不要使用报告中的固定示例 PID/IP 作为其他操作目标；候选设备节点存在也不证明相机/NPU 可用。

程序只读系统状态，无需安装服务或清理设备。[总目录](../../README.md) · [知识索引](../../docs/reference/knowledge-index.md)
