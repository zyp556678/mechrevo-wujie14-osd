# MECHREVO WUJIE14 PRO OSD

在 MECHREVO WUJIE14 Pro 上为 Fn 热键显示屏幕提示（OSD），替代厂商的 Windows 工具 `T140_OSD_V06`。

按 Fn+F1 / Fn+F4 / Fn+F7 / Fn+Esc 时弹出对应图标，1.5 秒后淡出。位置和大小可在设置界面里实时调整。

支持 **GNOME** 和 **KDE Plasma** 两种桌面，共用同一个后台守护进程。

## 覆盖范围

| 按键 | 功能 | 实现方式 |
|---|---|---|
| Fn+F1 | 性能模式（性能/均衡/静音） | MIFS 轮询 |
| Fn+F4 | 触控板开关 | MIFS 轮询 |
| Fn+F7 | 键盘背光亮度 | MIFS 轮询 |
| Fn+Esc | Fn 锁 | MIFS 轮询 |

**不支持**：Fn+F2（锁屏）、Fn+F3（显示输出）、Fn+F5（设置）。这三个键在 Linux 下塌缩成同一个键盘扫描码 `0xf6`，且没有可轮询的状态，无法区分。

**不处理**：F6/F8/F9/F10/F11/F12（睡眠、静音、音量、亮度）。桌面环境已自带原生 OSD，重复实现会弹两次。

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
  轮询 /proc/acpi/call → 值变化 → D-Bus system bus 信号
                                          ↓
                        ┌─────────────────┴─────────────────┐
                    GNOME 前端                          KDE 前端
                Shell 扩展 (GJS)                   mifs-osd-kde (PyQt6)
             Main.uiGroup 上的 St.Icon         zwlr_layer_shell_v1 自绘表面
```

拆成两个进程是因为 `/proc/acpi/call` 仅 root 可读，而前端运行在用户会话里。

两个前端**只在值变化时被动绘制**，所有硬件知识都在守护进程里；前端出问题最多丢一个图标，不会拖累桌面。

## GNOME 版

用 GNOME Shell 扩展而不是独立窗口，是因为 Mutter 不支持 `wlr-layer-shell`，GTK4 也没有窗口定位 API，独立窗口无法可靠地居中置顶。

**设置**：扩展应用 → MECHREVO WUJIE14 PRO OSD → 齿轮图标，或

```bash
gnome-extensions prefs mifs-osd@local
```

配置存在 GSettings（schema `org.gnome.shell.extensions.mifs-osd`），也可用命令行改：

```bash
SCHEMA=org.gnome.shell.extensions.mifs-osd
DIR=~/.local/share/gnome-shell/extensions/mifs-osd@local/schemas
gsettings --schemadir $DIR set $SCHEMA size-percent 0.10
gsettings --schemadir $DIR set $SCHEMA position-mode margin
```

## KDE 版

**它是个普通软件，不是 KDE 扩展。** KDE 的扩展体系（KWin 脚本、Plasma 部件）都不适用：Plasma 部件画在 plasmashell 自己的窗口里，层级低于普通应用窗口，没法可靠地盖在屏幕中央；KWin 脚本在 Plasma 6 里也画不了自定义图形。

所以走的是 `zwlr_layer_shell_v1`——KWin 官方支持的协议，普通进程就能申请一个 overlay 层级的表面，盖在所有窗口之上，且不依赖任何插件机制。

**设置**：应用启动器里搜「MIFS OSD 设置」，或

```bash
mifs-osd-settings
```

配置存在 `~/.config/mifs-osd/osd.conf`（KDE 没有 GSettings），格式是可手改的 INI：

```ini
[backend]
mode = layer-shell        ; layer-shell 自绘 | plasma 系统 OSD

[position]
mode = percent            ; percent 按屏幕比例 | margin 距底边固定像素
x-percent = 0.5000
y-percent = 0.7700
bottom-margin = 120

[icon]
size-percent = 0.1300     ; 图标宽度占屏宽的比例

