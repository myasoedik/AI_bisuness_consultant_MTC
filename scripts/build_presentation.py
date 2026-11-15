"""Create the required PDF presentation. Dev-only dependency: PyMuPDF."""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent.parent
if (ROOT/'tmp'/'pdf-tools').is_dir():
    sys.path.insert(0,str(ROOT/'tmp'/'pdf-tools'))
import pymupdf as fitz

OUT=ROOT/'output'/'pdf'
PREVIEW=ROOT/'tmp'/'pdfs'
OUT.mkdir(parents=True,exist_ok=True);PREVIEW.mkdir(parents=True,exist_ok=True)
FONT=Path('C:/Windows/Fonts/arial.ttf')
BOLD=Path('C:/Windows/Fonts/arialbd.ttf')
if not FONT.exists():
    FONT=Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
    BOLD=Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')

slides=[
 ('ИИ-консультант\nEnergyTool', 'Локальный MVP для МТС True Tech Hack&Change 2026', [
  'Репозиторий: https://github.com/myasoedik/AI_bisuness_consultant_MTC',
  'Проверка: README → .env и база → Docker → чат → тестовая заявка → экран менеджера. Кейс: docker compose up --build -d',
  'Демо: docker compose -f compose.yaml -f compose.demo.yaml up --build -d',
  'Чат: localhost:8000   Менеджер: localhost:8000/manager. Демо использует вымышленную базу; для кейса нужен API организаторов.'
 ], 'README.md; docs/ACCEPTANCE.md'),
 ('Задача клиента', 'Понятный следующий шаг по ситуации предприятия', [
  'Клиент описывает проблему своими словами. Ему нужно понять, какие данные собрать и какое направление решения рассмотреть.',
  'Консультант уточняет обстоятельства и использует сведения из выбранной базы знаний.',
  'Менеджер получает контакты, исходную задачу и историю обсуждения. Повторный сбор уже сообщённых деталей сокращается.',
  'Влияние на конверсию и экономию времени пока не измерено.'
 ], 'Задание кейса, стр. 4–6; energytool/core.py; energytool/storage.py'),
 ('Сценарий консультации', 'Клиент сохраняет заявку после обсуждения задачи', [
  '01  Вопрос клиента и уточнение недостающих параметров.',
  '02  Ответ с опорой на найденные документы. Источники и время доступны в режиме отладки.',
  '03  Форма с тестовыми ФИО, телефоном и компанией. Сервер сохраняет заявку и резюме.',
  '04  Менеджер открывает карточку с контактами и полной перепиской. Новый диалог клиента не наследует прежний контекст.'
 ], 'web/app.js; web/manager.js; energytool/server.py'),
 ('Общее ядро для чата и сабмита', 'Python 3.13 и SQLite, без внешних runtime-зависимостей', [
  'Поиск читает Markdown/TXT и ZIP, разбивает документы по заголовкам и ранжирует фрагменты BM25.',
  'Словарь формулировок и объединение рангов учитывают последний вопрос и предыдущие реплики клиента.',
  'Модель получает до восьми фрагментов и всю историю сессии. При превышении лимита запрос останавливается явно; история не обрезается.',
  'SQLite хранит сессии, заявки и результаты повторных запросов. Docker запускает приложение одной командой.'
 ], 'energytool/core.py; energytool/storage.py; solution.py; compose.yaml'),
 ('Два режима проверки', 'Материалы кейса остаются локальными при тестировании OpenRouter', [
  'Кейсовый режим: 19 исходных документов. Для ответов по EnergyTool нужен API организаторов или согласованный внешний сервис.',
  'Демо: отдельная вымышленная база «СкладЛаб» и бесплатная облачная модель OpenRouter. Ноутбук не запускает LLM.',
  'Режимы используют отдельные тома истории. База кейса не отправляется в OpenRouter по умолчанию.',
  'Пример демо: клиент сообщает о трёх складах. Консультант уточняет, на всех ли объектах выросли расходы.'
 ], 'compose.demo.yaml; demo-knowledge-base/demo.md; scripts/check_web.py'),
 ('Проверка реализации', '23 автоматических теста прошли', [
  'Проверены 205 сессий в истории, середина длинного диалога, отказ без сведений, заявки, повторы запросов и карточка менеджера.',
  'Точка входа solution.py проверена с синтетическими ZIP и CSV через локальный имитатор API.',
  'На 18 открытых примерах поиск находит все заданные признаки опорных сведений среди восьми фрагментов. До доработки: 13/18, после: 18/18.',
  'Это метрика поиска на наборе разработки. Она не является оценкой ответов Qwen, скрытых тестов или LLM-судьи.'
 ], 'tests/test_app.py; tests/test_submission.py; scripts/evaluate_retrieval.py'),
 ('Рабочее место менеджера', 'Заявки и связанные диалоги доступны внутри прототипа', [
  'Список показывает компанию, имя, телефон и время создания. Поиск поддерживает кириллицу без учёта регистра.',
  'Карточка содержит сохранённое резюме и все сообщения соответствующей сессии. Список обновляется автоматически.',
  'Чтение заявки не вызывает модель и не отправляет данные в CRM. Повтор одного запроса не создаёт новую заявку.',
  'Сохранённые данные переживают перезапуск контейнера. Используются только выдуманные контактные данные.'
 ], 'web/manager.html; energytool/storage.py; tests/test_app.py'),
 ('Границы MVP и завершение сдачи', 'Конкурсная проверка остаётся отдельным этапом', [
  'API Qwen и входные данные предоставляет платформа организаторов. Передаём ZIP без ключей; для допуска требуется ненулевой результат LLM-судьи.',
  'Качество ответов по настоящей базе с Qwen ещё не измерено. Векторный индекс и реранкер не подключены.',
  'Прототип предназначен для локального показа. Перед внешним внедрением нужны авторизация менеджеров, изоляция посетителей и политика хранения.',
  'Будущая интеграция: серверный адаптер передачи заявки в CRM. Живой оператор не входит в обязательный сценарий текущего задания.'
 ], 'docs/ACCEPTANCE.md; docs/ARCHITECTURE.md; задание кейса, стр. 7–12'),
]

