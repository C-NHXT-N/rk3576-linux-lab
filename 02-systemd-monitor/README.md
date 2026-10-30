# 02 — systemd 监控项目

本目录保留脚本与 unit 模板。学习顺序：[Shell 控制流](../docs/02-shell/03-control-flow.md) → [进程与信号](../docs/03-process/02-jobs-signals.md) → [监控](../docs/04-services/02-monitor.md) → [systemd 部署](../docs/04-services/04-systemd.md)。

## 先在前台验证

在仓库根目录执行：

```bash
bash 02-systemd-monitor/rk3576-monitor.sh --once
bash 02-systemd-monitor/rk3576-monitor.sh --samples 2 --interval 1
```

无参数持续采集，每 5 秒一次；--samples 0 也表示持续。--interval 必须为正整数。正常 TERM/INT 清理等待进程并退出；缺失或无效温度明确显示 N/A。

完整实现见 [rk3576-monitor.sh](rk3576-monitor.sh)。RK3576_THERMAL_ROOT 仅供测试夹具替换读取目录，默认真实 /sys/class/thermal，不能把模拟传感器当成硬件验证。

## 服务模板

[rk3576-monitor.service](rk3576-monitor.service) 含 @USER@ 和 @PROJECT_DIR@，不能直接安装。先执行：

```bash
mkdir -p run
python3 tools/render_service.py --project monitor > run/rk3576-monitor-lab.service
```

审阅、验证、安装、日志、异常恢复、enable 与清理均按[服务课程](../docs/04-services/04-systemd.md)执行。使用独立 rk3576-monitor-lab 名称，保留既有 rk3576-monitor 实例。

[课程总目录](../docs/README.md) · [检查工具](../tools/README.md)
