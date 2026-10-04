"""资源本预算、领取确认和输入失败边界测试；不向游戏发送输入。"""

import sys
import unittest
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "agent"))

from custom.action.StaminaFarm.accounting import FarmBudget, parse_balance
from custom.action.StaminaFarm.action import press, approach_reward
from custom.action.StaminaFarm.catalog import STAGES, resolve_stage


class RotationTests(unittest.TestCase):
    def test_weekday_categories_and_explicit_selection(self):
        expected = ["异能升级材料", "弧盘突破材料", "空幕"] * 2 + ["经验及甲硬币"]
        for offset, category in enumerate(expected):
            day = date(2026, 10, 5) + timedelta(days=offset)
            self.assertEqual(STAGES[resolve_stage("weekday", day)].category, category)
        self.assertEqual(resolve_stage("arc_apple", date(2026, 10, 5)), "arc_apple")
        with self.assertRaises(ValueError):
            resolve_stage("unknown")

    def test_every_variant_is_balanced_across_fifteen_weeks(self):
        counts = Counter(
            resolve_stage("weekday", date(2026, 10, 5) + timedelta(days=i))
            for i in range(15 * 7)
        )
        self.assertEqual(set(counts), set(STAGES))
        for category in {s.category for s in STAGES.values()}:
            self.assertEqual(
                len({counts[k] for k, s in STAGES.items() if s.category == category}), 1
            )

    def test_year_boundary_does_not_restart_the_rotation(self):
        # 连续两个异能日取相邻变体，跨公历年不会回到首项。
        self.assertEqual(resolve_stage("weekday", date(2026, 12, 31)), "ability_pigeon")
        self.assertEqual(resolve_stage("weekday", date(2027, 1, 4)), "ability_cards")
        self.assertEqual(resolve_stage("weekday", date(2027, 1, 7)), "ability_party")

    def test_scroll_layout_for_last_variants(self):
        self.assertEqual(STAGES["ability_escape"].guide_row, 3)
        self.assertEqual(STAGES["kongmu_mind"].guide_row, 2)
        self.assertEqual(STAGES["kongmu_rail"].guide_row, 3)
        self.assertEqual(STAGES["arc_apple"].menu_name, "苹果核")


class BudgetTests(unittest.TestCase):
    def test_transient_reward_prompt_is_not_immediately_used(self):
        module = "custom.action.StaminaFarm.action"
        clock = [0.0]
        frames = []

        def capture_frame(context):
            clock[0] += 0.2
            frames.append(len(frames))
            return frames[-1]

        def recognize_frame(context, name, image):
            return (image != 2) if name == "StaminaFarmRewardPrompt" else None

        with patch(module + ".capture", side_effect=capture_frame), patch(
            module + ".recognize", side_effect=recognize_frame
        ), patch(module + ".time.monotonic", side_effect=lambda: clock[0]), patch(
            module + ".time.sleep"
        ), patch(
            module + ".save_state"
        ) as save:
            approach_reward(None)
        self.assertGreaterEqual(len(frames), 7)
        save.assert_called_once_with("reward_ready", frames[-1])

    def test_budget_is_not_increased_by_regeneration(self):
        budget = FarmBudget(80, balance=249)
        budget.reserve(40)
        budget.confirm(210)
        self.assertTrue(budget.can_claim)
        budget.reserve(40)
        budget.confirm(171)
        self.assertFalse(budget.can_claim)
        self.assertEqual((budget.rounds, budget.spent), (2, 80))

    def test_pending_claim_cannot_be_clicked_again(self):
        budget = FarmBudget(80, balance=100)
        budget.reserve(40)
        with self.assertRaises(ValueError):
            budget.reserve(40)
        self.assertEqual(budget.spent, 40)

    def test_ambiguous_result_preserves_pending_reservation(self):
        budget = FarmBudget(40, balance=100)
        budget.reserve(40)
        with self.assertRaises(ValueError):
            budget.confirm(100)
        self.assertTrue(budget.pending)
        self.assertFalse(budget.can_claim)

    def test_no_claim_when_stamina_is_insufficient(self):
        budget = FarmBudget(40, balance=39)
        with self.assertRaises(ValueError):
            budget.reserve(40)
        self.assertEqual(budget.spent, 0)

    def test_double_claim_and_invalid_budgets_are_rejected(self):
        for value in [0, 39, 50, 280, True, "40"]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                FarmBudget(value)
        with self.assertRaises(ValueError):
            FarmBudget(80, balance=100).reserve(80)

    def test_weekly_vitality_and_ambiguous_ocr_are_rejected(self):
        self.assertEqual(parse_balance("249 / 320"), 249)
        for text in ["700/700", "249", "249/320 40", "24O/320", "-1/320"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_balance(text)

    def test_duplicate_result_cannot_count_twice(self):
        budget = FarmBudget(80, balance=100)
        budget.reserve(40)
        budget.confirm(60)
        with self.assertRaises(ValueError):
            budget.confirm(20)
        self.assertEqual(budget.rounds, 1)

    def test_press_releases_after_failed_down_or_stop(self):
        class Job:
            def __init__(self, succeeded):
                self.succeeded = succeeded

            def wait(self):
                return self

        for down_success, stopping in [(False, False), (True, True)]:
            events = []
            ctrl = SimpleNamespace(
                post_key_down=lambda k: (events.append(("down", k)), Job(down_success))[
                    1
                ],
                post_key_up=lambda k: (events.append(("up", k)), Job(True))[1],
            )
            ctx = SimpleNamespace(
                tasker=SimpleNamespace(controller=ctrl, stopping=stopping)
            )
            with self.assertRaises(RuntimeError):
                press(ctx, 87)
            self.assertEqual(events, [("down", 87), ("up", 87)])


if __name__ == "__main__":
    unittest.main()
