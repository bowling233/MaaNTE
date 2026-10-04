"""Linux 移植回归检查：启动导入、分辨率校验和异常后的按键释放。"""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent"))

from custom.action.auto_piano.maa_keyboard import MaaKeyboardBridge, WIN32_VK
from custom.action.Common.resize_game_window import ResizeGameWindow
from assemble import TASK_NAMES, adapt_controller_constraints, read_json


class FakeJob:
    def __init__(self, succeeded=True):
        self.succeeded = succeeded

    def wait(self):
        return self


class FakeController:
    def __init__(self, fail_down=None, fail_up=None, resolution=(1280, 720), capture=True):
        self.events = []
        self.fail_down = fail_down
        self.fail_up = fail_up
        self.resolution = resolution
        self.capture = capture

    def post_key_down(self, key):
        self.events.append(("down", key))
        return FakeJob(key != self.fail_down)

    def post_key_up(self, key):
        self.events.append(("up", key))
        return FakeJob(key != self.fail_up)

    def post_screencap(self):
        return FakeJob(self.capture)


@unittest.skipUnless(sys.platform == "linux", "仅验证 Linux 后端")
class PlatformTests(unittest.TestCase):
    def test_piano_uses_virtual_keys_and_releases_modifier(self):
        ctrl = FakeController()
        bridge = MaaKeyboardBridge(controller=ctrl, mapping={60: "shift+a"}, hold_seconds=0)
        bridge.execute_chord([60])
        self.assertEqual(ctrl.events, [
            ("down", WIN32_VK["shift"]), ("down", WIN32_VK["a"]),
            ("up", WIN32_VK["a"]), ("up", WIN32_VK["shift"]),
        ])

    def test_failed_press_still_releases_every_attempted_key(self):
        ctrl = FakeController(fail_down=WIN32_VK["a"])
        bridge = MaaKeyboardBridge(controller=ctrl, mapping={60: "shift+a"}, hold_seconds=0)
        with self.assertRaises(RuntimeError):
            bridge.execute_chord([60])
        self.assertEqual(ctrl.events[-2:], [("up", WIN32_VK["a"]), ("up", WIN32_VK["shift"])])

    def test_failed_release_does_not_skip_modifier_release(self):
        ctrl = FakeController(fail_up=WIN32_VK["a"])
        bridge = MaaKeyboardBridge(controller=ctrl, mapping={60: "shift+a"}, hold_seconds=0)
        with self.assertRaises(RuntimeError):
            bridge.execute_chord([60])
        self.assertEqual(ctrl.events[-1], ("up", WIN32_VK["shift"]))

    def test_resolution_checks_raw_size_and_capture_success(self):
        action = ResizeGameWindow()
        args = SimpleNamespace(custom_action_param="")
        for size, capture, expected in [
            ((1280, 720), True, True), ((1920, 1080), True, False),
            ((1280, 720), False, False),
        ]:
            with self.subTest(size=size, capture=capture):
                ctrl = FakeController(resolution=size, capture=capture)
                context = SimpleNamespace(tasker=SimpleNamespace(controller=ctrl))
                self.assertEqual(action.run(context, args).success, expected)

    def test_task_allowlist_matches_upstream_resources(self):
        interface = read_json(ROOT / "assets/interface.json")
        names = set()
        for path in interface["import"]:
            names.update(task["name"] for task in read_json(ROOT / "assets" / path).get("task", []))
        self.assertTrue(TASK_NAMES <= names)

    def test_framework_null_custom_param_uses_default_resolution(self):
        context = SimpleNamespace(tasker=SimpleNamespace(controller=FakeController()))
        result = ResizeGameWindow().run(context, SimpleNamespace(custom_action_param="null"))
        self.assertTrue(result.success)

    def test_nested_controller_constraints_keep_windows_support(self):
        data = {"option": {"controller": ["Win32-Front"]}}
        adapt_controller_constraints(data)
        self.assertEqual(data["option"]["controller"], ["Win32-Front", "Linux-Gamescope"])


if __name__ == "__main__":
    unittest.main()
