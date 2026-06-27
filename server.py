from http.server import HTTPServer, SimpleHTTPRequestHandler
import json
import urllib.request
import urllib.parse
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

def ask_claude(context):
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
        # убираем ```json если Claude добавил
        if text.startswith('```'):
            text = text.split('```')[1]
            if text.startswith('json'):
                text = text[4:]
        return json.loads(text)

class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/' or self.path.startswith('/widget'):
            self.path = '/widget.html'
        return super().do_GET()

    def do_POST(self):
        if self.path == '/analyze':
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length))
            context = body.get('context', '')

            try:
                ai = ask_claude(context)
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
                # демо-режим если нет ключа
                results = [
                    {'label': c['label'], 'status': 'bad', 'detail': 'Установите CLAUDE_API_KEY'}
                    for c in CHECKLIST
                ]
                response = json.dumps({'results': results, 'error': str(e)}).encode()

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(response)
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def log_message(self, fmt, *args):
        print(f"[{self.address_string()}] {fmt % args}")

if __name__ == '__main__':
    port = 8000
    print(f"Сервер запущен: http://localhost:{port}")
    print(f"Claude API key: {'установлен ✓' if CLAUDE_API_KEY else 'НЕ установлен — работает демо-режим'}")
    HTTPServer(('', port), Handler).serve_forever()