doc=fitz.open()
def text(page,rect,value,size=22,bold=False,color=(.12,.16,.20)):
    remainder=page.insert_textbox(fitz.Rect(rect),value,fontname='bold' if bold else 'regular',fontsize=size,color=color,lineheight=1.22)
    if remainder<0:
        raise RuntimeError('Text overflow: '+value[:60])

for number,(title,subtitle,paragraphs,source) in enumerate(slides,1):
    page=doc.new_page(width=1280,height=720)
    page.insert_font(fontname='regular',fontfile=str(FONT))
    page.insert_font(fontname='bold',fontfile=str(BOLD))
    text(page,(64,30,1100,56),'ENERGYTOOL / ПРОТОТИП / 15.11.2026',13,True,(.7,.1,.17))
    title_y=80
    title_h=136 if number==1 else 75
    text(page,(64,title_y,1210,title_y+title_h),title,48 if number==1 else 40,True)
    sy=title_y+title_h+5
    text(page,(64,sy,1210,sy+52),subtitle,23,False,(.39,.43,.48))
    y=sy+70
    gap=77 if number==1 else 94
    for paragraph in paragraphs:
        text(page,(64,y,1200,y+gap-12),paragraph,19 if number==1 else 23)
        y+=gap
    if number==1:
        page.insert_link({'kind':fitz.LINK_URI, 'from':fitz.Rect(64,291,1200,356),
                          'uri':'https://github.com/myasoedik/AI_bisuness_consultant_MTC'})
    text(page,(64,670,1150,703),'Источники: '+source,11,False,(.48,.52,.56))
    text(page,(1180,666,1230,704),f'{number:02d}',18,True,(.7,.1,.17))

path=OUT/'energytool-presentation.pdf'
doc.set_metadata({'title':'EnergyTool — локальный MVP','author':'EnergyTool project','subject':'Архитектура, проверка и сценарий сдачи'})
doc.save(path,garbage=4,deflate=True)
doc.close()
(ROOT/'docs'/'presentation.pdf').write_bytes(path.read_bytes())
with fitz.open(path) as check:
    assert len(check)==8
    for i,page in enumerate(check):
        assert page.get_text().strip()
        page.get_pixmap(matrix=fitz.Matrix(.8,.8)).save(PREVIEW/f'slide-{i+1}.png')
print('Created and rendered 8 PDF pages.')
