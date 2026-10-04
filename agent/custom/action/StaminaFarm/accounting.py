"""本性像素预算：点击前预留，看到领取结果后确认；异常时不重复领取。"""

import re
from dataclasses import asdict, dataclass


def parse_balance(text):
    match = re.fullmatch(r"(\d{1,4})/(\d{1,4})", re.sub(r"\s+", "", text))
    if not match:
        raise ValueError("无法明确识别本性像素余额")
    value, capacity = map(int, match.groups())
    # 都市活力为 /700，不能混作本性像素。
    if capacity != 320 or not 0 <= value <= 9999:
        raise ValueError("不是当前版本的本性像素余额")
    return value


@dataclass
class FarmBudget:
    limit: int
    spent: int = 0
    rounds: int = 0
    balance: int | None = None
    pending: bool = False

    def __post_init__(self):
        if (
            type(self.limit) is not int
            or not 40 <= self.limit <= 240
            or self.limit % 40
        ):
            raise ValueError("预算须为 40–240 内的 40 整数倍")

    @property
    def can_claim(self):
        return (
            not self.pending
            and self.spent + 40 <= self.limit
            and self.balance is not None
            and self.balance >= 40
        )

    def reserve(self, cost):
        if type(cost) is not int or cost != 40 or not self.can_claim:
            raise ValueError("领取金额、预算或余额不符合要求")
        self.spent += cost
        self.pending = True

    def confirm(self, new_balance):
        if not self.pending or self.balance is None:
            raise ValueError("没有等待确认的领取")
        # 当前单场最多两分钟，给自然恢复留三点余量；不因余额回升增加预算。
        if not 0 <= new_balance <= self.balance - 40 + 3:
            raise ValueError("领取后余额没有出现预期下降，停止而不是再次点击")
        self.balance = new_balance
        self.rounds += 1
        self.pending = False

    def snapshot(self):
        return asdict(self)
