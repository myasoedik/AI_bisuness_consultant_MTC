"""Competition entry point; test cases have isolated conversation context."""
import csv
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from energytool.core import Consultant, load_env, parse_question


def main():
    load_env()
    data = Path(os.getenv("DATA_DIR", "data"))
    questions = next((data / name for name in ("questions.csv", "train.csv") if (data / name).exists()), None)
    kb = next((data / name for name in ("knowledge-base.zip", "knowledge_base.zip", "kb.zip", "knowledge-base") if (data / name).exists()), None)
    if questions is None or kb is None:
        raise SystemExit("DATA_DIR должен содержать questions.csv и knowledge-base.zip (или каталог knowledge-base)")
    bot = Consultant(kb)
    bot.demo = False  # A submission must not use the synthetic demo persona.
    if not bot.configured:
        raise SystemExit("Для сабмита нужны LLM_BASE_URL и LLM_API_KEY; режим выдержек в сабмите отключён")
    if bot.external_blocked:
        raise SystemExit('Передача базы кейса в OpenRouter отключена. Используйте API организаторов.')
    with questions.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not {'id','question'} <= set(reader.fieldnames or []):
            raise SystemExit('Ожидаются колонки id,question')
        rows = list(reader)
    if any(not row.get('id') or not row.get('question','').strip() for row in rows):
        raise SystemExit('Входные данные содержат пустой id или question')
    def work(row):
        result = bot.answer(parse_question(row["question"]))
        return row["id"], " ".join(result["answer"].split())
    workers = max(1, min(8, int(os.getenv("MAX_WORKERS", "3"))))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        answers = list(pool.map(work, rows))
    with open("submission.csv", "w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, quoting=csv.QUOTE_ALL)
        writer.writerow(["id", "answer"])
        writer.writerows(answers)
    print(f"submission.csv: {len(answers)} answers")


if __name__ == "__main__":
    main()
