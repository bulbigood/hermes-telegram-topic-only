import runpy
import unittest
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch

from telegram import Update
from telegram.ext import Application, ExtBot, TypeHandler

register = runpy.run_path(str(Path(__file__).resolve().parents[1] / '__init__.py'))['register']


class Dispatch(unittest.IsolatedAsyncioTestCase):
    async def run_cases(self, settings, cases):
        ctx = Mock()
        config = {'chat_id': '101', **settings}
        ctx.get_config.side_effect = lambda key, default=None: config.get(key, default)
        register(ctx)
        platform, wire = ctx.register_platform_handler.call_args.args
        self.assertEqual(platform, 'telegram')
        bot = ExtBot('1:offline')
        app = Application.builder().bot(bot).updater(None).build()
        wire(app, None)
        core, observer, error = AsyncMock(), AsyncMock(), AsyncMock()
        app.add_handler(TypeHandler(Update, core), group=0)
        app.add_handler(TypeHandler(Update, observer), group=99)
        app.add_error_handler(error)
        base = {'message_id': 12, 'date': 1, 'chat': {'id': 101, 'type': 'private'}}
        with patch.object(ExtBot, 'initialize', new_callable=AsyncMock), patch.object(ExtBot, 'shutdown', new_callable=AsyncMock):
            async with app:
                for i, (case, kind, fields, allowed) in enumerate(cases):
                    with self.subTest(case=case):
                        payload = fields if kind == 'callback_query' else {**base, **fields}
                        await app.process_update(Update.de_json({'update_id': i, kind: payload}, bot))
                        error.assert_not_awaited()
                        for callback in (core, observer):
                            self.assertEqual(callback.await_count, int(allowed))
                            callback.reset_mock()

    async def test_dispatch(self):
        base = {'message_id': 12, 'date': 1, 'chat': {'id': 101, 'type': 'private'}}
        cases = [
            ('root command', 'message', {'text': '/stop'}, False),
            ('root text', 'message', {'text': 'hello'}, False),
            ('general', 'message', {'text': '/help', 'message_thread_id': 1, 'is_topic_message': True}, False),
            ('reply anchor', 'message', {'text': '/new', 'message_thread_id': 234}, False),
            ('missing topic ID', 'message', {'text': '/new', 'is_topic_message': True}, False),
            ('attachment', 'message', {'photo': [{'file_id': 'a', 'file_unique_id': 'b', 'width': 1, 'height': 1}]}, False),
            ('edited root', 'edited_message', {'text': '/topic'}, False),
            ('existing topic', 'message', {'text': '/help', 'is_topic_message': True, 'message_thread_id': 92}, True),
            ('first post in new topic', 'message', {'text': '/help', 'is_topic_message': True, 'message_thread_id': 1002}, True),
            ('topic created', 'message', {'forum_topic_created': {'name': 'New', 'icon_color': 42}, 'is_topic_message': True, 'message_thread_id': 999}, True),
            ('other DM', 'message', {'chat': {'id': 102, 'type': 'private'}, 'text': '/topic'}, True),
            ('group', 'message', {'chat': {'id': -103, 'type': 'supergroup'}, 'text': '/help'}, True),
            ('button in root', 'callback_query', {'id': 'a', 'from': {'id': 101, 'is_bot': False, 'first_name': 'Example'}, 'chat_instance': 'i', 'data': 'ok', 'message': base}, True),
        ]
        await self.run_cases({}, cases)

    async def test_exact_exceptions(self):
        cases = [('text ' + s, 'message', {'text': s}, ok) for s, ok in (
            ('/help', True), ('Пинг', True), ('пинг', False), ('Пинг ', False),
            ('/help extra', False), ('/help@other_bot', False), ('/help\n/stop', False),
        )]
        cases += [
            ('explicit general', 'message', {'text': 'Пинг', 'message_thread_id': 1}, True),
            ('unlisted in topic', 'message', {'text': '/stop', 'is_topic_message': True, 'message_thread_id': 98}, True),
            ('caption', 'message', {'caption': 'Пинг', 'photo': [{'file_id': 'a', 'file_unique_id': 'b', 'width': 1, 'height': 1}]}, False),
        ]
        await self.run_cases({'root_allowlist': ['/help', 'Пинг']}, cases)

    async def test_empty_and_malformed_allowlist(self):
        for value in ([], '/help', ['/help', None]):
            with self.subTest(value=value):
                await self.run_cases({'root_allowlist': value}, [('blocked', 'message', {'text': '/help'}, False)])

    def test_invalid_config_registers_no_filter(self):
        for value in (None, '', -14, True, 'not-an-id'):
            with self.subTest(value=value):
                ctx = Mock()
                ctx.get_config.return_value = value
                with self.assertRaises(ValueError):
                    register(ctx)
                ctx.register_platform_handler.assert_not_called()
