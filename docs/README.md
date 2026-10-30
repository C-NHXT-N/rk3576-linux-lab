# 跟着学：课程总目录

先阅读[环境说明](environment.md)，从第一课顺序学习。时间估计包含独立练习，安装依赖和准备外设可能另需时间。

1. [00-1 从电脑连接到开发板](00-start/01-connect.md)
2. [00-2 读懂命令、查帮助与编辑文件](00-start/02-help-editor.md)
3. [01-1 你在哪里：目录与路径](01-files/01-paths.md)
4. [01-2 创建、查看、复制、移动和删除](01-files/02-file-operations.md)
5. [01-3 Linux 目录各自负责什么](01-files/03-directory-map.md)
6. [01-4 文件类型、权限与链接](01-files/04-types-permissions.md)
7. [01-5 一棵目录树，多种文件系统](01-files/05-mounts-interfaces.md)
8. [02-1 输入输出、变量与退出状态](02-shell/01-streams-variables.md)
9. [02-2 处理文本，完成第一版巡检](02-shell/02-text-report.md)
10. [02-3 判断、循环、函数与参数](02-shell/03-control-flow.md)
11. [03-1 CPU、内存与系统负载](03-process/01-system-observation.md)
12. [03-2 进程、作业与信号](03-process/02-jobs-signals.md)
13. [04-1 综合项目：逐步完成系统巡检](04-services/01-inspector.md)
14. [04-2 从一次报告到持续监控](04-services/02-monitor.md)
15. [04-3 接口、地址、路由和监听端口](04-services/03-network.md)
16. [04-4 用 systemd 管理监控服务](04-services/04-systemd.md)
17. [05-1 从 C++ 源码到 Linux 进程](05-programming/01-build-process.md)
18. [05-2 文件描述符、write 与系统调用](05-programming/02-fd-strace.md)
19. [05-3 管道通信与共享内存](05-programming/03-ipc-memory.md)
20. [06-1 从启动链到设备树和驱动](06-hardware/01-boot-devices.md)
21. [06-2 摄像头、温度与 NPU 的可用性检查](06-hardware/02-camera-npu.md)
22. [07-0 RKNN 板端环境搭建与首次推理](07-rknn/00-environment.md)
23. [07-1 YOLO26n 模型转换与 INT8 量化](07-rknn/01-conversion.md)
24. [07-2 YOLO26n 静态图片检测项目](07-rknn/02-inference.md)
25. [08-1 交付可维护的视觉推理服务](08-deployment/01-vision-service.md)

## 如何选择路线

- Linux 零基础：按上面的顺序学习，保留自己的脚本和观察记录。
- 已会基本操作：按[知识点索引](knowledge-index.md)检查缺口，再从综合巡检进入项目。
- 没有摄像头：先完成基础课程与静态图像路径，相机实验明确保留待验证项。

文字已编写不等于硬件验证完成。[学习路线](roadmap.md)标明边界，[验证记录](validation.md)列出实际证据和缺口。
