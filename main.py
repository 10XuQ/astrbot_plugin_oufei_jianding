import random
import json
from datetime import datetime
from pathlib import Path

# 导入 AstrBot 的必要模块和类
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

# 定义数据文件的路径，确保数据持久化
DATA_DIR = Path("data/oufei_jianding")
RECORDS_FILE = DATA_DIR / "records.json"

# 确保数据目录存在
DATA_DIR.mkdir(exist_ok=True)

def get_records():
    """加载使用记录"""
    if not RECORDS_FILE.exists():
        return {}
    try:
        with open(RECORDS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}

def save_records(records):
    """保存使用记录"""
    with open(RECORDS_FILE, 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False, indent=4)

@register(
    name="oufei_jianding",
    author="Qwe(N)",
    desc="一个简单的每日欧非鉴定插件，可直接通过关键词触发。",
    version="1.0.0",
    repo=""
)
class OufeiJiandingPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    def _get_emoji(self, index: int, index_name: str) -> str:
        """根据指数和名称返回随机的 emoji"""
        emojis = []
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

        return random.choice(emojis) if emojis else ""

    @filter.event_message_type(filter.EventMessageType.ALL) # 监听所有类型的消息
    async def on_any_message(self, event: AstrMessageEvent):
        """
        监听所有消息，检查是否包含关键词 '欧非鉴定'
        """
        message_str = event.get_message_str() # 获取消息的纯文本内容
        session_id = event.unified_msg_origin # 使用 unified_msg_origin 作为会话ID，更通用

        # 检查消息是否完全匹配 '欧非鉴定' (忽略首尾空格)
        if message_str.strip() == "欧非鉴定":
            records = get_records()
            today_str = datetime.now().strftime("%Y-%m-%d")

            # 检查用户在当前会话今天是否已经鉴定过
            if session_id in records and records[session_id] == today_str:
                yield event.plain_result("你今天已经鉴定过了，明天再来吧~ 🍀")
                return

            # 生成 0 到 1000 之间的随机整数
            luck_score = random.randint(0, 1000)
            sad_score = random.randint(0, 1000)

            # 获取对应的随机表情
            luck_emoji = self._get_emoji(luck_score, "运气指数")
            sad_emoji = self._get_emoji(sad_score, "悲剧指数")

            # 构造回复消息
            reply_message = f"今日运气指数为 {luck_score} {luck_emoji}，悲剧指数为 {sad_score} {sad_emoji}"

            # 记录本次鉴定
            records[session_id] = today_str
            save_records(records)

            # 使用 yield 返回结果，Bot 会发送此消息
            yield event.plain_result(reply_message)
            # 发送消息后，可以选择停止事件传播，防止其他插件或默认 LLM 处理
            event.stop_event() # 可选：阻止后续处理
#插件由 Gemini 2.5Pro 与 Qwen3-Coder生成
