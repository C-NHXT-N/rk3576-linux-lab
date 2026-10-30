# 08-1 交付可维护的视觉推理服务

> 建议时间：20—40 分钟（含独立练习） · 状态：YOLO26n 静态图推理已实测；相机与跨重启待验证

临时视觉服务已完成真实推理、异常恢复和正常停止验证，见[记录](../yolo26-validation.md)。默认使用 FP16；INT8 的框偏差尚需进一步评估。
>
> 执行位置：除特别标注外，均为 **RK3576 的 Bash 终端**。普通用户执行；带 `sudo` 的步骤才需要管理员权限。
>
> 环境：先按[环境说明](../environment.md)设置 `RKLAB_ROOT`。先修课见页尾“上一课”；首次阅读从课程总目录开始。

## 这课完成什么

- 能把已经前台验证的推理程序部署为普通用户服务。
- 能结合日志、健康状态和分项时延排查故障。

## 跟着做：解释、预测、操作、观察


### 1. 先满足前台验收，再后台部署

本课必须以前一课的真实图像推理通过为前提。先在 config.json 选择已验证 静态 image 输入，将 frames 设为 0 表示持续运行，interval 设为 1 表示每次处理至少间隔约 1 秒。

```bash
cd "$RKLAB_ROOT/04-rknn-vision"
.venv/bin/python vision.py --config config.json
```

观察数条结果后按 Ctrl+C；正常结束应将健康状态改为 stopped。interval 是应用节流，不是 NPU 极限吞吐率；preprocess_ms、inference_ms 和 pipeline_ms 是应用侧测量，pipeline 包含取帧及前后处理，但不含随后等待和全部日志开销。

### 2. 生成并审阅课程服务

```bash
cd "$RKLAB_ROOT"
python3 tools/render_service.py --project vision > run/rk3576-vision-lab.service
cat run/rk3576-vision-lab.service
systemd-analyze verify run/rk3576-vision-lab.service
sudo install -m 644 run/rk3576-vision-lab.service /etc/systemd/system/rk3576-vision-lab.service
sudo systemctl daemon-reload
sudo systemctl start rk3576-vision-lab
sudo journalctl -u rk3576-vision-lab -n 20 --no-pager
python3 tools/check_lab.py vision
```

ExecStart 明确使用板端 .venv 的 Python，不依赖当前 Shell 已激活虚拟环境。User 是普通账户；相机和 NPU 的组权限按 BSP 实际要求配置，不能靠将整个服务改为 root 掩盖问题。

### 3. 健康检查到底证明什么

程序成功处理帧后写 run/health.json，包含 running、真实后端名、帧数和时间。检查器要求最近 30 秒有成功推理；因此本课 interval 保持 1 秒，并在应用可按此节奏运行时使用这个阈值。正常停止或运行异常后更新状态。

它证明近期处理发生，不证明检测精度达标或客户端可访问。该项目是受 systemd 管理、以 JSONL 输出结果的本地推理服务，不含远程 API；需要网络接口时再独立定义协议和访问范围。

**先预测：** unit 仍为 active，但健康记录过期，是不是“完全正常”？进程活着与持续产出是不同指标。

### 4. 测量和排错

```bash
systemctl show rk3576-vision-lab -p MainPID -p NRestarts -p ActiveState
sudo journalctl -u rk3576-vision-lab -n 50 --no-pager
bash 02-systemd-monitor/rk3576-monitor.sh --samples 3 --interval 1
```

在相同模型、分辨率、输入源和节流条件下比较预热后的多帧结果；记录 CPU、可用内存、温度和应用时延，区分摄像头读取慢、预处理慢和推理慢。首次模型加载与首帧耗时不要混入稳定运行指标而不说明。

故意异常终止时，只对自己的课程 unit 执行 systemctl kill，再观察 NRestarts 和恢复日志。StartLimit 限制连续失败重试；配置错时先修配置、reset-failed，再启动，不让错误无限刷日志。

### 5. 配置与可复现交付

记录模型/输入 hash、代码版本、wheel 与运行库版本、驱动/内核、输入源、配置和指标。日志保留策略由 journal 管理；用 `journalctl --disk-usage` 观察空间，排错时不要无差别清空系统日志。

确认持续运行、恢复与健康检查后，才执行 `sudo systemctl enable rk3576-vision-lab` 建立开机关系。跨重启验收单独记录，不能用 enabled 代替真正重启测试。


## 自己完成一次

给出一个“进程存在但没有近期结果”的排错过程。再修改 interval 并部署，解释这如何影响心跳阈值与吞吐率测量。

<details>
<summary>提示一：先想方向</summary>

同时看进程、日志、结果更新时间和资源，不只看 active。

</details>

<details>
<summary>提示二：关键工具</summary>

`systemctl show`、`journalctl`、health.json、监控脚本。

</details>

<details>
<summary>参考思路与解释（先尝试再展开）</summary>

先确认输入是否阻塞、最近日志和模型调用，再检查资源。改变配置后 restart；增大间隔需同步调整健康阈值，节流吞吐率不能作为模型极限 FPS。

</details>

## 完成标准

- [ ] 图像推理先前已真实通过。
- [ ] 服务持续产出，日志与健康检查符合预期。
- [ ] 正常停止、异常恢复分别验证。
- [ ] 有版本、模型和性能记录；相机与重启测试单独标注。

勾选属于自评，不能替代实际结果。请保留命令与关键现象，并用自己的话解释一次。

## 清理与回顾

停止并移除自己创建的服务；模型与记录可保留：

```bash
sudo systemctl disable --now rk3576-vision-lab
sudo rm -- /etc/systemd/system/rk3576-vision-lab.service
sudo systemctl daemon-reload
```

只删除课程 unit。回顾完整链路：输入 → 预处理 → NPU 推理 → 后处理 → 日志与心跳 → systemd 生命周期管理。

---

上一课：[07-2 YOLO26n 静态图片检测项目](../07-rknn/02-inference.md) · 下一课：[学习路线与后续专题](../roadmap.md)

[课程总目录](../README.md) · [知识点索引](../knowledge-index.md)
