"""Exercise the real entry point with a local fake API and synthetic files."""
import csv
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent


class SubmissionTests(unittest.TestCase):
    def test_csv_zip_protocol_and_case_isolation(self):
        calls=[]
        class Api(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_POST(self):
                data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                calls.append(data['messages'])
                body=json.dumps({'choices':[{'finish_reason':'stop','message':{'content':'Тестовый ответ\nВторая строка'}}]}).encode()
                self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        api=ThreadingHTTPServer(('127.0.0.1',0),Api)
        thread=threading.Thread(target=api.serve_forever,daemon=True);thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                p=Path(directory)
                with zipfile.ZipFile(p/'knowledge-base.zip','w') as archive:
                    archive.writestr('synthetic.md','# Учебный продукт\nТестовый учёт складов.')
                with (p/'questions.csv').open('w',encoding='utf-8-sig',newline='') as f:
                    writer=csv.writer(f);writer.writerow(['id','question'])
                    writer.writerows([['001','Пользователь: Уникальный контекст первого кейса\nАссистент: Уточните\nПользователь: Проверяем учёт'],['002','Независимый второй вопрос']])
                env={**os.environ,'DATA_DIR':str(p),'LLM_BASE_URL':f'http://127.0.0.1:{api.server_port}',
                     'LLM_API_KEY':'test-only','LLM_MODEL':'test-only','MAX_WORKERS':'1','DEMO_MODE':'1'}
                result=subprocess.run([sys.executable,str(ROOT/'solution.py')],cwd=p,env=env,capture_output=True,timeout=15)
                self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))
                with (p/'submission.csv').open(encoding='utf-8',newline='') as f: rows=list(csv.DictReader(f))
                self.assertEqual([r['id'] for r in rows],['001','002'])
                self.assertNotIn('\n',rows[0]['answer'])
                self.assertEqual(len(calls),2)
                self.assertNotIn('Уникальный контекст',json.dumps(calls[1],ensure_ascii=False))
                self.assertIn('МТС EnergyTool',calls[0][0]['content'])
        finally:
            api.shutdown();api.server_close();thread.join()
