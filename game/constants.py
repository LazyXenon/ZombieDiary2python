"""战斗层共享常量。

放在 game 包内而不是 app.constants：game/battle.py 需要它，而 app 包的
__init__ 会经 app.core → app.dialogs 反向导入 game.battle，从底层包引用
顶层包会形成循环导入。
"""

# 守卫虫洞关的底线（屏幕 x）：僵尸越过即判漏过，不许穿过传送门。
GUARD_LINE_X = 60.0
