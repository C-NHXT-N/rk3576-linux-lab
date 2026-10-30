# 实验验证记录

[课程目录](README.md) · [环境](environment.md) · [路线图](roadmap.md)

## 初次基础课程验证环境（2026-10-30）

| 项目 | 实际值 |
|---|---|
| 板型 | LubanCat-3 / RK3576 |
| 系统 | Ubuntu 22.04.5 LTS，镜像 BUILD_INFO 日期 2025-01-15 |
| 内核/架构 | 6.1.99-rk3576 / aarch64 |
| Python | 3.10.12（系统解释器） |
| C++ 编译器 | g++ 11.4.0 |
| strace | 5.16 |
| 课程起始代码 | b706e4e；本次改动尚未提交 |
| 既有服务 | rk3576-monitor 已运行；验证使用其他课程实例，不停止或覆盖既有 unit |
| Python 依赖 | 系统 Python 未安装 numpy、cv2、rknnlite、rknn |
| 可见视频节点 | video-dec0、video-enc0；未确认物理摄像头捕获节点 |

## 结果

| 检查 | 结果与证据 |
|---|---|
| Markdown | 38 个文件的本地链接、标题锚点、围栏与课件结构检查通过；不包含外部 URL 可达性 |
| Shell | 所有课程 .sh 的 bash -n 通过 |
| 自动回归 | 板端 8 项测试：有限采样/参数、报告分段、传感器异常、TERM 子进程清理、配置路径、无效配置、健康状态、缺依赖时撤销旧健康状态 |
| 基础工具 | environment 检查 11/11 通过 |
| 文件五课核心实验 | 绝对/相对路径、复制比较、符号/硬链接、640 权限及清理；files 检查 4/4 通过 |
| 文件系统 | 确认根为 /dev/mmcblk0p3 ext4；/proc=proc、/sys=sysfs、/dev=devtmpfs |
| 巡检报告 | inspector 检查 8/8 通过，身份/CPU/内存/存储/进程/网络/设备均有输出 |
| 温度与采样 | 真实 SoC/NPU 温度可读；夹具验证缺失、无效、不可读、零值、负数及任意 zone 编号，不修改真实 sysfs |
| C++ | 四个示例以 C++17、-Wall -Wextra -Werror 构建通过；programming 检查 3/3 通过 |
| 进程生命周期 | 新构建 process_lab 的 PID/PPID、exe 链接、30 秒正常退出完成观察 |
| 系统调用 | strace 确认 write(1, ..., 18)=18；pipe 与 mmap 带子进程追踪完成 |
| 回环网络 | 临时 127.0.0.1:8766 服务请求返回 200，实验结束终止并回收 |
| 监控 systemd 实例 | 独立 rk3576-monitor-check.service：状态检查 3/3，KILL 后 PID 从 922441 变为 922474，日志可见恢复，enable 关系与正常 TERM 停止通过 |
| 服务清理 | 临时 unit 及 enable 链接移除；原 rk3576-monitor 保持 active，MainPID=702 未变化 |
| 硬件只读观察 | model=EmbedFire LubanCat-3，compatible 包含 embedfire,rk3576-lubancat-3 与 rockchip,rk3576 |
| 视觉代码基础行为 | 配置/路径/心跳与缺依赖失败处理通过；不是模型或 NPU 测试 |

可重复的通用检查命令：

```bash
python3 tools/check_docs.py
find . -name '*.sh' -not -path './.git/*' -print0 | xargs -0 -r -n1 bash -n
bash tools/build_labs.sh
python3 -m unittest discover -s tests -v
python3 tools/check_lab.py environment
python3 tools/check_lab.py inspector
python3 tools/check_lab.py programming
```

个人运行产物位于板端 run/verified-write.trace、run/verified-pipe.trace、run/verified-mmap.trace、run/verified-process.txt，未提交仓库。监控生命周期可按服务课在自己的 -lab 实例重现，不重用本记录中的历史 PID。

systemd-analyze verify 还输出了镜像中其他既有 unit 的提示（netplan、bootanim、snapd、rkaiq），本轮没有顺带修改这些系统文件。视觉模板的可执行文件检查如实失败：板端尚未安装项目 .venv，不能将此项记录为成功。

## YOLO26n 新增实测

环境、FP16/INT8 转换、18 次静态图 NPU 推理及误差对照见[YOLO26n 记录](yolo26-validation.md)。原表为基础课程建设时的记录，后续项目环境不等于系统 Python。

## 明确尚未验证

- 摄像头图像采集：未确认已接入可用的物理捕获设备。
- enable 后跨重启行为：本轮不重启整块设备。
- 新手独立完成效果与 20—40 分钟时长：需要真实读者试读反馈，不能由作者自评宣布通过。

## 后续实测填写模板

```text
日期 / 验证人：
代码 commit：
板型 / 镜像 / 内核 / 架构：
解释器 / wheel / Toolkit / Runtime / 驱动版本：
上游仓库 commit / 模型与输入来源及 SHA256：
实验命令 / 当前目录 / 运行用户：
预期 / 实际结果 / 退出码 / 原始日志位置：
正常分支 / 缺失与失败分支 / 清理后状态：
已通过 / 失败 / 待验证及原因：
```

结果文件只含非敏感信息；模型权重和依赖环境不提交仓库。硬件接口、SDK 与模型以所记录版本为准，更新时重新验证相关链路。
