# main.py

# 导入 AstrBot API
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

# 导入 Python 标准库
import random
import time
import os
import json
from datetime import datetime, timezone

# 使用 @register 装饰器注册插件
@register(
    name="astrbot_plugin_oufei_jianding", # 插件名称，与文件夹名和 metadata.yaml 一致
    author="Qwe(N)", # 插件作者
    desc="一个用于鉴定用户今日欧非指数和悲剧指数的插件，可直接通过关键词触发，限制每日每个群/私聊一次，并随机添加表情。", # 插件描述
    version="1.0.0", # 插件版本
    repo="https://github.com/10XuQ/astrbot_plugin_oufei_jianding"
)
class OuFeiJianDingPlugin(Star):
    """
    欧非鉴定插件主类 (关键词触发版, 限制每日每群/私聊一次, 随机表情, 基于UTC日期)
    继承自 Star 基类
    """

    def __init__(self, context: Context):
        """
        插件初始化方法
        """
        super().__init__(context)
        logger.info("OuFeiJianDingPlugin (v1.0.0) by Qwe(N) 初始化完成")
        # 定义存储用户记录的文件路径，存储在 AstrBot 的 data 目录下
        self.data_file_path = os.path.join(context.get_config().get('data_dir', './data'), 'oufei_jianding_records.json')
        self.load_records()

    def load_records(self):
        """从文件加载用户记录"""
        self.user_records = {}
        if os.path.exists(self.data_file_path):
            try:
                with open(self.data_file_path, 'r', encoding='utf-8') as f:
                    self.user_records = json.load(f)
                logger.info(f"从 {self.data_file_path} 加载用户鉴定记录")
            except Exception as e:
                logger.error(f"加载用户鉴定记录失败: {e}")
                self.user_records = {} # 加载失败则初始化为空字典

    def save_records(self):
        """将用户记录保存到文件"""
        try:
            with open(self.data_file_path, 'w', encoding='utf-8') as f:
                json.dump(self.user_records, f, ensure_ascii=False, indent=4)
            logger.debug(f"用户鉴定记录已保存到 {self.data_file_path}")
        except Exception as e:
            logger.error(f"保存用户鉴定记录失败: {e}")

    def get_user_daily_key(self, user_id: str, session_id: str) -> str:
        """
        生成用户的每日唯一键 (user_id + session_id + YYYY-MM-DD in UTC)
        session_id 代表群号或私聊对象ID，确保每个群/私聊独立计数
        """
        # 使用 UTC 时间获取当前日期，确保全球范围内日期计算的一致性
        now_utc = datetime.now(timezone.utc)
        date_str = now_utc.strftime('%Y-%m-%d')
        return f"{user_id}_{session_id}_{date_str}"

    def get_emoji(self, index: int, index_name: str) -> str:
        """根据指数和名称返回随机的 emoji"""
        # 定义不同指数范围对应的 emoji 列表
        if index_name == "运气指数":
            if index < 200:
                emojis = ["😭", "😰", "😱", "😵", "💀"]
            elif index < 400:
                emojis = ["😢", "😔", "😟", "😕", "🙁"]
            elif index < 600:
                emojis = ["😐", "😑", "😶", "🤔", "🤨"]
            elif index < 800:
                emojis = ["🙂", "😊", "😄", "😏", "😌"]
            else:
                emojis = ["😀", "😃", "😄", "😁", "😆", "😍", "✨", "🎉", "🏆", "👑"]
        elif index_name == "悲剧指数":
            if index < 200:
                emojis = ["🥳", "😎", "🤓", "😇", "👼"]
            elif index < 400:
                emojis = ["🙂", "😊", "😄", "😏", "😌"]
            elif index < 600:
                emojis = ["😐", "😑", "😶", "🤔", "🤨"]
            elif index < 800:
                emojis = ["😢", "😔", "😟", "😕", "🙁"]
            else:
                emojis = ["😭", "😰", "😱", "😵", "💀", "💔", "👎", "😭"]
        else:
            return ""

        return random.choice(emojis) if emojis else ""

    async def terminate(self):
        """
        插件卸载/停用时的清理方法 (可选实现)
        """
        logger.info("OuFeiJianDingPlugin (v1.0.0) by Qwe(N) 已卸载")

    @filter.event_message_type(filter.EventMessageType.ALL) # 监听所有类型的消息
    async def on_any_message(self, event: AstrMessageEvent):
        """
        监听所有消息，检查是否包含关键词 '欧非鉴定'
        """
        message_str = event.get_message_str() # 获取消息的纯文本内容
        sender_id = event.get_sender_id() # 获取发送者ID
        session_id = event.get_session_id() # 获取会话ID (群号或私聊对象ID)

        # 检查消息是否完全匹配 '欧非鉴定' (忽略首尾空格)
        if message_str.strip() == "欧非鉴定":
            user_daily_key = self.get_user_daily_key(sender_id, session_id)

            # 检查用户在当前会话 (群/私聊) 今天是否已经鉴定过 (基于UTC日期)
            if user_daily_key in self.user_records:
                yield event.plain_result("你今天在这个地方已经鉴定过了，明天再来吧~")
                event.stop_event()
                return

            # 生成 0 到 1000 之间的随机整数
            luck_index = random.randint(0, 1000)
            tragedy_index = random.randint(0, 1000)

            # 获取对应的随机表情
            luck_emoji = self.get_emoji(luck_index, "运气指数")
            tragedy_emoji = self.get_emoji(tragedy_index, "悲剧指数")

            # 构造回复消息
            reply_message = f"今日运气指数为 {luck_index} {luck_emoji}，悲剧指数为 {tragedy_index} {tragedy_emoji}"

            # 记录本次鉴定
            self.user_records[user_daily_key] = {
                "timestamp": time.time(),
                "session_id": session_id, # 记录会话ID，便于后续可能的查询或清理
                "luck_index": luck_index,
                "tragedy_index": tragedy_index
            }
            self.save_records()

            # 使用 yield 返回结果，Bot 会发送此消息
            yield event.plain_result(reply_message)
            # 发送消息后，可以选择停止事件传播，防止其他插件或默认 LLM 处理
            event.stop_event() # 可选：阻止后续处理


#本插件由Qwen3-Coder编写
