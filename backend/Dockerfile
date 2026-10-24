# Backend NexCore: Flask + flask-sock servido pelo gunicorn.
#
# Dois cuidados que vêm do próprio app:
#  - worker de THREAD (gthread): o WebSocket deixa a conexão aberta, o `sync` trava;
#  - UM processo (-w 1): a fila, as travas e a auditoria vivem em memória, e o broadcast
#    do /v1/ws só alcança quem está no mesmo processo. Dois workers = duas filas.
# O pandas entra na imagem de produção porque /painel/impacto roda o verificador
# oficial (dataset/verificar_fila_priorizada.py) por subprocess.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt ./requirements.txt
COPY dataset/requirements.txt ./dataset/requirements.txt
RUN pip install -r requirements.txt -r dataset/requirements.txt

COPY . .

RUN useradd --system --uid 10001 --no-create-home nexcore
USER nexcore

ENV APP_AMBIENTE=producao \
    FLASK_DEBUG=0

EXPOSE 5000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/api/health', timeout=4)"

CMD ["gunicorn", "-k", "gthread", "-w", "1", "--threads", "50", \
     "-b", "0.0.0.0:5000", "--access-logfile", "-", "wsgi:app"]
