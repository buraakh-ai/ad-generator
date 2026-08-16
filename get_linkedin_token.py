import webbrowser
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests
import os

from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.getenv("LINKEDIN_CLIENT_ID")
CLIENT_SECRET = os.getenv("LINKEDIN_CLIENT_SECRET")
REDIRECT_URI = os.getenv("LINKEDIN_REDIRECT_URI")
SCOPE = os.getenv("LINKEDIN_SCOPE")

auth_url = (
    f"https://www.linkedin.com/oauth/v2/authorization"
    f"?response_type=code"
    f"&client_id={CLIENT_ID}"
    f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
    f"&scope={SCOPE}"
)

code_holder = {}

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if 'code' in params:
            code_holder['code'] = params['code'][0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'Authorization successful! You can close this tab.')
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'Error: no code found.')

    def log_message(self, format, *args):
        pass

print('Opening LinkedIn authorization page...')
webbrowser.open(auth_url)
print('Waiting for authorization...')
server = HTTPServer(('localhost', 8000), Handler)
server.handle_request()

if 'code' not in code_holder:
    print('Failed to get code.')
    exit(1)

code = code_holder['code']
print(f'Got code — exchanging for token...')

r = requests.post(
    'https://www.linkedin.com/oauth/v2/accessToken',
    headers={'Content-Type': 'application/x-www-form-urlencoded'},
    data={
        'grant_type':   'authorization_code',
        'code':          code,
        'redirect_uri':  REDIRECT_URI,
        'client_id':     CLIENT_ID,
        'client_secret': CLIENT_SECRET,
    }
)

result = r.json()
print(f'Response: {result}')

if 'access_token' in result:
    print(f'SUCCESS!')
    print(f"Access Token: {result['access_token']}")
    print(f"Expires in: {result.get('expires_in', 'unknown')} seconds")
else:
    print(f'Failed: {result}')
