"""AstrBot 欧非鉴定插件 (OuFeiJianDing).

随机生成一份"今日欧非鉴定"：运气指数与悲剧指数，均为 0~1000 的整数，
并按指数高低配上表情。

设计要点：
- 每日限一次，粒度是"人"而不是"群"：记录 key 用发送者 ID，同一个人
  在任一会话（群聊 / 私聊）鉴定过，当天在其他会话也不能再鉴定，避免换群刷分。
- 记录以 JSON 落盘，写入采用"临时文件 + 原子替换"，避免写到一半被打断时损坏数据。
- 数据存放在 AstrBot 约定的 plugin_data 目录，而不是相对工作目录，
  以免更新或重装插件时丢失。
- 完全本地计算，不依赖第三方库、不调用大模型、无需 API Key。

注意：每日的"今天"采用 AstrBot 所在主机的本地时区，请在部署时确认系统时区正确。
"""

from __future__ import annotations

import json
import os
import random
from datetime import datetime, timedelta
from pathlib import Path

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

# 记录文件的存放路径：data/plugin_data/astrbot_plugin_oufei_jianding/records.json
# 放在这里而不是插件目录，是为了让插件更新/重装时数据不被覆盖。
RECORDS_PATH = (
    Path(get_astrbot_data_path())
    / "plugin_data"
    / "astrbot_plugin_oufei_jianding"
    / "records.json"
)

# 旧版本把记录写在相对工作目录的 data/oufei_jianding/records.json，
# 首次加载时迁移一次，避免老用户迁移后当天可以重复鉴定。
LEGACY_RECORDS_PATH = Path("data/oufei_jianding/records.json")

# 两个指数的取值上限（含），用于换算表情档位。
MAX_INDEX = 1000

# 记录保留天数。只需要保留"今天"用于判断是否已鉴定，多留几天是为了容忍
# 系统时间被往回校正的情况，同时让文件大小有上界、不会无限增长。
KEEP_DAYS = 31

# 表情表：按指数分成 5 档，每档一组候选，命中后随机取一个。
# 分档规则与原实现一致：<200 / <400 / <600 / <800 / >=800。
# 运气指数：分越高越"欧"，表情越开心。
LUCK_EMOJIS = (
    ("😭", "😰", "😱", "😵", "💀"),
    ("😢", "😔", "😟", "😕", "🙁"),
    ("😐", "😑", "😶", "🤔", "🤨"),
    ("🙂", "😊", "😄", "😏", "😌"),
    ("😀", "😃", "😄", "😁", "😆", "😍", "✨", "🎉", "🏆", "👑"),
)
# 悲剧指数：分越高越"非"，所以表情档位与运气指数相反。
SAD_EMOJIS = (
    ("🥳", "😎", "🤓", "😇", "👼"),
    ("🙂", "😊", "😄", "😏", "😌"),
    ("😐", "😑", "😶", "🤔", "🤨"),
    ("😢", "😔", "😟", "😕", "🙁"),
    ("😭", "😰", "😱", "😵", "💀", "💔", "👎", "😭"),
)


def _load_records() -> dict[str, str]:
    """从磁盘读取鉴定记录。

    任何读取或解析失败都退化为空记录，绝不让数据问题影响插件其他功能。

    Returns:
        形如 ``{"用户ID": "YYYY-MM-DD"}`` 的字典；文件不存在或损坏时返回空字典。
    """
    if not RECORDS_PATH.exists():
        return {}
    try:
        with RECORDS_PATH.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(f"oufei_jianding: 读取鉴定记录失败，将按空记录处理: {exc}")
        return {}
    if not isinstance(data, dict):
        logger.warning("oufei_jianding: 鉴定记录格式异常，将按空记录处理。")
        return {}
    # 只保留 "用户ID -> 日期字符串" 这种合法结构，丢弃历史遗留的脏数据。
    return {key: value for key, value in data.items() if isinstance(value, str)}


def _save_records(records: dict[str, str]) -> None:
    """把鉴定记录原子地写入磁盘。

    先写同目录下的临时文件再 ``os.replace`` 覆盖目标文件，因此不会出现
    "文件被写坏一半"的中间状态。写失败只记录日志，不向上抛异常。

    Args:
        records: 待写入的记录字典。
    """
    try:
        RECORDS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = RECORDS_PATH.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as fp:
            json.dump(records, fp, ensure_ascii=False, indent=2)
        os.replace(tmp_path, RECORDS_PATH)
    except OSError as exc:
        logger.error(f"oufei_jianding: 保存鉴定记录失败: {exc}", exc_info=True)


