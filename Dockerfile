FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY 403.html /app/403.html
COPY proxy.py /app/proxy.py

EXPOSE 8080

# Mampok sets REVERSE_PORT, REDIRECT_HOST, REDIRECT_URL and PROJECT_ID as
# env vars on this container; see README.md.
CMD ["sh", "-c", "mitmdump --mode reverse:http://localhost:${REVERSE_PORT} -s /app/proxy.py --listen-port 8080 --set confdir=/app/.mitmproxy"]
