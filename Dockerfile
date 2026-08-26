# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm

# Evita criação de arquivos .pyc e força stdout/stderr sem buffer e fuso horário
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=America/Campo_Grande

WORKDIR /app

# Instala dependências do sistema e aplica patches de segurança
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*



# Copia e instala dependências do Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia o restante da aplicação
COPY . .

ENV STREAMLIT_PORT=8501

# Expõe a porta padrão do Streamlit
EXPOSE 8501 8502

# Healthcheck para monitorar o status do Streamlit
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:${STREAMLIT_PORT}/_stcore/health || exit 1

# Comando padrão de inicialização
CMD ["sh", "-c", "streamlit run dashboard.py --server.port=${STREAMLIT_PORT} --server.address=0.0.0.0"]


