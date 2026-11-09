"""每日重置倒计时 —— 原版的「服务器时间 / getYearDays」本地等价物。

反编译依据：
  AppUtils::getYearDays @0x11d04c → getYearDaysJNI（Java 层取「一年中的第几天」）
  MainMenuScene::clearDailyTaskInfo @0x11fbac
      YearDays = AppUtils::getYearDays();
      if (YearDays != 存档["last_login_day"]) { …每日重置… }

原版所有「每日刷新」的东西（签到 reward_day、每日任务、免费抽次数）
都用这个「一年中的第几天」当判据。

本地没有服务器，用**本机日期**当判据：tm_yday（一年中的第几天）
与原版的 getYearDays 语义一致。注意判据用「年」而不是「日」，
所以跨年会重置（tm_yday 在 12/31 → 1/1 时会变小），
这与原版 getYearDays 的行为一致。

倒计时本身：原版**没有**倒计时 UI（它靠服务器 push 通知）。
所以这里自己算「距离下一个自然日重置还有多久」。
"""

import datetime
import time


def year_days(dt=None):
    """一年中的第几天（1..366）—— 对齐 AppUtils::getYearDays。"""
    dt = dt or datetime.datetime.now()
    return dt.timetuple().tm_yday


def seconds_to_midnight(now=None):
    """距离下一个自然日 00:00 还有多少秒。

    原版是「服务器时间到第二天」，本地用本机时钟近似。
    """
    now = now or datetime.datetime.now()
    midnight = datetime.datetime.combine(now.date() + datetime.timedelta(days=1), datetime.time())
    return max(0, int((midnight - now).total_seconds()))


def format_countdown(sec):
    """秒 → 「HH:MM:SS」。不足一小时用 「MM:SS」。"""
    sec = max(0, int(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return "%d:%02d:%02d" % (h, m, s)
    return "%02d:%02d" % (m, s)


def countdown_text(now=None):
    """「距下次重置 05:23:41」。"""
    return "距下次重置 " + format_countdown(seconds_to_midnight(now))


class DailyTimer:
    """按「自然日」重置的计时器。

    原版每天是「服务器日期变了就重置」，所以判据是日期而不是 24 小时倒计时：
    玩家在 23:59 打开面板、00:01 再打开，重置是立刻发生的。
    本类保持同样语义：last_day 记录上次刷新时的日期，
    ``tick()`` 发现日期变了就触发 on_reset。
    """

    def __init__(self, on_reset=None):
        self.on_reset = on_reset
        self.last_day = year_days()
        self._last_check = time.time()

    def tick(self, now=None):
        """检查是否跨天。跨天则回调 on_reset 并返回 True。"""
        now = now or datetime.datetime.now()
        d = year_days(now)
        if d != self.last_day:
            self.last_day = d
            if self.on_reset:
                self.on_reset()
            return True
        return False

    def remaining(self, now=None):
        """距离下次重置的秒数。"""
        return seconds_to_midnight(now)
