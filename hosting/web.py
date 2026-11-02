"""Same-origin HTTP entry point for the isolated Render demonstration."""
import os
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.applications import Starlette
from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles


def public_origin():
    value = (os.getenv('DEMO_PUBLIC_ORIGIN') or os.getenv('RENDER_EXTERNAL_URL') or '').strip()
    address = urlsplit(value)
    local = address.hostname in ('localhost', '127.0.0.1', '::1') and os.getenv('RENDER') != 'true'
    if (not address.hostname or address.scheme not in (('https', 'http') if local else ('https',))
            or address.username is not None or address.password is not None or address.path not in ('', '/')
            or address.query or address.fragment):
        raise RuntimeError('Configure the public demo origin with RENDER_EXTERNAL_URL or DEMO_PUBLIC_ORIGIN.')
    return f'{address.scheme}://{address.netloc.lower()}'


ORIGIN = public_origin()
os.environ['COOKIE_SECURE'] = '1'
os.environ['ALLOWED_ORIGINS'] = ORIGIN

# Confirm the dedicated database before importing main, which runs schema migrations.
from hosting.bootstrap_demo import require_ready_demo
require_ready_demo()

STATIC = Path(__file__).resolve().parent.parent / 'demo-static'
if not (STATIC / 'index.html').is_file() or not (STATIC / 'assets').is_dir():
    raise RuntimeError('The demo web bundle is missing.')

from database import engine
from main import app as api

# Only the wrapper which verified the synthetic database enables this role.
api.state.demo_editor_username = os.getenv('DEMO_EDITABLE_GUEST')


def health(request):
    # The public probe reports connectivity without returning migration or deployment details.
    try:
        with engine.connect() as connection:
            connection.execute(text('SELECT 1'))
    except SQLAlchemyError:
        return JSONResponse({'status': 'unavailable'}, status_code=503)
    return JSONResponse({'status': 'ok'})


def public_file(request):
    return FileResponse(STATIC / (request.url.path.strip('/') or 'index.html'))


def robots(request):
    return PlainTextResponse('User-agent: *\nDisallow: /\n')


# The SPA uses hash routes. Only bundle assets and these named files are public.
site = Starlette(routes=[
    Route('/health', health), Route('/robots.txt', robots),
    *(Route(path, public_file) for path in ('/', '/index.html', '/brand.svg', '/theme-init.js')),
    Mount('/assets', StaticFiles(directory=STATIC / 'assets')),
])
DISABLED = ('/api/v1/assistant', '/api/v1/attachments')
SECURITY_HEADERS = {
    'Referrer-Policy': 'no-referrer', 'X-Content-Type-Options': 'nosniff',
    'X-Robots-Tag': 'noindex, nofollow', 'X-Frame-Options': 'DENY',
    'Content-Security-Policy': ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                                "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; "
                                "object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"),
}


def guard(method, path, headers):
    if ('//' in path or '\\' in path or '\x00' in path or any(part.startswith('.') for part in path.split('/'))
            or (path.startswith('/assets/') and path.endswith('.map'))):
        return JSONResponse({'detail': 'Not found'}, status_code=404)
    if not path.startswith('/api/'):
        return None
    if not path.startswith('/api/v1/'):
        return JSONResponse({'detail': 'Not found'}, status_code=404)
    if any(path == prefix or path.startswith(prefix + '/') for prefix in DISABLED):
        return JSONResponse({'detail': 'Недоступно в демоверсии / Демонұсқада қолжетімсіз'}, status_code=403)
    if method in ('GET', 'HEAD', 'OPTIONS'):
        return None

    content_type = headers.get('content-type', '').split(';', 1)[0].strip().lower()
    if content_type.startswith('multipart/') or content_type == 'application/x-www-form-urlencoded':
        return JSONResponse({'detail': 'Недопустимый тип запроса / Сұрау түріне рұқсат жоқ'}, status_code=415)

    # Host and forwarding headers belong to the request, not to our origin configuration.
    origin = headers.get('origin')
    if origin == ORIGIN:
        return None
    cli_login = (path.rstrip('/') == '/api/v1/auth/login' and content_type == 'application/json'
                 and 'cookie' not in headers)
    bearer = headers.get('authorization', '').lower().startswith('bearer ')
    if (origin is None and not headers.get('sec-fetch-site') and (cli_login or bearer)):
        return None
    return JSONResponse({'detail': 'Недопустимый источник запроса / Сұрау көзі рұқсат етілмеген'}, status_code=403)


async def app(scope, receive, send):
    if scope['type'] != 'http':
        await api(scope, receive, send)
        return
    path = scope['path']
    api_path = path.startswith('/api/')
    response = guard(scope['method'], path, Headers(scope=scope))

    async def send_response(message):
        if message['type'] == 'http.response.start':
            headers = MutableHeaders(scope=message)
            headers.update(SECURITY_HEADERS)
            if api_path or path in ('/', '/index.html', '/health'):
                headers['Cache-Control'] = 'no-store'
            if path.rstrip('/') == '/api/v1/auth/logout' and 'set-cookie' in headers:
                headers['set-cookie'] = 'hr_session=""; Max-Age=0; Path=/; HttpOnly; Secure; SameSite=Strict'
        await send(message)

    if response is not None:
        await response(scope, receive, send_response)
    else:
        await (api if api_path else site)(scope, receive, send_response)
