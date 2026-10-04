"""资源本预算、领取确认和输入失败边界测试；不向游戏发送输入。"""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "agent"))

from custom.action.StaminaFarm.accounting import FarmBudget, parse_balance
from custom.action.StaminaFarm.action import press


class BudgetTests(unittest.TestCase):
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