class OufeiJiandingPlugin(Star):
    """欧非鉴定插件：发送「欧非鉴定」，看看今天欧还是非。"""

    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        """初始化插件。

        Args:
            context: AstrBot 传入的插件上下文。
            config: 由 ``_conf_schema.json`` 解析出的插件配置，可能为 None。
        """
        super().__init__(context)
        self.config = config or {}
        self.records = _load_records()
        self._migrate_legacy_records()

    def _migrate_legacy_records(self) -> None:
        """把旧版本写在 data/oufei_jianding/ 下的记录迁移到新的 plugin_data 目录。

        仅在旧文件存在时执行一次；迁移完成后把旧文件改名，避免重复迁移。
        """
        if not LEGACY_RECORDS_PATH.exists():
            return
        # 迁移前先清掉已过期的记录，避免把历史垃圾一起搬过去。
        cutoff = datetime.now().date() - timedelta(days=KEEP_DAYS)
        try:
            with LEGACY_RECORDS_PATH.open("r", encoding="utf-8") as fp:
                legacy = json.load(fp)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(f"oufei_jianding: 迁移旧记录失败，跳过迁移: {exc}")
            return

        if isinstance(legacy, dict):
            merged = 0
            for user_id, day in legacy.items():
                if not isinstance(day, str) or not day:
                    continue
                try:
                    if datetime.strptime(day, "%Y-%m-%d").date() < cutoff:
                        continue
                except ValueError:
                    continue
                # 不覆盖新文件里已有的记录，避免把更新的结果改回旧值。
                if user_id not in self.records:
                    self.records[user_id] = day
                    merged += 1
            if merged:
                _save_records(self.records)
                logger.info(f"oufei_jianding: 已从旧路径迁移 {merged} 条鉴定记录。")

        try:
            LEGACY_RECORDS_PATH.rename(LEGACY_RECORDS_PATH.with_suffix(".json.migrated"))
        except OSError:
            # 改名失败不影响主流程，只是下次启动可能再迁移一遍（幂等，不会丢数据）。
            pass

    def _pick_emoji(self, index: int, emojis: tuple[tuple[str, ...], ...]) -> str:
        """按指数所在的档位随机挑一个表情。

        Args:
            index: 指数值，0~MAX_INDEX。
            emojis: 表情表，按档位从低到高排列，每档是一组候选表情。

        Returns:
            选中的表情；关闭 emoji 开关时返回空字符串。
        """
        if not self.config.get("use_emoji", True):
            return ""
        # 分档边界与原实现对齐：<200 / <400 / <600 / <800 / >=800。
        tier = min(max(index, 0) * len(emojis) // MAX_INDEX, len(emojis) - 1)
        return random.choice(emojis[tier])

    def _format_result(self, event: AstrMessageEvent, luck: int, sad: int) -> str:
        """拼装鉴定结果的文本。

        Args:
            event: 当前消息事件，用于取发送者昵称。
            luck: 运气指数。
            sad: 悲剧指数。

        Returns:
            完整的结果文本，emoji 开关关闭时不包含任何表情。
        """
        luck_emoji = self._pick_emoji(luck, LUCK_EMOJIS)
        sad_emoji = self._pick_emoji(sad, SAD_EMOJIS)
        # 关闭 emoji 时两个占位符都为空串，需要把多余的空格一并去掉。
        return (
            f"【今日欧非鉴定】\n"
            f"{event.get_sender_name() or '你'}\n"
            f"运气指数：{luck} {luck_emoji}\n"
            f"悲剧指数：{sad} {sad_emoji}\n"
            f"（每日一次，明天再来~）"
        ).replace(" \n", "\n")

    @filter.command("欧非鉴定", alias={"oufei", "欧非"})
    async def oufei_jianding(self, event: AstrMessageEvent):
        """鉴定你今天的欧非指数与悲剧指数（0~1000）。

        每人每天只能鉴定一次，私聊与群聊共享同一次数。

        Args:
            event: 当前消息事件。

        Yields:
            一条包含两项指数与表情的纯文本消息。
        """
        # 部分平台的 sender_id 可能为空，退化用 unified_msg_origin 兜底，
        # 保证同一个会话内的记录 key 始终稳定。
        user_id = event.get_sender_id() or event.unified_msg_origin
        today = datetime.now().strftime("%Y-%m-%d")

        try:
            if self.records.get(user_id) == today:
                yield event.plain_result("你今天已经鉴定过了，明天再来吧~ 🍀")
                return

            luck = random.randint(0, MAX_INDEX)
            sad = random.randint(0, MAX_INDEX)

            # 先落盘再回复：只有确实记下了这次鉴定，才告诉用户鉴定成功，
            # 否则用户会以为已经用掉今天的次数，实际却没有记录。
            self.records[user_id] = today
            cutoff = (datetime.now() - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
            self.records = {
                key: day for key, day in self.records.items() if day >= cutoff
            }
            _save_records(self.records)

            yield event.plain_result(self._format_result(event, luck, sad))
        except Exception as exc:  # noqa: BLE001 - 兜底，避免单条消息异常影响插件整体
            logger.error(f"oufei_jianding: 鉴定失败: {exc}", exc_info=True)
            yield event.plain_result("鉴定出了点小问题，等会儿再来试试吧~")
        finally:
            # 阻止事件继续传播，避免这条消息再被后面的插件或大模型处理一遍。
            event.stop_event()

    async def terminate(self):
        """插件被卸载或禁用时调用，此处无需清理任何资源。"""
        return None
