"""Exercise the local demo chat with synthetic data, never the case knowledge base."""
import json
import urllib.request


def request(path, payload=None):
    data = None if payload is None else json.dumps(payload).encode('utf-8')
    req = urllib.request.Request('http://127.0.0.1:8000' + path, data,
                                 {'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=110) as response:
        return json.load(response)


status = request('/api/status')
if not status.get('demo') or not status.get('llm'):
    raise SystemExit('Expected a running demo with LLM enabled; no message sent.')
print(json.dumps({'status': status}, ensure_ascii=True), flush=True)
sid = request('/api/sessions', {})['id']
try:
    result = request('/api/chat', {'session_id': sid,
                                   'message': 'У нас три склада, хотим сократить расходы на электричество.'})
    print(json.dumps({k: result[k] for k in ('mode', 'answer', 'elapsed_ms', 'error')},
                     ensure_ascii=True), flush=True)
    assert result['mode'] == 'llm', 'The API did not return an LLM response'
    assert result['sources'] and {s['document'] for s in result['sources']} == {'demo.md'}
finally:
    request('/api/close', {'session_id': sid})
