# 04-4 用 systemd 管理监控服务

> 建议时间：20—40 分钟（含独立练习） · 状态：已编写；验证范围见环境记录
>
> 执行位置：除特别标注外，均为 **RK3576 的 Bash 终端**。普通用户执行；带 `sudo` 的步骤才需要管理员权限。
>
> 环境：先按[环境说明](../environment.md)设置 `RKLAB_ROOT`。先修课见页尾“上一课”；首次阅读从课程总目录开始。

## 这课完成什么

- 能部署自己的课程 unit，查看日志并区分 active/enabled。
- 能验证正常停止、异常恢复和配置变更。

## 跟着做：解释、预测、操作、观察


### 1. 明确谁在管理谁

```bash
ps -p 1 -o pid,ppid,user,comm
systemctl status ssh --no-pager
systemctl cat ssh
```

本课程 Ubuntu 中 PID 1 为 systemd；systemctl 是请求服务管理操作的客户端。只查看 SSH，不停止它。journal 接收服务输出；用 journalctl 查询，不是读取当前终端的作业表。

### 2. 渲染适合当前用户和仓库路径的 unit

```bash
cd "$RKLAB_ROOT"
mkdir -p run
python3 tools/render_service.py --project monitor > run/rk3576-monitor-lab.service
cat run/rk3576-monitor-lab.service
systemd-analyze verify run/rk3576-monitor-lab.service
```

源码中的 [unit 模板](../../02-systemd-monitor/rk3576-monitor.service) 含占位符，不能直接复制安装。渲染器只输出文本，不做安装。课程要求仓库绝对路径不含空格等特殊字符；不符合时渲染器会明确拒绝。

`[Unit]` 描述服务及依赖；`[Service]` 定义 Type、User、WorkingDirectory、ExecStart 与重启策略；`[Install]` 定义 enable 建立的启动关系。此程序无需 root，User 使用当前普通用户。ExecStart 显式调用 Bash，不依赖脚本执行位。

### 3. 安装自己的课程实例

使用独立名称 `rk3576-monitor-lab`，不覆盖原来的 rk3576-monitor 服务。如果该名称已经由别人使用，先检查来源，不覆盖。

```bash
sudo install -m 644 run/rk3576-monitor-lab.service /etc/systemd/system/rk3576-monitor-lab.service
sudo systemctl daemon-reload
sudo systemctl start rk3576-monitor-lab
systemctl status rk3576-monitor-lab --no-pager
sudo journalctl -u rk3576-monitor-lab -n 20 --no-pager
python3 tools/check_lab.py monitor
```

daemon-reload 重新读取 unit，本身不会启动或重启服务。服务启动后的工作目录和运行身份来自 unit，不是当前 SSH 会话的目录或环境变量。

### 4. 区分查看日志与控制程序

```bash
sudo journalctl -u rk3576-monitor-lab -f
```

按 Ctrl+C 退出日志跟踪，再执行 `systemctl is-active rk3576-monitor-lab`：服务应仍为 active，因为结束的是 journalctl。

### 5. 验证异常恢复

**先预测：** 主进程被 KILL 后，新 PID 应与旧 PID 相同吗？

```bash
old_pid=$(systemctl show rk3576-monitor-lab -p MainPID --value)
printf 'old=%s\n' "$old_pid"
sudo systemctl kill --kill-who=main --signal=KILL rk3576-monitor-lab
sleep 4
systemctl show rk3576-monitor-lab -p MainPID -p NRestarts -p ActiveState
sudo journalctl -u rk3576-monitor-lab -n 20 --no-pager
```

限定对自己的课程服务发送信号，不对抄写的未知 PID 操作。Restart=on-failure 对异常退出恢复，RestartSec=3 延迟重启。KILL 无 cleanup；正常 `systemctl stop` 通常发送 TERM，即使有重启策略，显式停止也不会因此自动重启。

### 6. enable 与 start，代码与配置

```bash
sudo systemctl enable rk3576-monitor-lab
systemctl is-enabled rk3576-monitor-lab
systemctl is-active rk3576-monitor-lab
```

start 现在启动，enable 建立后续启动关系，两者独立。此处仅验证配置，不为课程自动重启整块设备；跨重启验证需在有本地恢复通道时另行安排。

改脚本后 restart；改 unit 后重新渲染、安装、daemon-reload，再 restart。不要把模板已改但部署文件未更新误判成 systemd 缓存失效。

### 常见失败与综合排错

203/EXEC：检查解释器与路径；CHDIR：检查 WorkingDirectory；权限错误：用 User 的身份检查路径访问。用 journalctl 找最早的失败原因，修复后 restart；若触发启动频率限制，修复原因再 `sudo systemctl reset-failed rk3576-monitor-lab`。


## 自己完成一次

复制生成的 unit 到 run 下另一个草稿文件，只在草稿中把 ExecStart 路径写错，用 systemd-analyze verify 与逐项检查定位，再修复。为监控输出增加一个生成时间字段并按“改程序”流程部署。

<details>
<summary>提示一：先想方向</summary>

先区分源码、模板、生成文件和已安装文件。

</details>

<details>
<summary>提示二：关键工具</summary>

`cat`、`systemd-analyze verify`、`systemctl cat`、`journalctl`。

</details>

<details>
<summary>参考思路与解释（先尝试再展开）</summary>

不要故意破坏正在使用的服务。检查 ExecStart、WorkingDirectory 与文件权限；脚本变更重启即可，unit 变更必须安装并 daemon-reload。

</details>

## 完成标准

- [ ] 课程服务以普通用户运行且日志可查。
- [ ] 正常停止与异常恢复行为不同，恢复后 PID 更新。
- [ ] active 和 enabled 可以分别解释。
- [ ] 能正确部署脚本与 unit 两类修改。

勾选属于自评，不能替代实际结果。请保留命令与关键现象，并用自己的话解释一次。

## 清理与回顾

本课结束后移除自己安装的课程实例，保留原监控服务：

```bash
sudo systemctl disable --now rk3576-monitor-lab
sudo rm -- /etc/systemd/system/rk3576-monitor-lab.service
sudo systemctl daemon-reload
systemctl is-active rk3576-monitor-lab
```

最后可能输出 inactive 或 unknown 并非零退出，这是清理后的预期。journal 中历史记录不会因删除 unit 自动消失。

---

上一课：[04-3 接口、地址、路由和监听端口](03-network.md) · 下一课：[05-1 从 C++ 源码到 Linux 进程](../05-programming/01-build-process.md)

[课程总目录](../README.md) · [知识点索引](../knowledge-index.md)
