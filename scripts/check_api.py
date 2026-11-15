"""Test the configured API using synthetic data only. Never print the key."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding='utf-8')
from energytool.core import Consultant

bot = Consultant()
if len(sys.argv) > 1:
    bot.model = sys.argv[1]
started = time.perf_counter()
try:
    answer = bot.complete([
        {"role": "system", "content": "Ответь кратко по-русски на вопрос пользователя."},
        {"role": "user", "content": "Вымышленная компания имеет три склада. Сколько у неё складов?"},
    ])
    print(json.dumps({"ok": True, "model": bot.model, "answer": answer[:1000],
                      "seconds": round(time.perf_counter() - started, 2)}, ensure_ascii=False))
except Exception as error:
    print(json.dumps({"ok": False, "error_type": type(error).__name__,
                      "http_status": getattr(error, "code", None)}))
    sys.exit(1)
