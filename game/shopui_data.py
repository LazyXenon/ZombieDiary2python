"""军火库属性格 —— 直接读 level/upgrade.xml 的 power / speed / crit。

反编译 GunShopLayer::onSelectGun：
    GunUpgradeDef::getLevelDef(def, level, v42)
    PropertyCells::setProperty(this+99,  v42[1], ...)   # power
    PropertyCells::setProperty(this+100, v42[2], ...)   # speed
    PropertyCells::setProperty(this+101, v42[3], ...)   # crit

XML 里 power / speed / crit 本身就是 0..12 的格数，不需要归一。
"""

from game.weapons import load_upgrade_table


CELL_COUNT = 12

_tab = None


def _load():
    global _tab
    if _tab is None:
        _tab = load_upgrade_table()
    return _tab


def gun_level(name, level):
    """返回 (power, speed, crit) 格数；level 超出范围时取最后一级。"""
    return tuple(int(v) for v in gun_attr(name, level))


def gun_attr(name, level):
    """返回 (power, speed, crit) 的**原始浮点值**。

    PropertyCells 的分段画法依赖小数：
      power=0.5 → 1 个半格（cell_now_l）
      power=1.0 → 1 个整格（cell_now）
    所以这里不能取整 —— 取整会把「半格」抹平，和原版对不上。
    """
    g = _load().get(name)
    if not g or not g.get("levels"):
        return (0.0, 0.0, 0.0)
    lv = g["levels"]
    lv = lv[min(max(0, level), len(lv) - 1)]
    out = []
    for key in ("power", "speed", "crit"):
        v = float(lv.get(key) or 0)
        out.append(max(0.0, min(float(CELL_COUNT), v)))
    return tuple(out)


def attr_cells(name, level=0):
    """返回 (当前值三元组, 下一级值三元组)。

    反编译依据：
      * 军火库主界面 GunShopLayer::onSelectGun @0x1329BC：
            KeyValue = getKeyValue(<gun>_lv, 0);
            GunUpgradeDef::getLevelDef(def, KeyValue, v42);
            PropertyCells::setProperty(this+99,  v42[1], 0.0, 0);
            PropertyCells::setProperty(this+100, v42[2], 0.0, 0);
            PropertyCells::setProperty(this+101, v42[3], 0.0, 0);
        —— 主界面取**玩家当前等级**（存档里的 `<gun>_lv`），next 传 0.0。

      * 升级弹窗 @0x134xxx 用 getLevelDef(level+1) 当 next，那是另一条路径。

    PropertyCells::setProperty(this, cur, next, 0) → setProperty1(0, cur, next)：
      · next 非整数 → 先画 1 格 cell_now_r（next 的小数半格）
      · 从 0 到 (int)next-1 → 每格 cell_now.png（已达成整格）
      · next 的小数 → 再画 1 格 cell_now_l
      · 之后 → cell_next.png（未达成）
    """
    cur = gun_attr(name, level)
    nxt = gun_attr(name, level + 1)
    return cur, nxt
