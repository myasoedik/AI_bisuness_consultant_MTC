"""Local evidence coverage on supplied examples. Does not call an LLM or upload data."""
import csv
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from energytool.core import Consultant, MATERIALS, ROOT, parse_question

# Evidence predicates, not answer templates. Scores measure retrieval only.
EVIDENCE = {
    '1': [r'восток|запад'], '2': [r'вертикальн|фасад'],
    '3': [r'поэтап|очеред|наращ'], '4': [r'шифер'],
    '5': [r'SIM|сим-карт|симк'], '6': [r'цех'], '7': [r'ретейл|магазин'],
    '8': [r'тарифн'], '9': [r'год производ'],
    '10': [r'профиль|дорогие часы', r'плата за мощность'],
    '11': [r'реактивн'], '12': [r'аудит', r'750'],
    '13': [r'невыгод|нецелесообраз|недостаточ'],
    '14': [r'накопител', r'дневн|светл|вечер'],
    '15': [r'арендатор', r'фотограф'],
    '16': [r'год|года', r'день и ночь|дневное и ночное|дневн.*ночн', r'вероятност|хищени'],
    '17': [r'двухставочн', r'плата за мощность'],
    '18': [r'тип прибор|модел|количество.*прибор|количеств.*тип', r'схема сбора|способ.*сбор|собираются показания'],
}


def evaluate():
    bot = Consultant(MATERIALS / 'knowledge-base')
    bot.key = ''  # Evaluation is strictly offline even if .env has credentials.
    rows = list(csv.DictReader((MATERIALS / 'demo_questions.csv').open(encoding='utf-8-sig', newline='')))
    cases = []
    started = time.perf_counter()
    for row in rows:
        sources = bot.answer(parse_question(row['question']))['sources']
        text = '\n'.join(s['title'] + '\n' + s['text'] for s in sources)
        text = re.sub(r'\s+', ' ', text)
        checks = [bool(re.search(pattern, text, re.I)) for pattern in EVIDENCE[row['id']]]
        cases.append({'id': row['id'], 'covered': all(checks), 'checks': checks,
                      'sources': [s['id'] for s in sources]})
    return {'dataset': '18 supplied examples; development set, not hidden evaluation',
            'metric': 'All annotated evidence predicates found in retrieved top-8 chunks',
            'covered': sum(c['covered'] for c in cases), 'total': len(cases),
            'elapsed_ms': round((time.perf_counter() - started) * 1000), 'cases': cases}


if __name__ == '__main__':
    result = evaluate()
    target = ROOT / 'output' / 'retrieval-evaluation.json'
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'cases'}))
    print('Missing evidence:', [(c['id'], c['checks']) for c in result['cases'] if not c['covered']])
