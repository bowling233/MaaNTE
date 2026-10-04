"""原生 MaaFramework 配置合并回归；独立于 AgentServer 进程执行。"""

import json
from pathlib import Path
import tempfile
import unittest


class ConfigTests(unittest.TestCase):
    def test_gui_options_merge_without_losing_stage_budget_or_operation(self):
        from maa.resource import Resource

        root = Path(__file__).resolve().parents[2]
        pipeline = json.loads(
            (root / "assets/resource/base/pipeline/StaminaFarm.json").read_text()
        )
        task = json.loads((root / "assets/resource/tasks/StaminaFarm.json").read_text())
        entrance = pipeline["StaminaFarmEntrance"]
        entrance["next"] = []
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory) / "pipeline"
            bundle.mkdir()
            (bundle / "test.json").write_text(
                json.dumps({"StaminaFarmEntrance": entrance})
            )
            resource = Resource()
            self.assertTrue(resource.post_bundle(directory).wait().succeeded)
            for option, value in [
                ("StaminaFarmStage", "arc_apple"),
                ("StaminaFarmBudget", 80),
                ("StaminaFarmDifficulty", "6"),
                ("StaminaFarmFighter", "4"),
            ]:
                definition = task["option"][option]
                if "cases" in definition:
                    override = next(
                        c["pipeline_override"]
                        for c in definition["cases"]
                        if c["name"] == value
                    )
                else:
                    override = json.loads(
                        json.dumps(definition["pipeline_override"]).replace(
                            '"{budget}"', str(value)
                        )
                    )
                self.assertTrue(resource.override_pipeline(override))
            node = resource.get_node_data("StaminaFarmEntrance")
            self.assertEqual(
                node["attach"],
                {
                    "stage": "arc_apple",
                    "budget": 80,
                    "difficulty": 6,
                    "fighter_slot": 4,
                },
            )
            self.assertEqual(
                node["action"]["param"]["custom_action_param"], {"operation": "reset"}
            )


if __name__ == "__main__":
    unittest.main()
