"""Filter one Telegram DM's root, except for explicitly allowed text."""

import logging


def register(ctx):
    value = str(ctx.get_config("chat_id", default="")).strip()
    if not value.isascii() or not value.isdecimal() or int(value) <= 0:
        raise ValueError("telegram-topic-only: configure a positive private chat_id before enabling")
    chat_id = int(value)
    entries = ctx.get_config("root_allowlist", default=[])
    if not isinstance(entries, list) or not all(isinstance(s, str) and s.strip() for s in entries):
        # Do not abort registration: that would disable protection altogether.
        logging.getLogger(__name__).warning("Invalid root_allowlist: no root exceptions will be allowed")
        entries = []
    root_allowlist = frozenset(entries)

    def wire(app, adapter):
        from telegram.ext import ApplicationHandlerStop, MessageHandler, filters

        class BlockedRootMessage(filters.MessageFilter):
            def filter(self, message):
                # A reply anchor alone is not a topic. Match Hermes' private-chat
                # routing and exclude General (1), even when marked as a topic.
                tid = message.message_thread_id
                if message.is_topic_message and isinstance(tid, int) and tid > 1:
                    return False
                return message.text not in root_allowlist

        async def discard(update, context):
            # A plain return would still run handlers in later PTB groups.
            raise ApplicationHandlerStop

        scope = (filters.UpdateType.MESSAGES & filters.ChatType.PRIVATE
                 & filters.Chat(chat_id=chat_id) & BlockedRootMessage())
        app.add_handler(MessageHandler(scope, discard, block=True), group=-100)

    ctx.register_platform_handler("telegram", wire)