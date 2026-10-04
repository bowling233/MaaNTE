"""用已安装的 Linux Python 环境和 MXU 组装实验性运行目录。"""

import argparse
import fcntl
import importlib.metadata
import json
import shutil
import sys
from pathlib import Path

import jsonc
import maa

ROOT = Path(__file__).resolve().parents[2]
# 首批仅开放无需物理键盘监听、Win32 鼠标位置查询及网络抓包的入口。
TASK_NAMES = {"ClaimRewards", "MakeCoffeeLite", "Tetris", "Rhythm", "AutoPiano"}
CONTROLLER_NAME = "Linux-Gamescope"


def read_json(path):
    return jsonc.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")


def adapt_controller_constraints(value):
    if isinstance(value, dict):
        controllers = value.get("controller")
        if isinstance(controllers, list):
            if CONTROLLER_NAME not in controllers and any(name.startswith("Win32") for name in controllers):
                controllers.append(CONTROLLER_NAME)
        for child in value.values():
            adapt_controller_constraints(child)
    elif isinstance(value, list):
        for child in value:
            adapt_controller_constraints(child)


def assemble(output, mxu):
    if output == ROOT or ROOT in output.parents:
        raise RuntimeError("请将运行目录放在源码仓库之外")
    output.mkdir(parents=True, exist_ok=True)
    with (output / ".runtime.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("运行目录正在使用，请先关闭 MXU 和任务进程") from None
        _assemble(output, mxu)


def _assemble(output, mxu):
    if sys.platform != "linux":
        raise RuntimeError("此工具仅用于 Linux 原生构建")
    if importlib.metadata.version("maafw").removeprefix("v") != "5.14.2":
        raise RuntimeError("请使用 tools/linux/requirements.txt 安装匹配的 MaaFramework")
    if sys.prefix == sys.base_prefix:
        raise RuntimeError("请在虚拟环境中安装依赖并执行组装")
    if output == ROOT or ROOT in output.parents:
        raise RuntimeError("请将运行目录放在源码仓库之外")
    if not mxu.is_file():
        raise FileNotFoundError(mxu)

    model_sources = {
        "ocr": ROOT / "assets/MaaCommonAssets/OCR/ppocr_v5/zh_cn",
        "classify": ROOT / "assets/MaaNTEModels/classify",
        "navi": ROOT / "assets/MaaNTEModels/navi",
    }
    for path in model_sources.values():
        if not path.is_dir():
            raise RuntimeError(f"缺少子模块资源：{path}，请先初始化 git submodule")

    output.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "assets/resource", output / "resource", dirs_exist_ok=True)
    shutil.copytree(
        ROOT / "agent", output / "agent", dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    for name, path in model_sources.items():
        shutil.copytree(path, output / "resource/base/model" / name, dirs_exist_ok=True)
    shutil.copytree(Path(maa.__file__).parent / "bin", output / "maafw", dirs_exist_ok=True)
    if mxu.resolve() != output / "mxu":
        shutil.copy2(mxu, output / "mxu")
    (output / "mxu").chmod(0o755)
    launcher = output / "start.sh"
    launcher.write_text(
        '#!/usr/bin/env bash\nset -euo pipefail\n'
        'cd -- "$(dirname -- "${BASH_SOURCE[0]}")"\n'
        'exec 9>.runtime.lock\nflock -s -n 9\n'
        '# 5.14.2 的跨动态库 RTTI 需要全局符号；只对本次 MXU 进程生效。\n'
        'export MAAFW_BINARY_PATH="$PWD/maafw"\n'
        'export LD_PRELOAD="$PWD/maafw/libMaaFramework.so:$PWD/maafw/libMaaLinuxControlUnit.so${LD_PRELOAD:+:$LD_PRELOAD}"\n'
        'exec ./mxu "$@"\n', encoding="utf-8",
    )
    launcher.chmod(0o755)
    for name in ("requirements.txt", "LICENSE", "README.md"):
        shutil.copy2(ROOT / name, output / name)
    shutil.copy2(ROOT / "assets/logo.png", output / "logo.png")

    interface = read_json(ROOT / "assets/interface.json")
    interface["version"] = "0.0.0-linux-dev"
    interface["icon"] = "logo.png"
    interface["controller"] = [{
        "name": CONTROLLER_NAME,
        "type": "Linux",
        "linux": {
            "screencap": "PipeWire", "input": "Libei",
            "pipewire_source": "Gamescope", "use_win32_vk_code": True,
        },
    }]
    # 保留虚拟环境路径，不能 resolve() 到环境外的 Python 实际二进制。
    interface["agent"] = {
        "child_exec": sys.executable,
        "child_args": ["-u", str(output / "agent/main.py")],
    }
    imports = []
    enabled = []
    for relative in interface["import"]:
        document = read_json(ROOT / "assets" / relative)
        tasks = [task for task in document.get("task", []) if task["name"] in TASK_NAMES]
        if not tasks:
            continue
        document["task"] = tasks
        if "MakeCoffeeLite" in [task["name"] for task in tasks]:
            for item in document["option"]["MakeCoffeeLoopTimeAndTimeout"]["inputs"]:
                if item["name"] == "LoopTime":
                    item["default"] = "1"
        adapt_controller_constraints(document)
        write_json(output / relative, document)
        imports.append(relative)
        enabled.extend(task["name"] for task in tasks)
    if set(enabled) != TASK_NAMES:
        raise RuntimeError(f"缺少预期的任务入口：{TASK_NAMES - set(enabled)}")
    interface["import"] = imports
    write_json(output / "interface.json", interface)
    config = output / "config"
    config.mkdir(exist_ok=True)
    # 实验包依赖由组装环境提供，禁止启动时改装依赖或热更新覆盖本地补丁。
    write_json(config / "pip_config.json", {"enable_pip_install": False})
    write_json(config / "hot_update.json", {"enable_hot_update": False})
    print(json.dumps({"output": str(output), "tasks": sorted(enabled)}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mxu", type=Path, required=True, help="已解压的 MXU Linux 可执行文件")
    args = parser.parse_args()
    assemble(args.output.resolve(), args.mxu.resolve())


if __name__ == "__main__":
    main()
