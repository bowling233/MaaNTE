"""验证 Gamescope 截图和输入；默认只截图，输入必须通过参数显式指定。"""

import argparse
import json
import time
from pathlib import Path

from native_library import load_global

load_global()

from maa.controller import LinuxController
from maa.toolkit import Toolkit
from PIL import Image


def connect(display=None):
    instances = Toolkit.find_gamescope_instances()
    if display is not None:
        instances = [item for item in instances if item.display_no == display]
    if len(instances) != 1:
        raise RuntimeError("需要唯一的 Gamescope 实例；请使用 --display 指定编号")
    instance = instances[0]
    if not instance.pipewire_node_id or not instance.eis_socket_path:
        raise RuntimeError("Gamescope 缺少 PipeWire 节点或 libei 输入 socket")
    controller = LinuxController(
        {
            "screencap_method": 4,
            "input_method": 4,
            "pw_node_id": instance.pipewire_node_id,
            "eis_socket_path": instance.eis_socket_path,
            "use_win32_vk_code": True,
        }
    )
    require(controller.post_connection(), "连接")
    return controller


def require(job, operation):
    if not job.wait().succeeded:
        raise RuntimeError(f"{operation}失败")


def capture(controller, path):
    require(controller.post_screencap(), "截图")
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(controller.cached_image[:, :, ::-1]).save(path)
    return {"path": str(path.resolve()), "resolution": controller.resolution}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--display", type=int)
    parser.add_argument("--output", type=Path, required=True)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--click", type=int, nargs=2, metavar=("X", "Y"))
    action.add_argument("--key", type=int, help="Win32 虚拟键码")
    action.add_argument("--relative", type=int, nargs=2, metavar=("DX", "DY"))
    parser.add_argument("--hold", type=float, default=0.1)
    args = parser.parse_args()
    if not 0 <= args.hold <= 5:
        parser.error("--hold 必须在 0 到 5 秒之间")
    Toolkit.init_option(str(args.output.parent / "debug"))
    controller = connect(args.display)
    if args.click:
        require(controller.post_click(*args.click), "点击")
    elif args.key is not None:
        try:
            require(controller.post_key_down(args.key), "按下按键")
            time.sleep(args.hold)
        finally:
            require(controller.post_key_up(args.key), "释放按键")
    elif args.relative:
        require(controller.post_relative_move(*args.relative), "移动视角")
    print(json.dumps(capture(controller, args.output), ensure_ascii=False))


if __name__ == "__main__":
    main()
