# Linux / Gamescope 实验适配

游戏使用 Proton，MXU、MaaFramework 和 MaaNTE Agent 原生运行。当前验证环境为 KDE Wayland、Gamescope 3.16.29、Python 3.12、MaaFramework 5.14.2、MXU 2.7.1；尚非正式 Linux 发行包。

## 组装

安装 Gamescope、PipeWire、libei，以及 MXU 所需的 GTK/WebKitGTK 系统库。初始化仓库固定版本的模型子模块，下载并解压官方 MXU Linux x86_64 2.7.1。

以下变量需替换为自己的路径；运行目录必须在源码仓库之外：

```bash
git submodule update --init --recursive
runtime=/absolute/path/to/runtime
python3.12 -m venv "$runtime/.venv"
"$runtime/.venv/bin/python" -m pip install -r tools/linux/requirements.txt
"$runtime/.venv/bin/python" tools/linux/assemble.py \
  --output "$runtime" --mxu /absolute/path/to/extracted/mxu
```

组装器复制资源、模型、Agent 和与 Python 包匹配的原生库，生成 Linux 专用 interface。依赖安装和热更新在实验包中关闭，避免覆盖本地适配。更新源码后应关闭 MXU 和任务进程再重新组装；文件锁会拒绝覆盖正在使用的运行目录。

## 启动与验证

用已有可运行的 Proton 前缀和游戏启动方式，在外层增加 Gamescope，设置游戏和 Gamescope 均为 1280×720，例如：

```bash
gamescope -w 1280 -h 720 -W 1280 -H 720 -r 60 -- \
  /path/to/proton waitforexitandrun /path/to/NTELauncher.exe
"$runtime/.venv/bin/python" tools/linux/probe.py \
  --display 0 --output /absolute/path/to/capture.png
"$runtime/start.sh"
```

Proton 所需的 `STEAM_COMPAT_DATA_PATH`、`STEAM_COMPAT_CLIENT_INSTALL_PATH` 等环境变量仍须按现有配置设置。不要在同一前缀已有进程时使用等待 wineserver 退出的启动方式。MXU 中选择 Linux-Gamescope 控制器和正确实例。多个 Gamescope 同时运行时，命令行必须明确指定 `--display`，编号以实际发现结果为准。

`probe.py` 默认只截图；`--click X Y`、`--key VK`、`--relative DX DY` 才会发送输入。任务入口可以独立测试：

```bash
"$runtime/.venv/bin/python" tools/linux/run_task.py \
  --runtime "$runtime" --display 0 --entry ClaimRewardsEntrance --timeout 180
```

咖啡需先手动进入带“开店”按钮的关卡选择界面，当前任务不负责从开放世界导航到咖啡店。实验 GUI 默认只跑一轮。`run_task.py` 输出的是 Pipeline 状态；部分上游流程会以错误截图节点结束仍返回成功，必须同时检查节点、结算画面和活力变化，不能只看退出码循环消耗。

## 范围与已知限制

- 已完成本机领奖和多轮平民咖啡；截图、点击、键盘、滚轮基础控制已验证。
- 俄罗斯方块、音游、钢琴入口仅通过导入和控制器适配检查，未完成实机玩法验证。
- 暂不开放依赖物理键盘监听、Win32 光标查询或 Windows 网络抓包的其他任务。
- Linux 的窗口尺寸操作只校验截图分辨率，不模拟 Win32 调整窗口。
- 本机 5.14.2 默认局部加载动态库时，滚轮/相对移动被错误判断为不支持。`native_library.py` 和 `start.sh` 对当前进程全局加载两个 Maa 动态库作为临时兼容措施；升级后需复测能否删除。
- 偶见 libei 初始设备握手失败；连接失败应检查 Gamescope 日志和实际画面，不应无限重试。
- 不要并发运行两个控制同一游戏的任务。

## 检查

```bash
"$runtime/.venv/bin/python" tools/linux/test_platform.py
git diff --check
```

测试覆盖 Linux 导入、窗口尺寸验证、空参数处理及钢琴按键失败后的释放，不代表所有游戏任务已适配。
