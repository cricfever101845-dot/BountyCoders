"""Regression coverage for the production API gateway and history query."""
import io
from email.message import Message
from urllib.error import HTTPError

import app as application


def upstream(status, body, content_type):
    headers = Message()
    headers['Content-Type'] = content_type
    return HTTPError('https://backend.example/api/test', status, 'test', headers, io.BytesIO(body))


def test_proxy_html_write_is_not_replayed(monkeypatch):
    calls = []

    def open_request(req, timeout):
        calls.append(req)
        raise upstream(502, b'<!DOCTYPE html><html>gateway</html>', 'text/html')

    monkeypatch.setenv('BACKEND_URL', 'https://backend.example')
    monkeypatch.setattr(application, 'urlopen', open_request)
    with application.app.test_request_context('/api/submit_answer', method='POST', json={'code': 'print(1)'}):
        response = application.app.make_response(application._proxy_api_request())
        assert response.status_code == 502
        assert response.is_json
        assert len(calls) == 1


def test_proxy_retries_safe_read(monkeypatch):
    responses = iter([
        upstream(503, b'<html>starting</html>', 'text/html'),
        upstream(200, b'{"entries":[]}', 'application/json'),
    ])
    monkeypatch.setenv('BACKEND_URL', 'https://backend.example')
    monkeypatch.setattr(application.time, 'sleep', lambda seconds: None)
    monkeypatch.setattr(application, 'urlopen', lambda req, timeout: next(responses))
    with application.app.test_request_context('/api/leaderboard'):
        response = application.app.make_response(application._proxy_api_request())
        assert response.status_code == 200
        assert response.get_json() == {'entries': []}


def test_proxy_rejects_invalid_json_and_redirects(monkeypatch):
    monkeypatch.setenv('BACKEND_URL', 'https://backend.example')
    for status, body, mime in [(200, b'{invalid', 'application/json'), (302, b'', 'text/html')]:
        monkeypatch.setattr(application, 'urlopen', lambda req, timeout: upstream(status, body, mime))
        with application.app.test_request_context('/api/test', method='POST'):
            response = application.app.make_response(application._proxy_api_request())
            assert response.status_code == 502
            assert response.is_json
    assert application._NoApiRedirect().redirect_request(None, None, 302, '', {}, 'https://other.example') is None


def test_history_completed_courses():
    with application.app.test_client() as client:
        with client.session_transaction() as session:
            session['user_id'] = 1
        response = client.get('/api/course_history')
        assert response.status_code == 200
        assert isinstance(response.get_json()['completed'], list)

def test_readiness_probe_is_short_and_does_not_forward_credentials(monkeypatch):
    calls = []

    def fake_open(req, timeout):
        calls.append((req, timeout))
        return upstream(503, b'<html>starting</html>', 'text/html')

    monkeypatch.setenv('BACKEND_URL', 'https://backend.example')
    monkeypatch.setattr(application, 'urlopen', fake_open)
    with application.app.test_request_context('/api/service_ready', headers={'Authorization': 'Bearer test-only', 'Cookie': 'session=example'}):
        response = application.app.make_response(application._proxy_api_request())
        assert response.status_code == 503
        assert response.is_json
    assert len(calls) == 1
    req, timeout = calls[0]
    assert req.full_url == 'https://backend.example/ready'
    assert timeout <= 12
    assert req.get_header('Authorization') is None
    assert req.get_header('Cookie') is None


def test_local_readiness_alias_returns_json():
    with application.app.test_client() as client:
        response = client.get('/api/service_ready')
        assert response.status_code == 200
        assert response.get_json() == {'status': 'ready', 'database': 'connected'}
        assert response.headers['Cache-Control'] == 'no-store'
