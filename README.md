# MECHREVO WUJIE14 PRO OSD

在 MECHREVO WUJIE14 Pro 上为 Fn 热键显示屏幕提示（OSD），替代厂商的 Windows 工具 `T140_OSD_V06`。

按 Fn+F1 / Fn+F4 / Fn+F7 / Fn+Esc 时弹出对应图标，1.5 秒后淡出。位置和大小可在设置界面里实时调整。

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

## 设置

打开设置界面：扩展应用 → MECHREVO WUJIE14 PRO OSD → 齿轮图标，或

```bash
gnome-extensions prefs mifs-osd@local
```

**Position 页**：一个按显示器宽高比绘制的屏幕缩略图，直接拖动白色方块即可设定位置。

两种定位模式：

| 模式 | 行为 |
|---|---|
| 屏幕比例 | 图标中心位于屏幕的 (X%, Y%)，可放在任意位置 |
| 距底边边距 | 水平居中，距屏幕底边固定像素，适合贴在底栏上方 |

**Icon 页**：调整图标大小、选择预览用图标，以及「Show」按钮——点一下会在真实屏幕上弹一次，方便判断实际观感和对比度。

### 为什么用百分比

位置存成屏幕宽高的小数（如 `x=0.5, y=0.77`），大小存成屏幕宽度的百分比（如 `0.13`）。这样换分辨率、接外接显示器时，图标的相对位置和观感都保持一致，不会跑偏。

配置存在 GSettings（schema `org.gnome.shell.extensions.mifs-osd`），也可用命令行改：

```bash
SCHEMA=org.gnome.shell.extensions.mifs-osd
DIR=~/.local/share/gnome-shell/extensions/mifs-osd@local/schemas
gsettings --schemadir $DIR set $SCHEMA size-percent 0.10
gsettings --schemadir $DIR set $SCHEMA position-mode margin
```

## 安装

从 [Releases](https://github.com/zyp556678/mechrevo-wujie14-osd/releases) 下载 zip 解压，或直接 clone 仓库，然后：

```bash
pkexec ./install.sh      # 图形会话：走 polkit 弹认证框
sudo ./install.sh        # 无图形会话或 pkexec 不可用时
```

脚本会：装守护进程到 `/usr/libexec/mifs-osd/`、装扩展（含 prefs 与 schema）到用户目录、装 D-Bus 策略、配置 `acpi_call` 开机自动加载、启用并启动 systemd 服务。

安装后需要重新登录（或重启 GNOME Shell）让扩展生效。

> **关于提权方式**：脚本本身会检查 `id -u`，用哪种方式提权都行。`pkexec` 依赖 polkit，纯 SSH 或最小化安装的机器上可能不存在或不可用，那种情况用 `sudo`。

## 卸载

```bash
pkexec ./uninstall.sh    # 或 sudo ./uninstall.sh
```

## 依赖

- `acpi-call-dkms`（Secure Boot 下需要完成 MOK 注册）
- `python3-gi`、GTK4、libadwaita、GNOME Shell 50+
- `gjs`

## 开发

以下命令都需要 root（因为 `/proc/acpi/call` 仅 root 可读），用 `pkexec` 或 `sudo` 均可：

```bash
# 查看所有功能当前值
sudo python3 tools/mifsctl.py list

# 读写单个功能
sudo python3 tools/mifsctl.py get SystemPerMode
sudo python3 tools/mifsctl.py set TPLock 1

# 只测轮询（打印变化，不涉及 D-Bus）
sudo python3 -u tools/polltest.py 60

# 端到端（轮询 → D-Bus 信号 → 订阅者）
sudo tools/e2e_root.sh 60
```

> 用 `pkexec` 时注意：它会重置工作目录到 `/root`，且不支持重定向、管道和 `&&`。
> 所以 `pkexec` 的调用要用**绝对路径**，多步操作要写成脚本再整体执行。

重新生成图标（需要厂商的 Windows 二进制）：

```bash
python3 tools/extract_icons.py OSD_V06/T140_OSD_V06/BLDFnHotkeyUtility.exe
python3 scripts/scale_icons.py
```

开发扩展时，把 `src/extension/mifs-osd@local/` 软链接到
`~/.local/share/gnome-shell/extensions/`，改完用
`gnome-extensions disable/enable mifs-osd@local` 热重载。

> 注意：改 `extension.js` 或 `prefs.js` 后，`disable/enable` **不会**重新加载 ESM 模块（GNOME 50 会缓存），需要 `killall -3 gnome-shell` 才能真正生效。

## 目录

```
src/daemon/mifs_osd/     root 守护进程
  acpi.py                MIFS 协议（WMAA + 32 字节缓冲区）
  features.py            功能常量表
  poller.py              轮询 + 防抖
  mapper.py              (功能,值) → 图标文件名
  dbus_service.py        org.mechrevo.Mifs
  __main__.py            组装轮询线程 + GLib 主循环
src/extension/mifs-osd@local/   GNOME Shell 扩展
  extension.js           订阅信号并绘制
  prefs.js               设置界面（缩略图预览 + 实时调整）
  schemas/               GSettings schema
  icons/                 600×600 图标（由脚本生成）
tools/                   开发用 CLI、图标提取、测试脚本
```

## 已知限制

1. 快速连按 Fn+F1 时，中间状态可能不弹 OSD（轮询是采样）。
2. 依赖 `acpi_call`；内核升级后 DKMS 会重编，Secure Boot 下可能需要重新 MOK 注册。
3. GNOME Shell 大版本升级后，`metadata.json` 的 `shell-version` 可能需要更新。
4. 仅适用于 MECHREVO WUJIE14 Pro —— 其他机型的 ACPI 路径和 MIFS 功能码可能不同。

## 许可与致谢

代码以 [MIT 许可证](LICENSE) 发布。

图标（`src/extension/mifs-osd@local/icons/`）从厂商 Windows 二进制中提取，版权归原厂商所有，不适用 MIT 许可，仅供在本机型上替代原工具使用。

