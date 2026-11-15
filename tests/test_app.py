import json
import io
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from urllib.parse import urlencode
from pathlib import Path
from unittest.mock import patch

from energytool.core import Consultant, MATERIALS, Search, parse_question
from energytool.server import make_server
from energytool.storage import Store

TEST_KB = Path(__file__).parent / 'fixtures'
HAS_CASE = (MATERIALS / 'knowledge-base').is_dir()


class RetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.search = Search(TEST_KB)

    def test_full_document_index(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "test.md").write_text("# Продукт\n" + "Вводная информация.\n" * 100 + "## Особенность\nПоддерживается фотораспознавание уникального индикатора.", encoding="utf-8")
            matches = Search(directory).search("фотораспознавание")
            self.assertIn("уникального", matches[0][0].text)

    @unittest.skipUnless(HAS_CASE, 'Optional case files are not distributed with the project')
    def test_relevant_products(self):
        search = Search(MATERIALS / 'knowledge-base')
        for query, document in [("Солнечная станция на крыше", "23-solar.md"),
                                ("Распознавание показаний по фотографии", "25-meter-reading.md"),
                                ("Поиск коммерческих потерь", "24-losses.md"),
                                ("Выход на оптовый рынок", "21-orem.md")]:
            with self.subTest(query=query):
                self.assertTrue(any(c.document.endswith(document) for c, _ in search.search(query)))

    def test_dialogue_parser(self):
        messages = parse_question("Пользователь: Первый вопрос\nАссистент: Уточните\nПользователь: Последний вопрос")
        self.assertEqual([m["role"] for m in messages], ["user", "assistant", "user"])
        self.assertEqual(messages[-1]["content"], "Последний вопрос")

    def test_missing_api_is_explicit(self):
        bot = Consultant(TEST_KB)
        bot.key = ""
        result = bot.answer([{"role": "user", "content": "Солнечные панели"}])
        self.assertEqual(result["mode"], "retrieval")
        self.assertIn("LLM не подключена", result["answer"])
        self.assertTrue(result["sources"])

    def test_model_failure_is_reported(self):
        bot = Consultant(TEST_KB)
        bot.key, bot.base = "test", "http://unused"
        with patch.object(bot, "complete", side_effect=TimeoutError):
            result = bot.answer([{"role": "user", "content": "Солнечные панели"}])
        self.assertEqual(result["error"], "llm_unavailable")

    def test_case_materials_are_not_sent_to_openrouter_by_default(self):
        with patch.dict('os.environ', {'DEMO_MODE':'0','ALLOW_CASE_EXTERNAL_API':'0'}):
            bot = Consultant(TEST_KB)
            bot.key,bot.base = 'test','https://openrouter.ai/api/v1'
            with patch.object(bot,'complete') as complete:
                result = bot.answer([{'role':'user','content':'Солнечные панели'}])
                complete.assert_not_called()
                self.assertEqual(result['mode'],'retrieval')

    def test_early_client_facts_survive_long_dialogue(self):
        bot=Consultant(TEST_KB)
        bot.key,bot.base='test','http://unused'
        history=[{'role':'user','content':'Объект в Туле, 840 кВт.'}]
        history += [{'role':'assistant' if i%2==0 else 'user','content':'Обсудим учёт'} for i in range(24)]
        history.append({'role':'user','content':'Вернёмся к моему объекту'})
        with patch.object(bot,'complete',return_value='Ответ') as complete:
            bot.answer(history)
        self.assertIn('840',json.dumps(complete.call_args.args[0],ensure_ascii=False))

    def test_middle_of_long_history_is_preserved(self):
        bot = Consultant(TEST_KB)
        bot.key, bot.base = 'test', 'http://unused'
        history = [{'role':'user','content':'Учёт ' + 'данные '*800} for _ in range(12)]
        history[5]['content'] = 'Учёт: уникальный объект 731 в середине разговора'
        history += [{'role':'user','content':'Учёт расходов'} for _ in range(25)]
        with patch.object(bot,'complete',return_value='Ответ') as complete:
            bot.answer(history)
        self.assertEqual(complete.call_args.args[0][2:], history)

    def test_context_limit_is_explicit_without_silent_truncation(self):
        bot = Consultant(TEST_KB)
        bot.key, bot.base = 'test', 'http://unused'
        with patch.dict('os.environ', {'MAX_CONTEXT_CHARS':'500'}), patch.object(bot,'complete') as complete:
            result = bot.answer([{'role':'user','content':'Солнечные панели'}])
        complete.assert_not_called()
        self.assertEqual(result['error'],'context_limit')

    def test_missing_evidence_offers_specialist_without_calling_model(self):
        bot = Consultant(TEST_KB)
        for key in ('', 'test'):
            bot.key, bot.base = key, 'http://unused'
            with patch.object(bot.searcher,'search',return_value=[]), patch.object(bot,'complete') as complete:
                result = bot.answer([{'role':'user','content':'Вопрос за пределами базы'}])
            complete.assert_not_called()
            self.assertEqual(result['mode'],'refusal')
            self.assertIn('специалист',result['answer'])

    def test_truncated_model_output_is_not_shown_as_complete(self):
        bot = Consultant(TEST_KB)
        bot.key, bot.base = 'test', 'http://unused'
        response = io.BytesIO(json.dumps({'choices': [{'finish_reason': 'length',
                                                      'message': {'content': 'Незаконченное предложение'}}]}).encode())
        with patch('urllib.request.urlopen', return_value=response):
            with self.assertRaises(ValueError):
                bot.complete([{'role': 'user', 'content': 'Тест'}])

    @unittest.skipUnless(HAS_CASE, 'Optional case files are not distributed with the project')
    def test_short_followup_retains_product_context(self):
        bot = Consultant()
        bot.key = ""
        result = bot.answer(parse_question("Пользователь: Мы электросетевая компания. Хотим лучше находить потери.\nАссистент: Какие данные у вас есть?\nПользователь: По одним приборам почасовые, по другим только суточные.\nАссистент: Какой архив накоплен?\nПользователь: Примерно за два года. Таких данных хватит, чтобы начать?"))
        self.assertTrue(any(s["document"].endswith("24-losses.md") for s in result["sources"][:3]))

    def test_demo_uses_only_fictional_sources(self):
        with patch.dict('os.environ', {'DEMO_MODE': '1'}):
            bot = Consultant(MATERIALS.parent / 'demo-knowledge-base')
        bot.key, bot.base = 'test', 'http://unused'
        with patch.object(bot, 'complete', return_value='На всех трёх складах выросли расходы?') as complete:
            result = bot.answer([{'role': 'user', 'content': 'У нас три склада, хотим сократить расходы на электричество'}])
        self.assertEqual(result['mode'], 'llm')
        self.assertTrue(result['sources'])
        self.assertEqual({s['document'] for s in result['sources']}, {'demo.md'})
        self.assertIn('вымышленной компании', complete.call_args.args[0][0]['content'])


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "db.sqlite3")
        self.bot = Consultant(TEST_KB)
        self.bot.key = ""
        self.server = make_server("127.0.0.1", 0, self.bot, self.store)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = "http://127.0.0.1:" + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path, data=None, headers=None):
        request = urllib.request.Request(self.url + path, None if data is None else json.dumps(data).encode(),
                                         headers or {"Content-Type": "application/json"})
        with urllib.request.urlopen(request) as response:
            return json.load(response)

    def test_consultation_lead_and_new_session(self):
        sid = self.request("/api/sessions", {})["id"]
        result = self.request("/api/chat", {"session_id": sid, "message": "Нужны солнечные панели для склада"})
        self.assertTrue(result["sources"])
        lead = self.request("/api/leads", {"session_id": sid, "name": "Тестовый Клиент", "phone": "+7 000 000-00-00", "company": "Тест", "test_data": True})
        self.assertIn("солнечные панели", lead["summary"])
        self.request("/api/close", {"session_id": sid})
        other = self.request("/api/sessions", {})["id"]
        self.assertEqual(self.request("/api/sessions/" + other)["messages"], [])
        previous = self.request("/api/sessions/" + sid)
        self.assertEqual(len(previous["messages"]), 2)
        self.assertEqual(len(previous["leads"]), 1)
        reopened = Store(self.store.path)
        self.assertEqual(len(reopened.messages(sid)), 2)
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request("/api/chat", {"session_id": sid, "message": "Продолжим"})
        self.assertEqual(error.exception.code, 409)

    def test_invalid_input_and_origin(self):
        sid = self.request("/api/sessions", {})["id"]
        for payload in ({"session_id": sid, "message": ""}, {"session_id": sid, "message": "x" * 6001}):
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.request("/api/chat", payload)
            self.assertEqual(error.exception.code, 400)
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request("/api/sessions", {}, {"Origin": "https://untrusted.example"})
        self.assertEqual(error.exception.code, 403)

    def test_lead_requires_test_data_and_valid_phone(self):
        sid = self.request("/api/sessions", {})["id"]
        base = {"session_id": sid, "name": "Тест", "phone": "70000000000", "company": "Тест"}
        for extra in ({"test_data": False}, {"test_data": True, "phone": "123"}):
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.request("/api/leads", {**base, **extra})
            self.assertEqual(error.exception.code, 400)

    def test_retries_do_not_duplicate_messages_or_leads(self):
        sid=self.request('/api/sessions',{})['id']
        turn={'session_id':sid,'message':'Учёт для трёх складов','request_id':'turn-request-001'}
        with patch.object(self.bot,'answer',return_value={'answer':'Ответ','sources':[], 'mode':'llm','elapsed_ms':1,'error':None}) as answer:
            first=self.request('/api/chat',turn)
            self.assertEqual(self.request('/api/chat',turn),first)
            self.assertEqual(answer.call_count,1)
        self.assertEqual(len(self.store.messages(sid)),2)
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request('/api/chat',{**turn,'message':'Другой вопрос'})
        self.assertEqual(error.exception.code,409)
        data={'session_id':sid,'name':'Тест','phone':'70000000000','company':'Тест','test_data':True,'request_id':'lead-request-001'}
        first=self.request('/api/leads',data)
        second=self.request('/api/leads',data)
        self.assertEqual(first['id'],second['id'])
        self.assertEqual(len(self.store.leads(sid)),1)
        self.assertEqual(Store(self.store.path).cached_turn(sid,turn['request_id'],turn['message'])['answer'],'Ответ')
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request('/api/leads',{**data,'company':'Другое имя'})
        self.assertEqual(error.exception.code,409)

    def test_manager_list_search_details_and_persistence(self):
        first = self.request('/api/sessions', {})['id']
        second = self.request('/api/sessions', {})['id']
        self.store.add(first, 'user', 'Первый склад: ищем причину роста расходов')
        self.store.add(first, 'assistant', 'Изменилось ли потребление?', {'mode': 'llm', 'sources': []})
        self.store.add(second, 'user', 'Другой диалог, не относится к первому складу')
        one = self.request('/api/leads', {'session_id': first, 'name': 'Иван Тестовый',
            'phone': '+7 000 000-00-01', 'company': 'Тестовый Склад', 'test_data': True})
        two = self.request('/api/leads', {'session_id': second, 'name': 'Анна Пример',
            'phone': '+7 000 000-00-02', 'company': 'Другая Компания', 'test_data': True})
        self.request('/api/close', {'session_id': first})
        listing = self.request('/api/leads?limit=1')
        self.assertEqual(listing['total'], 2)
        self.assertEqual(listing['filtered'], 2)
        self.assertEqual(listing['items'][0]['id'], two['id'])
        self.assertEqual(self.request('/api/leads?limit=1&offset=1')['items'][0]['id'], one['id'])
        for query in ('тЕсТоВыЙ скЛАД', 'ИВАН', '000-00-01'):
            with self.subTest(query=query):
                found = self.request('/api/leads?' + urlencode({'q': query}))
                self.assertEqual(found['filtered'], 1)
                self.assertEqual(found['items'][0]['id'], one['id'])
        self.assertEqual(self.request('/api/leads?q=%25')['items'], [])  # '%' is literal, not a wildcard.
        detail = self.request('/api/leads/' + one['id'])
        self.assertEqual(detail['lead']['phone'], '+7 000 000-00-01')
        self.assertEqual(detail['session']['id'], first)
        self.assertTrue(detail['session']['closed'])
        self.assertEqual([m['role'] for m in detail['messages']], ['user', 'assistant'])
        self.assertNotIn('Другой диалог', json.dumps(detail, ensure_ascii=False))
        # Reading a card does not reopen the client session or append messages.
        self.assertEqual(len(self.store.messages(first)), 2)
        reopened = Store(self.store.path)
        self.assertEqual(reopened.list_leads()['total'], 2)
        self.assertEqual(reopened.lead_detail(one['id'])['lead']['summary'], one['summary'])

    def test_manager_empty_list_missing_detail_and_invalid_pagination(self):
        self.assertEqual(self.request('/api/leads')['items'], [])
        for path, status in [('/api/leads/' + '0' * 32, 404), ('/api/leads?limit=101', 400),
                             ('/api/leads?offset=-1', 400), ('/api/leads?limit=invalid', 400),
                             ('/api/leads?q=' + 'a' * 201, 400)]:
            with self.subTest(path=path), self.assertRaises(urllib.error.HTTPError) as error:
                self.request(path)
            self.assertEqual(error.exception.code, status)

    def test_all_sessions_remain_accessible_after_200(self):
        ids = [self.store.create() for _ in range(205)]
        self.store.add(ids[0], 'user', 'Самый ранний диалог без заявки')
        visible = []
        for offset in range(0,250,50):
            visible += self.request('/api/sessions?limit=50&offset='+str(offset))
        self.assertEqual({s['id'] for s in visible}, set(ids))
        self.assertEqual(len(visible),205)
        self.assertEqual(self.request('/api/sessions/'+ids[0])['messages'][0]['content'], 'Самый ранний диалог без заявки')

    def test_invalid_session_pagination(self):
        for path in ('/api/sessions?limit=0','/api/sessions?limit=101','/api/sessions?offset=-1','/api/sessions?limit=bad'):
            with self.subTest(path=path), self.assertRaises(urllib.error.HTTPError) as error:
                self.request(path)
            self.assertEqual(error.exception.code,400)

    def test_manager_assets_are_served(self):
        for path, mime in [('/manager', 'text/html'), ('/manager.js', 'text/javascript'),
                           ('/manager.css', 'text/css')]:
            with self.subTest(path=path), urllib.request.urlopen(self.url + path) as response:
                self.assertEqual(response.status, 200)
                self.assertTrue(response.headers['Content-Type'].startswith(mime))
                self.assertTrue(response.read())


if __name__ == "__main__":
    unittest.main()
