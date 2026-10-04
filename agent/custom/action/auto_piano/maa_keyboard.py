import ctypes
import sys
import time

from .key_mapping import NOTE_KEY_MAPPING
from utils.logger import logger

user32 = ctypes.windll.user32 if sys.platform == "win32" else None
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_ACTIVATE = 0x0006
WA_CLICKACTIVE = 2

# 使用游戏专用的左 Shift 和左 Ctrl 防跑调。
WIN32_VK = {
    "shift": 0xA0,
    "ctrl": 0xA2,
    "a": 0x41,
    "b": 0x42,
    "c": 0x43,
    "d": 0x44,
    "e": 0x45,
    "f": 0x46,
    "g": 0x47,
    "h": 0x48,
    "i": 0x49,
    "j": 0x4A,
    "k": 0x4B,
    "l": 0x4C,
    "m": 0x4D,
    "n": 0x4E,
    "o": 0x4F,
    "p": 0x50,
    "q": 0x51,
    "r": 0x52,
    "s": 0x53,
    "t": 0x54,
    "u": 0x55,
    "v": 0x56,
    "w": 0x57,
    "x": 0x58,
    "y": 0x59,
    "z": 0x5A,
}

WINDOW_TITLES = [
    "NTE  ",
    "异环  ",
]


def get_lparam(vk_code, is_down=True):
    """构建底层硬件扫描码。"""
    scan_code = user32.MapVirtualKeyW(vk_code, 0)
    lparam = 1 | (scan_code << 16)
    if not is_down:
        lparam |= 0xC0000000
    return lparam


class MaaKeyboardBridge:
    def __init__(
        self,
        hold_seconds: float = 0.008,
        mapping: dict | None = None,
        controller=None,
    ):
        self.mapping = mapping if mapping is not None else NOTE_KEY_MAPPING
        self.hold_seconds = hold_seconds
        self.hwnd = 0
        self.controller = controller if sys.platform != "win32" else None
        if user32 is None:
            if self.controller is None:
                raise RuntimeError("Linux 钢琴输入需要 MaaFramework 控制器")
            return

        for title in WINDOW_TITLES:
            hwnd = user32.FindWindowW(None, title)
            if hwnd:
                self.hwnd = hwnd
                logger.info("已连接到游戏窗口: '%s' (HWND: %s)", title, self.hwnd)
                break

        if not self.hwnd:
            logger.warning(
                "未找到列表中的任何窗口，请检查游戏是否运行！列表: %s",
                WINDOW_TITLES,
            )

    def _force_send_key(self, vk_code, is_down):
        """Windows 保留消息输入，Linux 通过控制器发送按键。"""
        if self.controller is not None:
            post = self.controller.post_key_down if is_down else self.controller.post_key_up
            if not post(vk_code).wait().succeeded:
                raise RuntimeError("钢琴按键发送失败")
            return
        if not self.hwnd:
            return

        lparam = get_lparam(vk_code, is_down)
        msg = WM_KEYDOWN if is_down else WM_KEYUP
        user32.PostMessageW(self.hwnd, msg, vk_code, lparam)

    def _activate(self):
        if self.controller is not None:
            return
        user32.SendMessageW(self.hwnd, WM_ACTIVATE, WA_CLICKACTIVE, 0)

    def execute_chord(self, midi_notes):
        """按修饰键类型隔离并短按一个和弦。"""
        if not self.hwnd and self.controller is None:
            return

        self._activate()
        self._execute_chord_groups(midi_notes)

    def _execute_chord_groups(self, midi_notes):
        """发送已经激活窗口的短按和弦。"""

        normal_keys, shift_keys, ctrl_keys = [], [], []

        for note in midi_notes:
            if note not in self.mapping:
                continue
            action = self.mapping[note]
            key = action.split("+")[-1]
            if "shift+" in action:
                shift_keys.append(key)
            elif "ctrl+" in action:
                ctrl_keys.append(key)
            else:
                normal_keys.append(key)

        self._press_group(normal_keys)
        self._press_group(shift_keys, "shift")
        self._press_group(ctrl_keys, "ctrl")

    def _press_group(self, keys, modifier: str | None = None):
        if not keys:
            return

        pressed = []
        try:
            if modifier and modifier in WIN32_VK:
                pressed.append(WIN32_VK[modifier])
                self._force_send_key(WIN32_VK[modifier], True)
                time.sleep(0.002)

            for key in keys:
                if key in WIN32_VK:
                    # 即使发送端报告失败，也尝试释放，避免错误中断后留下按住的键。
                    pressed.append(WIN32_VK[key])
                    self._force_send_key(WIN32_VK[key], True)
            if self.hold_seconds > 0:
                time.sleep(self.hold_seconds)
        finally:
            active_error = sys.exc_info()[0] is not None
            release_error = None
            for vk in reversed(pressed):
                try:
                    self._force_send_key(vk, False)
                except RuntimeError as exc:
                    logger.warning("钢琴按键释放失败 (%s): %s", vk, exc)
                    release_error = exc
            if release_error is not None and not active_error:
                raise release_error
