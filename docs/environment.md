# 实验环境与执行约定

[课程目录](README.md) · [验证记录](validation.md)

## 谁执行哪一段命令

| 位置 | 用途 | 如何识别 |
|---|---|---|
| Windows PowerShell / 电脑终端 | SSH、文件传输 | 课文明示“电脑端” |
| RK3576 Bash | Linux 与板端实验 | 本课程默认位置 |
| 受支持的 Linux 转换主机 | RKNN Toolkit2 模型转换 | 课文明示“转换主机” |

本机终端与远端终端可能看起来相似；不确定时先检查 `hostname`、`uname -m`、`pwd`。命令块不含 `$` 提示符。示例输出中的用户名、PID、IP、分区编号不能直接作为操作目标。

## 设置仓库根目录

尚未获取仓库时，先完成[连接开发板与克隆仓库](00-start/01-connect.md)，再返回本页设置环境并检查工具。本页后面的相对路径命令均在仓库根目录执行。

默认仓库位于 `~/rk3576-linux-lab`。使用其他目录时把 cd 后的路径改成自己的路径：

```bash
cd ~/rk3576-linux-lab
export RKLAB_ROOT="$PWD"
test -d "$RKLAB_ROOT/docs" && printf 'Course root: %s
' "$RKLAB_ROOT"
```

每个新 SSH 会话重新设置 RKLAB_ROOT；它不是永久设置。渲染课程 unit 时要求仓库绝对路径只包含字母、数字、`_ . / -`，避免初学阶段混入 systemd 路径转义问题。渲染器会校验并拒绝其他路径。

个人操作练习放 `~/rk3576-practice`，源码实验产物放仓库 build，日志与临时配置放仓库 run。课程不要以 root 身份长期登录运行。

## 基础工具

```bash
python3 tools/check_lab.py environment
```

Ubuntu 22.04 缺少基础工具时，确认软件源可用后，按需安装：

```bash
sudo apt update
sudo apt install git build-essential python3 python3-venv nano man-db strace iproute2 procps util-linux file
```

这些步骤会安装软件，先看 apt 将变更哪些包。相机检查另外需要 v4l-utils；没有相机时不必为基础课程安装。RKNN 依赖单独在项目虚拟环境准备，按官方兼容矩阵选择，不能由本工具检查自动修复。

## 权限和状态约定

- 普通文件实验只操作自己的练习目录；系统目录以只读观察为主。
- 系统服务安装等命令明确带 sudo。使用 rk3576-monitor-lab、rk3576-vision-lab 作为课程实例。
- 不要求学习期间重启整块设备；enabled 只表示配置关系，跨重启行为单独实测。
- 没有传感器、相机或运行库时明确记录缺失；不能把 N/A 当 0 或把跳过当成功。
- 课程清理按具体对象执行；不提供无差别删除和清空系统日志的命令。

## 记录结果

每次硬件实验记录板型、系统镜像、内核、解释器和库版本，保留原始命令与输出。检查器只验证基本可观察结果，自评还需说明原因并完成变式任务。

遇到失败先查[排错索引](troubleshooting.md)。确认成功后再进入下一课，确实缺少外设的项目标注待验证。
