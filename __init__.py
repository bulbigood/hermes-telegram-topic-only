"""Allow only actual topic messages in one operator-selected Telegram DM."""


def register(ctx):
    value = str(ctx.get_config("chat_id", default="")).strip()
    if not value.isascii() or not value.isdecimal() or int(value) <= 0:
        raise ValueError("telegram-topic-only: configure a positive private chat_id before enabling")
    chat_id = int(value)

    def wire(app, adapter):
        from telegram.ext import ApplicationHandlerStop, MessageHandler, filters

        class OutsideTopic(filters.MessageFilter):
            def filter(self, message):
                # A reply anchor alone is not a topic. Match Hermes' private-chat
                # routing and exclude General (1), even when marked as a topic.
                tid = message.message_thread_id
                return not (message.is_topic_message and isinstance(tid, int) and tid > 1)

        async def discard(update, context):
            # A plain return would still run handlers in later PTB groups.
            raise ApplicationHandlerStop

        scope = (filters.UpdateType.MESSAGES & filters.ChatType.PRIVATE
                 & filters.Chat(chat_id=chat_id) & OutsideTopic())
        app.add_handler(MessageHandler(scope, discard, block=True), group=-100)

    ctx.register_platform_handler("telegram", wire)