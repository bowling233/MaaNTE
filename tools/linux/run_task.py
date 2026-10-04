"""连接 Gamescope 和独立 Agent，执行一个指定的 MaaNTE Pipeline 入口。"""

import argparse
import fcntl
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from native_library import load_global

load_global()

from maa.agent_client import AgentClient
from maa.resource import Resource
from maa.tasker import Tasker
from maa.toolkit import Toolkit

from probe import capture, connect, require


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--entry", required=True)
    parser.add_argument("--display", type=int)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--override", type=Path, help="Pipeline 覆盖 JSON 文件")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout 必须大于 0")
    runtime = args.runtime.resolve()
    override = json.loads(args.override.read_text()) if args.override else {}
    runtime_lock = (runtime / ".runtime.lock").open("a")
    fcntl.flock(runtime_lock, fcntl.LOCK_SH | fcntl.LOCK_NB)
    os.chdir(runtime)
    Toolkit.init_option(str(runtime / "debug"))
    controller = connect(args.display)
    capture(controller, runtime / "debug/before.png")
    if controller.resolution != (1280, 720):
        raise RuntimeError("请将 Gamescope 和游戏设置为 1280x720")
    resource = Resource()
    require(resource.post_bundle(str(runtime / "resource/base")), "加载资源")
    tasker = Tasker()
    tasker.bind(resource, controller)
    if not tasker.inited:
        raise RuntimeError("Tasker 初始化失败")
    agent = AgentClient()
    if not agent.bind(resource):
        raise RuntimeError("绑定 Agent 失败")
    agent.set_timeout(20000)
    interface = json.loads((runtime / "interface.json").read_text())
    env = os.environ.copy()
    env.update({
        "PI_CLIENT_NAME": "MaaNTE-Linux-Probe",
        "PI_CLIENT_LANGUAGE": "zh_cn",
        "PI_CONTROLLER": json.dumps({"name": "Linux-Gamescope", "type": "Linux"}),
    })
    with (runtime / "debug/agent-console.log").open("w") as log:
        child = subprocess.Popen(
            [interface["agent"]["child_exec"], "-u", str(runtime / "agent/main.py"), agent.identifier],
            cwd=runtime, env=env, stdout=log, stderr=subprocess.STDOUT,
        )
        try:
            if not agent.connect():
                raise RuntimeError("Agent 连接失败，请检查 debug/agent-console.log")
            job = tasker.post_task(args.entry, override)
            deadline = time.monotonic() + args.timeout
            while not job.status.done:
                if child.poll() is not None:
                    raise RuntimeError("Agent 意外退出")
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"任务超过 {args.timeout} 秒，已请求停止")
                time.sleep(0.1)
            capture(controller, runtime / "debug/after.png")
            detail = job.get()
            print(json.dumps({
                "entry": args.entry, "succeeded": job.succeeded,
                "nodes": [tasker.get_node_detail(node).name for node in detail.node_id_list]
                if detail else [],
            }, ensure_ascii=False))
            if not job.succeeded:
                raise RuntimeError("任务失败，请检查 debug 日志")
        finally:
            tasker.post_stop().wait()
            if agent.connected:
                agent.disconnect()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()


if __name__ == "__main__":
    main()
