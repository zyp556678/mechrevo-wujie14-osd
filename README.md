# MECHREVO WUJIE14 PRO OSD

在 MECHREVO WUJIE14 Pro 上为 Fn 热键显示屏幕提示（OSD），替代厂商的 Windows 工具 `T140_OSD_V06`。

按 Fn+F1 / Fn+F4 / Fn+F7 时，屏幕中央偏上弹出对应图标，1.5 秒后淡出——与 Windows 版行为一致。

## 覆盖范围

| 按键 | 功能 | 实现方式 |
|---|---|---|
| Fn+F1 | 性能模式（性能/均衡/静音） | MIFS 轮询 |
| Fn+F4 | 触控板开关 | MIFS 轮询 |
| Fn+F7 | 键盘背光亮度 | MIFS 轮询 |
| Fn+Esc | Fn 锁 | MIFS 轮询 |

**不支持**：Fn+F2（锁屏）、Fn+F3（显示输出）、Fn+F5（设置）。这三个键在 Linux 下塌缩成同一个键盘扫描码 `0xf6`，且没有可轮询的状态，无法区分。

**不处理**：F6/F8/F9/F10/F11/F12（睡眠、静音、音量、亮度）。GNOME 已自带原生 OSD，重复实现会弹两次。

## 原理

厂商工具走 WMI 事件（`HID_EVENT20`），但那需要写内核模块。本方案改用两条更简单的路径：

**读状态**：MIFS 接口通过 `acpi_call` 暴露在 `/proc/acpi/call`：

```
\_SB.PCI0.WMID.WMAA 0x0 0x0 {32 字节}
  [1]  0xFA=Get / 0xFB=Set
  [3]  功能名
  [4]  值
```

**收事件**：固件不提供事件队列，所以以 0.3 秒周期轮询上述功能，值变化即弹 OSD。快速连按可能漏掉中间态——变化后会延迟 150ms 再读一次确认。

## 架构

```
root 守护进程 mifs-osdd (Python)
  轮询 /proc/acpi/call  →  值变化  →  D-Bus system bus 信号
                                            ↓
                        GNOME Shell 扩展 (GJS)
                        订阅信号 → Main.uiGroup 上的 St.Icon
```

拆成两个进程是因为 `/proc/acpi/call` 仅 root 可读，而 GNOME Shell 扩展运行在用户会话里。

用 GNOME Shell 扩展而非独立窗口，是因为 Mutter 不支持 `wlr-layer-shell`，且 GTK4 没有窗口定位 API，独立窗口无法可靠地居中置顶。

## 安装

```bash
pkexec ./install.sh
```

脚本会：装守护进程到 `/usr/libexec/mifs-osd/`、装扩展到用户目录、装 D-Bus 策略、配置 `acpi_call` 开机自动加载、启用并启动 systemd 服务。

安装后需要重新登录（或重启 GNOME Shell）让扩展生效。

## 卸载

```bash
pkexec ./uninstall.sh
```

## 依赖

- `acpi-call-dkms`（Secure Boot 下需要完成 MOK 注册）
- `python3-gi`、GTK4、GNOME Shell 50+
- `gjs`

## 开发

```bash
# 查看所有功能当前值
pkexec python3 tools/mifsctl.py list

# 读写单个功能
pkexec python3 tools/mifsctl.py get SystemPerMode
pkexec python3 tools/mifsctl.py set TPLock 1

# 只测轮询（打印变化，不涉及 D-Bus）
pkexec python3 -u tools/polltest.py 60

# 端到端（轮询 → D-Bus 信号 → 订阅者）
pkexec tools/e2e_root.sh 60
```

重新生成图标（源图在 `extracted_osd_png/`）：

```bash
python3 scripts/scale_icons.py
```

开发扩展时，把 `src/extension/mifs-osd@local/` 软链接到
`~/.local/share/gnome-shell/extensions/`，改完用
`gnome-extensions disable/enable mifs-osd@local` 热重载。

## 目录

```
src/daemon/mifs_osd/     root 守护进程
  acpi.py                MIFS 协议（WMAA + 32 字节缓冲区）
  features.py            功能常量表
  poller.py              轮询 + 防抖
  mapper.py              (功能,值) → 图标文件名
  dbus_service.py        org.mechrevo.Mifs
src/extension/mifs-osd@local/   GNOME Shell 扩展
  extension.js           订阅信号并绘制
  icons/                 600×600 图标（由脚本生成）
tools/                   开发用 CLI 与测试脚本
```

## 已知限制

1. 快速连按 Fn+F1 时，中间状态可能不弹 OSD（轮询是采样）。
2. 依赖 `acpi_call`；内核升级后 DKMS 会重编，Secure Boot 下可能需要重新 MOK 注册。
3. GNOME Shell 大版本升级后，`metadata.json` 的 `shell-version` 可能需要更新。