[preview]
icon = SystemPerfMode_2.png
trigger = 0               ; 设置界面靠自增这个值触发一次真实预览
```

改完文件**不用重启**，渲染器会监听到并立即生效。

**两种渲染方式**：默认 `layer-shell` 自绘，位置和大小由配置控制。切到 `plasma` 则调 plasmashell 自带的 OSD 服务——代价是位置、大小、超时全部由 plasmashell 决定，不可配置，只在自绘不生效时当退路用。

**自启动**：登录时自动启动。用 deb 装的话入口在 `/etc/xdg/autostart/mifs-osd-kde.desktop`（对所有用户生效）；用源码包装的话在 `~/.config/autostart/`。开关都在系统设置 → 开机与关机 → 自动启动里，停用它不影响守护进程。

## 设置界面

两版交互一致，都提供两种预览，因为它们回答不同的问题：

**缩略图**：按显示器宽高比画一个屏幕缩略图，直接拖动白色方块设定位置，改完即时生效。

两种定位模式：

| 模式 | 行为 |
|---|---|
| 屏幕比例 | 图标中心位于屏幕的 (X%, Y%)，可放在任意位置 |
| 距底边边距 | 水平居中，距屏幕底边固定像素，适合贴在底栏上方 |

**Show 按钮**：在真实屏幕上弹一次，方便判断实际观感和对比度。

### 为什么用百分比

位置存成屏幕宽高的小数（如 `x=0.5, y=0.77`），大小存成屏幕宽度的百分比（如 `0.13`）。这样换分辨率、接外接显示器时，图标的相对位置和观感都保持一致，不会跑偏。

两版的算法是刻意保持一致的，从 GNOME 换到 KDE 不需要重新调整。

## 安装

三个发布包对应三条路，**互不重叠**——按你的桌面选一个即可：

| 发布包 | 给谁 | 装法 |
|---|---|---|
| `mechrevo-wujie14-osd_<版本>_all.deb` | Debian / Ubuntu + **KDE Plasma** | `sudo apt install ./xxx.deb` |
| `mifs-osd-gnome-extension-<版本>.zip` | **GNOME** | extensions.gnome.org，或 `gnome-extensions install` |
| `mechrevo-wujie14-osd-<版本>.zip` | 手动安装（开发 / 其它发行版） | 解压后 `pkexec ./install.sh` |

之所以不合成一个包：两个前端各有一整套自己的代码，塞在一起等于让每个用户都拖着一份自己跑不了的桌面的代码。而且 GNOME 扩展还要单独上传到 extensions.gnome.org，那样磁盘上会出现两份同样的 JS 却分不清在跑哪一份。

### KDE Plasma（推荐 deb）

```bash
sudo apt install ./mechrevo-wujie14-osd_1.1.0_all.deb
```

自启动项装在 `/etc/xdg/autostart/`，**对所有用户生效**，装完注销重登即可。卸载：

```bash
sudo apt remove mechrevo-wujie14-osd
```

包里的 `acpi-call-dkms` 只是 `Recommends` 而非 `Depends`——Secure Boot 机器上它的内核模块要先做 MOK 注册再重启才能加载，把它设成硬依赖会让包直接装不上。

### GNOME

从 [extensions.gnome.org](https://extensions.gnome.org) 搜索安装，或用上表的 zip：

```bash
gnome-extensions install --force mifs-osd-gnome-extension-1.1.0.zip
```

注意：扩展需要守护进程来读硬件状态。用 deb 装过的话（即使你只跑 GNOME）它已经在跑了；否则先用源码包跑一次 `install.sh`。

### 手动安装（源码包）

解压后：

```bash
pkexec ./install.sh      # 图形会话：走 polkit 弹认证框
sudo ./install.sh        # 无图形会话或 pkexec 不可用时
```

脚本会：装守护进程到 `/usr/libexec/mifs-osd/`、装图标到 `/usr/share/mifs-osd/icons/`、装两个前端（GNOME 扩展 + KDE 程序）、装 D-Bus 策略、配置 `acpi_call` 开机自动加载、启用并启动 systemd 服务、写 KDE 自启动项。

两个前端**总是都装**：GNOME 扩展只有 GNOME Shell 会加载，KDE 自启动项里写了 `NotShowIn=GNOME`，所以两者不会同时弹。换桌面不用重装，重新登录即可。若系统级自启动已存在（比如装过 deb），脚本不会往用户家目录再写一份。

安装后需要重新登录（GNOME 下还需重启 Shell）让前端生效。

> **关于提权方式**：脚本本身会检查 `id -u`，用哪种方式提权都行。`pkexec` 依赖 polkit，纯 SSH 或最小化安装的机器上可能不存在或不可用，那种情况用 `sudo`。

## 卸载

用 deb 装的：

```bash
sudo apt remove mechrevo-wujie14-osd
```

用源码包装的：

```bash
pkexec ./uninstall.sh    # 或 sudo ./uninstall.sh
```

两者都会留下 `acpi-call-dkms`（别的用途也可能需要它），要清干净再 `apt remove acpi-call-dkms`。

## 依赖

公共：`acpi-call-dkms`（Secure Boot 下需要完成 MOK 注册）。

GNOME 版：`gjs`、GTK4、libadwaita、GNOME Shell 50+。

KDE 版：`python3-pyqt6`、`python3-pyqt6.qtqml`、`layer-shell-qt`、`qml6-module-org-kde-layershell`。Plasma 自带，一般不用手动装；`install.sh` 会检查并在缺失时提示 apt 命令。

## 开发

以下命令都需要 root（因为 `/proc/acpi/call` 仅 root 可读），用 `pkexec` 或 `sudo` 均可：

```bash
# 查看所有功能当前值
sudo python3 tools/mifsctl.py list

