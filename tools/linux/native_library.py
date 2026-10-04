"""MaaFramework 5.14.2 Linux 动态库加载兼容处理。"""

import ctypes
import importlib.util
import os
from pathlib import Path

_libraries = []


def load_global():
    if _libraries:
        return
    configured = os.environ.get("MAAFW_BINARY_PATH")
    if configured:
        directory = Path(configured)
    else:
        spec = importlib.util.find_spec("maa")
        if spec is None or spec.origin is None:
            raise RuntimeError("请先安装 maafw==5.14.2")
        directory = Path(spec.origin).parent / "bin"
    # libc++ 的跨动态库 dynamic_cast 依赖共享的 RTTI；RTLD_LOCAL 会让
    # ScrollableUnit / RelativeMovableUnit 判断失败，即使 Linux 后端已实现。
    for name in ("libMaaFramework.so", "libMaaLinuxControlUnit.so"):
        _libraries.append(ctypes.CDLL(str(directory / name), mode=ctypes.RTLD_GLOBAL))
