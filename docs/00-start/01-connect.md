# 00-1 从电脑连接到开发板

> 建议时间：20—40 分钟（含独立练习） · 状态：已编写；验证范围见环境记录
>
> 执行位置：除特别标注外，均为 **RK3576 的 Bash 终端**。普通用户执行；带 `sudo` 的步骤才需要管理员权限。
>
> 环境：先按[环境说明](../environment.md)设置 `RKLAB_ROOT`。先修课见页尾“上一课”；首次阅读从课程总目录开始。

## 这课完成什么

- 能区分本机终端与远端 Shell。
- 能解释用户、主机名、内核和发行版之间的区别。

## 跟着做：解释、预测、操作、观察


### 1. 先知道命令会在哪台机器上执行

你的电脑通过 SSH 启动了开发板上的远程会话。电脑提供键盘和显示，命令通常由板上的 Bash 解释，程序在板上运行。Ubuntu 是包含内核、Shell、系统库与工具的发行版；RK3576 是硬件平台。

**先预测：** 连接前后运行查看系统的命令，结果应该相同吗？

在 **Windows PowerShell** 中，先把示例地址改成自己板卡的实际 IP。`192.0.2.10` 是文档示例地址，不能直接用于实验。

```powershell
$rkBoardAddress = '192.0.2.10'
$rkBoardUser = 'cat'
ssh "$rkBoardUser@$rkBoardAddress"
```

首次连接先按设备管理渠道核对主机指纹；随后输入自己的密码，输入时没有字符回显。教程不提供统一密码，也不要把密码写进仓库。

进入类似 `cat@lubancat:~$` 的提示符后，在 **开发板** 执行：

```bash
whoami
hostname
id
uname -r
uname -m
cat /etc/os-release
```

`whoami` 是用户，`hostname` 是主机名；UID/GID 是账户和组的数字身份。`uname -r` 是内核版本，`/etc/os-release` 是发行版信息，`aarch64` 表示 64 位 ARM 架构。实际值不必与作者设备一致。

### 2. 准备课程仓库

在开发板用户目录中执行。若已存在仓库，直接进入它，不必再次克隆。

```bash
cd ~
git clone https://github.com/C-NHXT-N/rk3576-linux-lab.git
cd rk3576-linux-lab
export RKLAB_ROOT="$PWD"
printf '%s\n' "$RKLAB_ROOT"
```

如果尚未推送作者的本次改动，GitHub 上的版本可能不同；请使用包含本课程目录的版本。每次重新登录都要按环境说明重新设置变量。

### 3. 根据错误判断连接到了哪一层

| 现象 | 先检查 | 下一步 |
|---|---|---|
| Could not resolve hostname | 主机名是否能解析 | 改用设备实际 IP，再单独排查名称解析 |
| Connection timed out | 地址、网络与访问路径 | 确认设备在线、电脑和设备网络可达 |
| Connection refused | 目标端口与 SSH 服务 | 通过串口或本机终端检查设备上的 SSH 服务 |
| Permission denied | 用户名与认证方式 | 核对账户和凭据，而不是反复更换网络命令 |

这些错误提示指向不同层次，不能统一解释为“密码错了”。


## 自己完成一次

新开第二个 SSH 会话，分别确认用户和主机名。解释为什么两次登录可以属于同一台主机，但不是同一个 Shell 进程。

<details>
<summary>提示一：先想方向</summary>

先区分账户、主机与一次登录会话。

</details>

<details>
<summary>提示二：关键工具</summary>

`whoami`、`hostname`、`echo $$`。

</details>

<details>
<summary>参考思路与解释（先尝试再展开）</summary>

同一账户可以登录同一主机多次。两次运行 `echo $$` 通常看到不同 PID；详细机制在进程课解释。

</details>

## 完成标准

- [ ] 记录实际用户、主机名、架构、内核、发行版。
- [ ] 能分清示例 IP 与自己的 IP。
- [ ] 能说明当前命令在电脑还是板上执行。

勾选属于自评，不能替代实际结果。请保留命令与关键现象，并用自己的话解释一次。

## 清理与回顾

第二个会话输入 `exit` 退出；主学习会话保持连接。不要把关闭 SSH 会话等同于关闭开发板。

---

上一课：[课程总目录](../README.md) · 下一课：[00-2 读懂命令、查帮助与编辑文件](02-help-editor.md)

[课程总目录](../README.md) · [知识点索引](../knowledge-index.md)