# 读写单个功能
sudo python3 tools/mifsctl.py get SystemPerfMode
sudo python3 tools/mifsctl.py set TPLock 1

# 只测轮询（打印变化，不涉及 D-Bus）
sudo python3 -u tools/polltest.py 60

# 端到端（轮询 → D-Bus 信号 → 订阅者）
sudo tools/e2e_root.sh 60
```

KDE 前端不需要 root，可以直接跑：

```bash
cd src/kde
python3 -m mifs_osd_kde                     # 渲染器
python3 -m mifs_osd_kde --list-icons        # 列出图标名
python3 -m mifs_osd_kde --show Fn_ON.png    # 只弹一次，不接 D-Bus
python3 -m mifs_osd_kde --backend plasma    # 临时换成系统 OSD
python3 -m mifs_osd_settings.main           # 设置界面
```

重新生成图标（需要厂商的 Windows 二进制）：

```bash
python3 tools/extract_icons.py OSD_V06/T140_OSD_V06/BLDFnHotkeyUtility.exe
python3 scripts/scale_icons.py
```

开发 GNOME 扩展时，把 `src/extension/mifs-osd@local/` 软链接到
`~/.local/share/gnome-shell/extensions/`，改完用
`gnome-extensions disable/enable mifs-osd@local` 热重载。

> 注意：改 `extension.js` 或 `prefs.js` 后，`disable/enable` **不会**重新加载 ESM 模块（GNOME 50 会缓存），需要 `killall -3 gnome-shell` 才能真正生效。

开发 KDE 前端时，改完代码直接重启进程即可；改 `osd.qml` 后同样需要重启。

## 目录

```
src/daemon/mifs_osd/     root 守护进程（与桌面无关）
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
src/kde/mifs_osd_kde/    KDE 渲染器
  osd.qml                layer-shell 表面 + 淡入淡出
  renderer.py            两种后端：自绘 / 系统 OSD
  config.py              INI 读写
  geometry.py            百分比 → 像素（与 GNOME 版算法一致）
  icons.py               图标查找
  __main__.py            D-Bus 订阅 + 配置监听
src/kde/mifs_osd_settings/      KDE 设置界面
desktop/                 自启动项与应用入口
tools/                   开发用 CLI、图标提取、测试脚本
```

## 已知限制

1. 快速连按 Fn+F1 时，中间状态可能不弹 OSD（轮询是采样）。
2. 依赖 `acpi_call`；内核升级后 DKMS 会重编，Secure Boot 下可能需要重新 MOK 注册。
3. GNOME Shell 大版本升级后，`metadata.json` 的 `shell-version` 可能需要更新。
4. KDE 版的多显示器：只在主屏显示，与 GNOME 版行为一致。
5. KDE 版依赖 KWin 的 `zwlr_layer_shell_v1`。其它 Wayland 合成器（Sway、Hyprland）也支持该协议，但未测试。
6. 仅适用于 MECHREVO WUJIE14 Pro —— 其他机型的 ACPI 路径和 MIFS 功能码可能不同。

## 许可与致谢

代码以 [MIT 许可证](LICENSE) 发布。

图标（`src/extension/mifs-osd@local/icons/`）从厂商 Windows 二进制中提取，版权归原厂商所有，不适用 MIT 许可，仅供在本机型上替代原工具使用。
