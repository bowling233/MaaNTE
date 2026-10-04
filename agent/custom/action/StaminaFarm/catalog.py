"""中文资源本目录与按星期选择；仅计算计划，不发送输入或消费体力。"""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Stage:
    name: str
    category: str
    entrance: str
    index: int
    count: int
    category_index: int

    @property
    def menu_name(self):
        return self.name.removeprefix("泡影罐头·")

    @property
    def guide_row(self):
        # 第五项起滚到列表底端，底端仍显示四行。
        return self.index if self.index < 4 else self.index - (self.count - 4)


_GROUPS = (
    (
        "经验及甲硬币",
        "胡迪尼的魔术舞台",
        (
            ("character_exp", "合订本"),
            ("weapon_exp", "万花筒"),
            ("currency", "硬币记"),
        ),
    ),
    (
        "异能升级材料",
        "胡迪尼的诡计舞台",
        (
            ("ability_pigeon", "小心鸽子"),
            ("ability_cards", "扑克茶会"),
            ("ability_party", "惊喜派对"),
            ("ability_telepathy", "心电感应"),
            ("ability_escape", "越狱艺术"),
        ),
    ),
    (
        "弧盘突破材料",
        "泡影罐头工厂",
        (
            ("arc_apple", "泡影罐头·苹果核"),
            ("arc_spiral", "泡影罐头·螺旋乐"),
            ("arc_dream", "泡影罐头·液态梦"),
            ("arc_dessert", "泡影罐头·冷甜点"),
            ("arc_drama", "泡影罐头·戏剧芯"),
        ),
    ),
    (
        "空幕",
        "兔子洞",
        (
            ("kongmu_clock", "钟表把戏"),
            ("kongmu_sculpture", "雕塑展馆"),
            ("kongmu_loom", "纬线织机"),
            ("kongmu_carrot", "守卫萝卜"),
            ("kongmu_mind", "精神图谱"),
            ("kongmu_rail", "轨道之夜"),
        ),
    ),
)

STAGES = {
    key: Stage(name, category, entrance, index, len(entries), category_index)
    for category_index, (category, entrance, entries) in enumerate(_GROUPS)
    for index, (key, name) in enumerate(entries)
}

# 周一/四异能、周二/五弧盘、周三/六空幕、周日经验货币。
WEEKDAY_CATEGORIES = (1, 2, 3, 1, 2, 3, 0)
ROTATION_EPOCH = date(2026, 10, 5)  # 周一；不使用每年重置的 ISO 周数。


def resolve_stage(selection, day=None):
    if selection != "weekday":
        if selection not in STAGES:
            raise ValueError("不支持的资源本")
        return selection
    day = day or date.today()
    week = (day - ROTATION_EPOCH).days // 7
    weekday = day.weekday()
    category = WEEKDAY_CATEGORIES[weekday]
    entries = _GROUPS[category][2]
    occurrence = 0 if weekday < 3 or weekday == 6 else 1
    offset = week if category == 0 else week * 2 + occurrence
    return entries[offset % len(entries)][0]
