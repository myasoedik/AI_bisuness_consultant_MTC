"""SQLite persistence. New sessions never inherit previous session context."""
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, created_at TEXT, title TEXT, closed INTEGER DEFAULT 0);
                CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY, session_id TEXT REFERENCES sessions(id),
                    role TEXT, content TEXT, metadata TEXT, created_at TEXT);
                CREATE TABLE IF NOT EXISTS leads(id TEXT PRIMARY KEY, session_id TEXT REFERENCES sessions(id),
                    name TEXT, phone TEXT, company TEXT, summary TEXT, created_at TEXT);
                CREATE TABLE IF NOT EXISTS turns(session_id TEXT REFERENCES sessions(id), request_id TEXT,
                    question TEXT, result TEXT, PRIMARY KEY(session_id, request_id));
                CREATE INDEX IF NOT EXISTS messages_session ON messages(session_id,id);
                CREATE INDEX IF NOT EXISTS leads_created ON leads(created_at);
            """)
            columns = {row[1] for row in db.execute('PRAGMA table_info(leads)')}
            if 'request_id' not in columns:
                db.execute('ALTER TABLE leads ADD COLUMN request_id TEXT')
            db.execute('CREATE UNIQUE INDEX IF NOT EXISTS leads_request ON leads(session_id,request_id)')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.create_function("casefold", 1, lambda value: (value or "").casefold(), deterministic=True)
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self):
        sid = uuid.uuid4().hex
        with self.connect() as db:
            db.execute("INSERT INTO sessions(id,created_at,title) VALUES(?,?,?)", (sid, now(), "Новый диалог"))
        return sid

    def session(self, sid):
        with self.connect() as db:
            row = db.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
            return dict(row) if row else None

    def close(self, sid):
        with self.connect() as db:
            db.execute("UPDATE sessions SET closed=1 WHERE id=?", (sid,))

    def list_sessions(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM sessions ORDER BY created_at DESC LIMIT 200")]

    def messages(self, sid):
        with self.connect() as db:
            return [{**dict(row), "metadata": json.loads(row["metadata"])} for row in
                    db.execute("SELECT * FROM messages WHERE session_id=? ORDER BY id", (sid,))]

    def add(self, sid, role, content, metadata=None):
        with self.connect() as db:
            db.execute("INSERT INTO messages(session_id,role,content,metadata,created_at) VALUES(?,?,?,?,?)",
                       (sid, role, content, json.dumps(metadata or {}, ensure_ascii=False), now()))
            if role == "user":
                db.execute("UPDATE sessions SET title=? WHERE id=? AND title='Новый диалог'", (content[:64], sid))

    def cached_turn(self, sid, request_id, question):
        if not request_id:
            return None
        with self.connect() as db:
            row = db.execute('SELECT question,result FROM turns WHERE session_id=? AND request_id=?', (sid,request_id)).fetchone()
        if row:
            if row['question'] != question:
                raise ValueError('Повтор запроса содержит другое сообщение')
            return json.loads(row['result'])
        return None

    def save_turn(self, sid, question, result, request_id=None):
        with self.connect() as db:
            for role, content, metadata in [('user',question,{}), ('assistant',result['answer'],{k:v for k,v in result.items() if k!='answer'})]:
                db.execute('INSERT INTO messages(session_id,role,content,metadata,created_at) VALUES(?,?,?,?,?)',
                           (sid,role,content,json.dumps(metadata,ensure_ascii=False),now()))
            db.execute("UPDATE sessions SET title=? WHERE id=? AND title='Новый диалог'", (question[:64],sid))
            if request_id:
                db.execute('INSERT INTO turns VALUES(?,?,?,?)', (sid,request_id,question,json.dumps(result,ensure_ascii=False)))

    def lead(self, sid, name, phone, company, request_id=None):
        messages = self.messages(sid)
        # Deterministic, auditable summary: do not infer unprovided client attributes.
        requests = [m["content"] for m in messages if m["role"] == "user"]
        summaries = [m["content"] for m in messages if m["role"] == "assistant" and m["metadata"].get("mode") == "llm"]
        summary = "Компания: " + company + "\nКонтакт: " + name + ", " + phone
        summary += "\nИсходная задача:\n" + (requests[0][:1200] if requests else 'Клиент оставил контакты без предварительной консультации.')
        if len(requests) > 1:
            summary += "\nУточнения клиента:\n" + "\n".join("• " + t[:700] for t in requests[1:][-8:])
        if summaries:
            summary += "\nПоследняя консультация:\n" + summaries[-1][:2000]
        summary += "\nСледующий шаг: специалисту уточнить условия и подготовить предварительную оценку."
        lead = {"id": uuid.uuid4().hex, "session_id": sid, "name": name, "phone": phone,
                "company": company, "summary": summary, "created_at": now()}
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if request_id:
                old = db.execute('SELECT * FROM leads WHERE session_id=? AND request_id=?', (sid,request_id)).fetchone()
                if old:
                    if (old['name'],old['phone'],old['company']) != (name,phone,company):
                        raise ValueError('Повтор запроса содержит другие контактные данные')
                    return dict(old)
            db.execute("INSERT INTO leads(id,session_id,name,phone,company,summary,created_at,request_id) VALUES(:id,:session_id,:name,:phone,:company,:summary,:created_at,:request_id)",
                       {**lead, 'request_id': request_id})
        return lead

    def leads(self, sid):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM leads WHERE session_id=? ORDER BY created_at", (sid,))]

    def list_leads(self, query="", limit=50, offset=0):
        where = "WHERE instr(casefold(l.company || char(10) || l.name || char(10) || l.phone), ?) > 0"
        with self.connect() as db:
            total = db.execute("SELECT count(*) FROM leads").fetchone()[0]
            filtered = db.execute("SELECT count(*) FROM leads l " + where, (query.casefold(),)).fetchone()[0]
            rows = db.execute("""SELECT l.id, l.session_id, l.name, l.phone, l.company, l.created_at,
                                  s.title AS session_title
                                  FROM leads l JOIN sessions s ON s.id=l.session_id """ + where +
                              " ORDER BY l.created_at DESC, l.id DESC LIMIT ? OFFSET ?",
                              (query.casefold(), limit, offset))
            return {"items": [dict(row) for row in rows], "total": total, "filtered": filtered,
                    "limit": limit, "offset": offset}

    def lead_detail(self, lead_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
        if not row:
            return None
        lead = dict(row)
        return {"lead": lead, "session": self.session(lead["session_id"]),
                "messages": self.messages(lead["session_id"])}
