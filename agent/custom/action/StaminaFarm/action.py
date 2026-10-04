"""胡迪尼资源本的局部控制与预算核对；菜单和场景流转由 Pipeline 负责。"""

import json
import time
from pathlib import Path
from uuid import uuid4

import cv2
from maa.agent.agent_server import AgentServer
from maa.custom_action import CustomAction

from utils.logger import logger
from utils.maafocus import PrintT
from .accounting import FarmBudget, parse_balance

_state = None
_STAGES = {
    "character_exp": ("合订本", 0),
    "weapon_exp": ("万花筒", 1),
    "currency": ("硬币记", 2),
}


def require(job):
    if not job.wait().succeeded:
        raise RuntimeError("控制器操作失败")


def capture(context):
    if context.tasker.stopping:
        raise RuntimeError("任务已停止")
    controller = context.tasker.controller
    require(controller.post_screencap())
    image = controller.cached_image
    if image is None or image.shape[:2] != (720, 1280):
        raise RuntimeError("需要 1280×720 有效截图")
    return image


def recognize(context, name, image):
    result = context.run_recognition(name, image)
    return result if result is not None and result.hit else None


def read_balance(context, name, image):
    result = recognize(context, name, image)
    if not result:
        raise ValueError("本性像素余额识别失败")
    texts = [item.text for item in result.all_results if hasattr(item, "text")]
    # 不拼接不相干候选；必须只有一个有效数值。
    balances = set()
    for text in texts:
        try:
            balances.add(parse_balance(text))
        except ValueError:
            pass
    if len(balances) != 1:
        raise ValueError("本性像素 OCR 候选不唯一")
    return balances.pop()


def press(context, key, duration=0.08):
    controller = context.tasker.controller
    try:
        require(controller.post_key_down(key))
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            if context.tasker.stopping:
                raise RuntimeError("任务已停止")
            time.sleep(min(0.02, max(0, deadline - time.monotonic())))
    finally:
        require(controller.post_key_up(key))


def click_box(context, result):
    if not result or result.box is None:
        raise RuntimeError("没有可点击的识别结果")
    box = result.box
    require(
        context.tasker.controller.post_click(box.x + box.w // 2, box.y + box.h // 2)
    )


def save_state(event, image=None):
    if _state is None:
        return
    directory = _state["directory"]
    if image is not None:
        filename = "%02d-%s.png" % (len(_state["events"]), event)
        if not cv2.imwrite(str(directory / filename), image):
            raise RuntimeError("无法保存领奖证据")
    else:
        filename = None
    _state["events"].append(
        {
            "event": event,
            "time": time.time(),
            "image": filename,
            **_state["budget"].snapshot(),
        }
    )
    data = {
        "stage": _state["stage"],
        "difficulty": _state["difficulty"],
        "fighter_slot": _state["fighter_slot"],
        "events": _state["events"],
    }
    temp = directory / "ledger.tmp"
    temp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temp.replace(directory / "ledger.json")


def reset(context, params):
    global _state
    _state = None
    budget = FarmBudget(params.get("budget", 40))
    stage = params.get("stage", "character_exp")
    if stage not in _STAGES:
        raise ValueError("不支持的资源本")
    difficulty = params.get("difficulty", 6)
    slot = params.get("fighter_slot", 1)
    if type(difficulty) is not int or not 1 <= difficulty <= 6:
        raise ValueError("难度必须为 1–6")
    if type(slot) is not int or not 1 <= slot <= 4:
        raise ValueError("主控角色站位必须为 1–4")
    image = capture(context)
    directory = Path("debug/stamina-farm") / (
        time.strftime("%Y%m%d-%H%M%S-") + uuid4().hex[:8]
    )
    directory.mkdir(parents=True)
    _state = {
        "budget": budget,
        "stage": stage,
        "difficulty": difficulty,
        "fighter_slot": slot,
        "directory": directory,
        "events": [],
    }
    name, index = _STAGES[stage]
    overrides = {
        "StaminaFarmGuideGo": {
            "recognition": {
                "param": {"expected": [name], "roi": [530, 170 + index * 104, 210, 80]}
            },
            "action": {"param": {"target": [1110, 187 + index * 104, 115, 44]}},
        },
        "StaminaFarmSelectStage": {
            "recognition": {
                "param": {"expected": [name], "roi": [10, 120 + index * 80, 160, 40]}
            }
        },
        "StaminaFarmStageTitle": {"recognition": {"param": {"expected": [name]}}},
        "StaminaFarmDifficulty": {
            "action": {"param": {"target": [35 + (difficulty - 1) * 60, 640, 30, 30]}}
        },
    }
    if not context.override_pipeline(overrides):
        raise RuntimeError("配置资源本节点失败")
    save_state("start", image)
    PrintT(context, "stamina_farm.started", name, budget.limit)


def approach_entrance(context):
    deadline = time.monotonic() + 30
    moved = 0.0
    while time.monotonic() < deadline:
        image = capture(context)
        # 传送淡出的一帧也可能命中 InWorld（模板对亮度不敏感）。
        # 未确认正常游戏画面时只等待，不发送移动输入。
        if cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).mean() < 25:
            time.sleep(0.1)
            continue
        if recognize(context, "StaminaFarmEntrancePrompt", image):
            return
        if not recognize(context, "InWorld", image):
            time.sleep(0.1)
            continue
        if moved >= 5:
            raise RuntimeError("入口未出现在预期距离内，停止移动")
        press(context, 87, 0.3)
        moved += 0.3
    raise TimeoutError("未找到胡迪尼入口交互，停止移动")


