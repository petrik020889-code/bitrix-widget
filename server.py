from http.server import HTTPServer, SimpleHTTPRequestHandler
import json
import urllib.request
import os

CLAUDE_API_KEY = os.environ.get('CLAUDE_API_KEY', '')

CHECKLIST = [
    {'key': 'need',     'label': 'Потребность выяснена',      'question': 'Что именно нужно клиенту?'},
    {'key': 'lpr',      'label': 'ЛПР определён',             'question': 'Кто принимает решение о покупке?'},
    {'key': 'budget',   'label': 'Бюджет подтверждён',        'question': 'Какой бюджет одобрен?'},
    {'key': 'deadline', 'label': 'Срок договора уточнён',     'question': 'Когда нужно подписать договор?'},
    {'key': 'delivery', 'label': 'Дата поставки названа',     'question': 'К какой дате нужно оборудование?'},
    {'key': 'kp_sent',  'label': 'КП отправлено',             'question': 'Было ли отправлено коммерческое предложение?'},
    {'key': 'feedback', 'label': 'Обратная связь по КП',      'question': 'Клиент дал обратную связь по КП?'},
]

def ask_claude_qualify(context):
    questions = '\n'.join([f"- {c['key']}: {c['question']}" for c in CHECKLIST])
    prompt = f"""Ты анализируешь CRM-сделку. На основе данных ниже ответь на каждый вопрос: выяснено (yes) или нет (no).
Если есть конкретная информация — добавь короткую деталь (до 60 символов).

Данные сделки:
{context}

Вопросы (ответь строго в JSON):
{questions}

Формат ответа — только JSON, без пояснений:
{{
  "need":     {{"status": "yes/no", "detail": "..."}},
  "lpr":      {{"status": "yes/no", "detail": "..."}},
  "budget":   {{"status": "yes/no", "detail": "..."}},
  "deadline": {{"status": "yes/no", "detail": "..."}},
  "delivery": {{"status": "yes/no", "detail": "..."}},
  "kp_sent":  {{"status": "yes/no", "detail": "..."}},
  "feedback": {{"status": "yes/no", "detail": "..."}}
}}"""

    body = json.dumps({
        'model': 'claude-haiku-4-5-20251001',
        'max_tokens': 500,
        'messages': [{'role': 'user', 'content': prompt}]
    }).encode()

    req = urllib.request.Request(
        'https://api.anthropic.com/v1/messages',
        data=body,
        headers={
            'x-api-key': CLAUDE_API_KEY,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json',
        }
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
        text = data['content'][0]['text'].strip()
        if text.startswith('```'):
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
        return json.loads(text)


def ask_claude_questions(missing_labels, context):
    items = '\n'.join([f'- {l}' for l in missing_labels])
    prompt = f"""Ты опытный менеджер по продажам B2B. Помоги коллеге задать клиенту вопросы, чтобы мягко выяснить недостающую информацию.

Контекст сделки:
{context}

Что нужно выяснить:
{items}

Для каждого пункта придумай один вопрос клиенту. Требования:
- Не в лоб, а мягко и естественно, как в живом разговоре
- Звучит как забота о клиенте, а не допрос
- Отвечая на вопрос, клиент невольно даёт именно нужную информацию
- Короткий, разговорный, без канцелярщины
- На русском языке

Ответь строго в формате JSON-массива без пояснений:
[
  {{"label": "название критерия", "question": "текст вопроса"}},
  ...
]"""

    body = json.dumps({
        'model': 'claude-haiku-4-5-20251001',
        'max_tokens': 800,
        'messages': [{'role': 'user', 'content': prompt}]
    }).encode()

    req = urllib.request.Request(
        'https://api.anthropic.com/v1/messages',
        data=body,
        headers={
            'x-api-key': CLAUDE_API_KEY,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json',
        }
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
        text = data['content'][0]['text'].strip()
        if text.startswith('```'):
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
        return json.loads(text)


def serve_widget(handler):
    with open('widget.html', 'rb') as f:
        content = f.read()
    handler.send_response(200)
    handler.send_header('Content-Type', 'text/html; charset=utf-8')
    handler.send_header('Access-Control-Allow-Origin', '*')
    handler.end_headers()
    handler.wfile.write(content)


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/' or self.path.startswith('/widget'):
            serve_widget(self)
        else:
            super().do_GET()

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        raw = self.rfile.read(length)

        if self.path == '/analyze':
            body = json.loads(raw) if raw else {}
            context = body.get('context', '')
            try:
                ai = ask_claude_qualify(context)
                results = []
                for c in CHECKLIST:
                    item = ai.get(c['key'], {})
                    results.append({
                        'label': c['label'],
                        'status': 'ok' if item.get('status') == 'yes' else 'bad',
                        'detail': item.get('detail', '')
                    })
                response = json.dumps({'results': results}).encode()
            except Exception as e:
                results = [
                    {'label': c['label'], 'status': 'bad', 'detail': str(e)[:50]}
                    for c in CHECKLIST
                ]
                response = json.dumps({'results': results, 'error': str(e)}).encode()

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(response)

        elif self.path == '/questions':
            body = json.loads(raw) if raw else {}
            missing = body.get('missing', [])
            context = body.get('context', '')
            try:
                result = ask_claude_questions(missing, context)
                response = json.dumps({'questions': result}).encode()
            except Exception as e:
                response = json.dumps({'error': str(e)}).encode()

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(response)

        else:
            serve_widget(self)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def log_message(self, fmt, *args):
        print(f"[{self.address_string()}] {fmt % args}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    print(f"Сервер запущен: http://localhost:{port}")
    print(f"Claude API key: {'установлен ✓' if CLAUDE_API_KEY else 'НЕ установлен'}")
    HTTPServer(('', port), Handler).serve_forever()
