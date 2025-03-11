from flask import Flask, request
from flask_cors import CORS
import requests
import socket

PROXY = "127.0.0.1:9050"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

app = Flask(__name__)
CORS(app)


def get_proxy():
    return {"http": f"socks5h://{PROXY}", "https": f"socks5h://{PROXY}"} if PROXY else None


def request_new_tor_ip():
    with socket.create_connection(("127.0.0.1", 9051)) as s:
        s.sendall(b'AUTHENTICATE ""\r\n')
        response = s.recv(1024).decode()
        if "250" not in response:
            raise Exception("Tor authentication failed")
        s.sendall(b'SIGNAL NEWNYM\r\n')
        response = s.recv(1024).decode()
        if "250" not in response:
            raise Exception("Failed to request new identity")


def get_tor_ip():
    try:
        proxy = get_proxy()
        response = requests.get("https://check.torproject.org/api/ip", proxies=proxy, timeout=10)
        return response.json().get("IP", "Unknown IP")
    except requests.RequestException as e:
        return f"Error: {e}"


@app.route('/get-tor-ip', methods=['GET'])
def fetch_tor_ip():
    return get_tor_ip()


@app.route('/fetch-url', methods=['GET'])
def fetch_url():
    redirect_link = request.args.get('link')
    if not redirect_link:
        return "No link provided", 400

    headers = HEADERS.copy()
    if 'vidmoly' in redirect_link:
        headers['Referer'] = 'https://vidmoly.to'

    try:
        response = requests.head(redirect_link, headers=headers, allow_redirects=True, timeout=10, proxies=get_proxy())
        return response.url
    except requests.RequestException:
        return "None"


@app.route('/fetch-html', methods=['GET'])
def fetch_html():
    redirect_link = request.args.get('link')
    if not redirect_link:
        return "No link provided", 400

    headers = HEADERS.copy()
    if 'vidmoly' in redirect_link:
        headers['Referer'] = 'https://vidmoly.to'

    def fetch():
        return requests.get(redirect_link, headers=headers, allow_redirects=True, timeout=10, proxies=get_proxy())

    try:
        response = fetch()
        if 'Just a moment...' in response.text:
            raise ValueError("Captcha")

        if '500 Internal Server Error' in response.text:
            raise ValueError("500 Internal Server Error")
        return response.text
    except ValueError:
        request_new_tor_ip()
        response = fetch()
        return response.text
    except requests.RequestException as e:
        return str(e), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