def enter(context):
    image = capture(context)
    budget = _state["budget"]
    budget.balance = read_balance(context, "StaminaFarmMenuBalance", image)
    if not budget.can_claim:
        # 不点击加号，不使用补充道具；在关卡选择界面正常结束。
        context.override_next("StaminaFarmEnter", ["StaminaFarmFinish"])
        save_state("insufficient_stamina", image)
        return
    if not recognize(context, "StaminaFarmStageTitle", image):
        raise RuntimeError("选中的资源本与配置不一致")
    save_state("enter", image)
    click_box(context, recognize(context, "StaminaFarmEnterButton", image))


def combat(context):
    deadline = time.monotonic() + 120
    advanced = 0.0
    selected = False
    last_skill = last_ultimate = -1000.0
    while time.monotonic() < deadline:
        image = capture(context)
        if recognize(context, "StaminaFarmVictory", image) or recognize(
            context, "StaminaFarmRewardPrompt", image
        ):
            save_state("victory", image)
            return
        if recognize(context, "StaminaFarmDefeat", image):
            raise RuntimeError("角色倒下或挑战失败，不消耗复活道具")
        if not recognize(context, "StaminaFarmEnemyCount", image):
            # 场景变化时不继续攻击。短暂动画交给下一帧确认，总时长仍受上限约束。
            time.sleep(0.1)
            continue
        if not selected:
            press(context, 48 + _state["fighter_slot"])
            selected = True
        elif advanced < 3.5:
            duration = min(0.35, 3.5 - advanced)
            press(context, 87, duration)
            advanced += duration
        elif time.monotonic() - last_skill >= 7:
            press(context, 69)
            last_skill = time.monotonic()
        elif time.monotonic() - last_ultimate >= 15:
            press(context, 81)
            last_ultimate = time.monotonic()
        else:
            # 使用控制器的鼠标接触事件，Linux/Windows 共用；异常和停止均释放。
            ctrl = context.tasker.controller
            try:
                require(ctrl.post_touch_down(640, 360))
                end = time.monotonic() + 0.2
                while time.monotonic() < end and not context.tasker.stopping:
                    time.sleep(0.02)
            finally:
                require(ctrl.post_touch_up())
    raise TimeoutError("战斗超过 120 秒，未确认成功")


def approach_reward(context):
    deadline = time.monotonic() + 35
    missing_since = None
    while time.monotonic() < deadline:
        image = capture(context)
        if recognize(context, "StaminaFarmRewardPrompt", image):
            return
        marker = recognize(context, "StaminaFarmRewardMarker", image)
        if not marker:
            missing_since = missing_since or time.monotonic()
            if time.monotonic() - missing_since > 4:
                raise RuntimeError("奖励定位标记丢失，停止移动")
            time.sleep(0.1)
            continue
        missing_since = None
        center = marker.box.x + marker.box.w / 2
        if center > 760:
            press(context, 68, 0.25)
        elif center < 520:
            press(context, 65, 0.25)
        else:
            press(context, 87, 0.35)
    raise TimeoutError("未到达奖励交互位置")


def claim(context):
    image = capture(context)
    if not recognize(context, "StaminaFarmCost40", image):
        raise RuntimeError("未识别到单倍领取成本 40，停止")
    button = recognize(context, "StaminaFarmClaimButton", image)
    if not button:
        raise RuntimeError("未识别到单倍领取按钮")
    _state["budget"].reserve(40)
    # 点击前写账；即使操作后崩溃也留下未确认记录，绝不自动再点一次。
    save_state("claim_pending", image)
    click_box(context, button)


def account(context):
    image = capture(context)
    if not recognize(context, "StaminaFarmResultTitle", image):
        raise RuntimeError("未识别到获得道具")
    budget = _state["budget"]
    budget.confirm(read_balance(context, "StaminaFarmResultBalance", image))
    save_state("claim_confirmed", image)
    PrintT(context, "stamina_farm.progress", budget.rounds, budget.spent, budget.limit)
    context.override_next(
        "StaminaFarmAccount",
        ["StaminaFarmRepeat" if budget.can_claim else "StaminaFarmExit"],
    )


@AgentServer.custom_action("stamina_farm")
class StaminaFarmAction(CustomAction):
    def run(self, context, argv):
        try:
            params = json.loads(argv.custom_action_param or "{}") or {}
            operation = params.get("operation")
            if operation == "reset":
                reset(context, params)
            elif _state is None:
                raise RuntimeError("刷本任务未初始化")
            elif operation == "approach_entrance":
                approach_entrance(context)
            elif operation == "enter":
                enter(context)
            elif operation == "combat":
                combat(context)
            elif operation == "approach_reward":
                approach_reward(context)
            elif operation == "claim":
                claim(context)
            elif operation == "account":
                account(context)
            elif operation == "finish":
                save_state("finished", capture(context))
                PrintT(context, "stamina_farm.finished", _state["budget"].spent)
            else:
                raise ValueError("未知刷本操作")
            return CustomAction.RunResult(success=True)
        except Exception as exc:
            logger.exception("本性像素刷本失败: %s", exc)
            try:
                save_state("failed", context.tasker.controller.cached_image)
            except Exception:
                logger.exception("保存刷本失败证据时出错")
            PrintT(context, "stamina_farm.failed", str(exc))
            return CustomAction.RunResult(success=False)
