"""击杀僵尸随机掉落技能 —— 原版 RandomAbilityManager / RandomAbilityNode。

反编译依据（D:\\Code\\dsh\\full_dump\\all_merged.c）：

  RandomAbilityManager::randomAbility @0x17f2c4
      randInt(50) 决定基础技能：
        ≤10 hp   ≤20 power   ≤30 shield   ≤40 speed   >40 airstrike
      再拼上后缀（"_1" / "_2"）；airstrike 不带后缀。

  RandomAbilityManager::getRandomAbility @0x18285c
      候选池 > 8 时：抽 "_1" 变体与 "_2" 变体，
      randInt(10) <= 4（40%）选 "_2"，否则选 "_1"；
      候选池 ≤ 8 时只抽 "_1"。

  RandomAbilityManager::getProbability @0x17f334
      按关卡 day 分档的掉落概率：
        day 1-2    → 0（不掉）
        day 3-5    → 0.04
        day 6-8    → 0.03
        day 9-11   → 0.022
        day 12-23  → 0.016
        day ≥24     → 0.012

  RandomAbilityManager::onZombieDead @0x18359c
      士兵身上没有生效技能时才掉；randInt(1000) <= 概率*1000 才生成。

  RandomAbilityNode::onUpdate @0x17fc30
      掉落物持续向士兵移动；当 |士兵x - 掉落物x| / 2 <= 掉落物宽 * 1.2 时拾取：
      触发技能 → 延迟 (技能时长 + 1.0) 后移除。

  RandomAbilityNode::startAnimation @0x17f314
      ScaleTo(0.3s, 1.2) + 在 (w*0.5, h*0.3) ↔ (w*0.5, h*0.6) 之间循环浮动。
"""

import random

from engine import res


# 基础技能 → 后缀候选池（AbilityItemButton 能装备的技能）
BASE_POOL = ["hp", "power", "shield", "speed"]

# 掉落概率（getProbability 的五档）
PROB_LEVELS = [
    (3, 0.04),
    (6, 0.03),
    (9, 0.022),
    (12, 0.016),
    (24, 0.012),
]


def drop_probability(day):
    """RandomAbilityManager::getProbability：按 day 返回掉落概率。"""
    d = int(day)
    if d <= 2:
        return 0.0
    if d <= 5:
        return 0.04
    if d <= 8:
        return 0.03
    if d <= 11:
        return 0.022
    if d <= 23:
        return 0.016
    return 0.012


def random_ability(rng=None, level=0):
    """RandomAbilityManager::randomAbility + getRandomAbility：抽一个技能名。

    randomAbility：randInt(50) 分 5 档，每档 10%
      ≤10 hp   ≤20 power   ≤30 shield   ≤40 speed   >40 airstrike
    再拼后缀："_1" 或 "_2"；**airstrike 不带后缀**。

    getRandomAbility：判据是 **level > 8**（不是候选池大小！）。
      反编译 RandomAbilityManager::getRandomAbility @0x18285c：
          if ( *(int *)(a2 + 4) > 8 ) { 抽 "_1" 与 "_2" 两个，
              randInt(10) <= 4（40%）选 "_2"；否则选 "_1" }
          else { 只抽 "_1" }
      a2 是 RandomAbilityManager*，a2+4 = this+1 = setLevelId 存的 level。
      第 9 关起再也不会掉出 "_2" 变体技能。

    返回形如 "hp_1" / "power_2" / "airstrike"。
    """
    r = rng or random
    n = r.randint(1, 50)
    if n <= 10:
        base = "hp"
    elif n <= 20:
        base = "power"
    elif n <= 30:
        base = "shield"
    elif n <= 40:
        base = "speed"
    else:
        return "airstrike"
    if int(level) > 8:
        return base + ("_2" if r.randint(1, 10) <= 4 else "_1")
    return base + "_1"


class AbilityDrop:
    """地面上的技能掉落物。"""

    def __init__(self, name, x, y, width=60.0):
        self.name = name
        self.x = x
        self.y = y
        self.width = width
        self.t = 0.0
        self.taken = False
        self.dead = False

    def update(self, dt, soldier_x):
        """RandomAbilityNode::onUpdate：向士兵移动，进入范围即拾取。"""
        self.t += dt
        # 每帧向士兵靠拢（距离越近越快）
        dx = soldier_x - self.x
        self.x += dx * min(1.0, dt * 2.0)
        if abs(soldier_x - self.x) / 2.0 <= self.width * 1.2:
            self.taken = True
        return self.taken
