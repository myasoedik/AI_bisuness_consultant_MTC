"""Local, single-user prototype HTTP server. Run: python -m energytool.server."""
import json
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from .core import Consultant, ROOT, load_env
from .storage import Store


def make_server(host="127.0.0.1", port=8000, consultant=None, store=None):
    consultant = consultant or Consultant()
    store = store or Store(os.getenv("DB_PATH", str(ROOT / "data" / "energytool.sqlite3")))
    locks = [threading.Lock() for _ in range(64)]

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Never log conversations or contact data.

        def send(self, status, payload, mime="application/json; charset=utf-8"):
            body = json.dumps(payload, ensure_ascii=False).encode() if mime.startswith("application/json") else payload
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/api/status":
                return self.send(200, {"llm": consultant.configured and not consultant.external_blocked, "model": consultant.model, "demo": consultant.demo,
                                       "external_blocked": consultant.external_blocked,
                                       "chunks": len(consultant.searcher.chunks), "documents": len({c.document for c in consultant.searcher.chunks})})
            if path == "/api/sessions":
                return self.send(200, store.list_sessions())
            if path == "/api/leads":
                params = parse_qs(urlparse(self.path).query)
                try:
                    limit = int(params.get("limit", ["50"])[0])
                    offset = int(params.get("offset", ["0"])[0])
                    query = params.get("q", [""])[0].strip()
                    if not 1 <= limit <= 100 or offset < 0 or len(query) > 200:
                        raise ValueError()
                except ValueError:
                    return self.send(400, {"error": "Некорректные параметры списка заявок"})
                return self.send(200, store.list_leads(query, limit, offset))
            match = re.fullmatch(r"/api/leads/([a-f0-9]{32})", path)
            if match:
                detail = store.lead_detail(match[1])
                return self.send(200, detail) if detail else self.send(404, {"error": "Заявка не найдена"})
            match = re.fullmatch(r"/api/sessions/([a-f0-9]{32})", path)
            if match:
                session = store.session(match[1])
                return self.send(200, {"session": session, "messages": store.messages(match[1]), "leads": store.leads(match[1])}) if session else self.send(404, {"error": "Диалог не найден"})
            files = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/style.css": ("style.css", "text/css; charset=utf-8"),
                     "/manager": ("manager.html", "text/html; charset=utf-8"),
                     "/manager.js": ("manager.js", "text/javascript; charset=utf-8"),
                     "/manager.css": ("manager.css", "text/css; charset=utf-8")}
            if path in files:
                filename, mime = files[path]
                return self.send(200, (ROOT / "web" / filename).read_bytes(), mime)
            self.send(404, {"error": "Не найдено"})

        def do_POST(self):
            # Browser cross-origin mutations are not accepted by the local prototype.
            origin = self.headers.get("Origin")
            if origin and urlparse(origin).netloc != self.headers.get("Host"):
                return self.send(403, {"error": "Недопустимый источник запроса"})
            try:
                length = int(self.headers.get("Content-Length", 0))
                if not 0 <= length <= 40000:
                    return self.send(413, {"error": "Слишком большой запрос"})
                data = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(data, dict):
                    raise ValueError()
            except (ValueError, UnicodeDecodeError):
                return self.send(400, {"error": "Некорректный JSON"})
            path = urlparse(self.path).path
            if path == "/api/sessions":
                return self.send(201, {"id": store.create()})
            sid = data.get("session_id", "")
            if not isinstance(sid, str) or not re.fullmatch(r"[a-f0-9]{32}", sid):
                return self.send(400, {"error": "Некорректный диалог"})
            with locks[int(sid[:8], 16) % len(locks)]:
                session = store.session(sid)
                if not session:
                    return self.send(404, {"error": "Диалог не найден"})
                if path == "/api/close":
                    store.close(sid)
                    return self.send(200, {"ok": True})
                if session["closed"]:
                    return self.send(409, {"error": "Диалог завершён. Начните новый."})
                if path == "/api/chat":
                    text = data.get("message")
                    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 6000:
                        return self.send(400, {"error": "Введите сообщение от 1 до 6000 символов"})
                    request_id = data.get('request_id')
                    if request_id is not None and (not isinstance(request_id,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{8,80}',request_id)):
                        return self.send(400, {"error": "Некорректный идентификатор запроса"})
                    try:
                        cached = store.cached_turn(sid,request_id,text.strip())
                    except ValueError as error:
                        return self.send(409, {"error": str(error)})
                    if cached:
                        return self.send(200,cached)
                    history = [{"role": m["role"], "content": m["content"]} for m in store.messages(sid)
                               if m['role']=='user' or m['metadata'].get('mode')=='llm']
                    history.append({'role':'user','content':text.strip()})
                    result = consultant.answer(history)
                    store.save_turn(sid,text.strip(),result,request_id)
                    return self.send(200, result)
                if path == "/api/leads":
                    fields = [data.get(k, "") for k in ("name", "phone", "company")]
                    if not all(isinstance(v, str) and 1 <= len(v.strip()) <= 200 for v in fields):
                        return self.send(400, {"error": "Заполните имя, телефон и компанию"})
                    if not re.fullmatch(r'[+\d()\s-]+',fields[1]) or not 10 <= len(re.sub(r"\D", "", fields[1])) <= 15:
                        return self.send(400, {"error": "Телефон должен содержать от 10 до 15 цифр"})
                    if data.get("test_data") is not True:
                        return self.send(400, {"error": "Подтвердите использование тестовых данных"})
                    request_id = data.get('request_id')
                    if request_id is not None and (not isinstance(request_id,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{8,80}',request_id)):
                        return self.send(400, {"error": "Некорректный идентификатор запроса"})
                    try:
                        lead = store.lead(sid, *(v.strip() for v in fields), request_id=request_id)
                    except ValueError as error:
                        return self.send(409, {"error": str(error)})
                    return self.send(201,lead)
                self.send(404, {"error": "Не найдено"})

    return ThreadingHTTPServer((host, port), Handler)


if __name__ == "__main__":
    load_env()
    host, port = os.getenv("HOST", "127.0.0.1"), int(os.getenv("PORT", "8000"))
    server = make_server(host, port)
    print(f"EnergyTool: http://{host}:{port}", flush=True)
    server.serve_forever()
