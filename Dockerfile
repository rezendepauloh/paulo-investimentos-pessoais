FROM python:3.12-slim-bookworm

# Variáveis de ambiente para execução limpa do Python com verificação estrita de TLS
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    TZ=America/Campo_Grande \
    PIP_DEFAULT_TIMEOUT=120 \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt

WORKDIR /app

# Instala dependências do sistema e certificados confiáveis
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    build-essential \
    tzdata \
    tesseract-ocr \
    tesseract-ocr-por \
    && update-ca-certificates \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Se existirem certificados corporativos/CA adicionais em certs/, instala na store oficial do SO
COPY certs* /tmp/certs/
RUN if [ -d /tmp/certs ] && [ -n "$(ls -A /tmp/certs 2>/dev/null)" ]; then \
        cp /tmp/certs/*.crt /usr/local/share/ca-certificates/ 2>/dev/null || true; \
        update-ca-certificates; \
    fi && rm -rf /tmp/certs

# Copia e instala dependências do Python com validação estrita de certificados HTTPS
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Cria usuário não-privilegiado para execução segura do contêiner (Princípio do Menor Privilégio)
RUN groupadd --gid 10001 appgroup \
    && useradd --uid 10001 --gid 10001 --shell /usr/sbin/nologin --create-home appuser

# Copia o restante da aplicação com permissões restritas (segredos excluídos via .dockerignore)
COPY --chown=appuser:appgroup . .
RUN mkdir -p /app/data /app/logs \
    && chown -R appuser:appgroup /app \
    && chmod 750 /app/data /app/logs

USER appuser

ARG STREAMLIT_PORT=8502
ENV STREAMLIT_PORT=${STREAMLIT_PORT}

# Expõe a porta padrão do Streamlit
EXPOSE ${STREAMLIT_PORT}

# Variáveis padrão de execução do Streamlit (bind interno no namespace do contêiner; host restringe em 127.0.0.1)
ENV STREAMLIT_SERVER_PORT=${STREAMLIT_PORT} \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true

# Healthcheck para monitorar o status do Streamlit
HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=3 \
    CMD curl --fail http://127.0.0.1:${STREAMLIT_PORT}/_stcore/health || exit 1

# Comando padrão de inicialização
CMD ["streamlit", "run", "dashboard.py"]





