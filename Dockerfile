FROM python:3.13-slim

 

WORKDIR /app

 

COPY . /app/

# Instalar dependencias básicas correctamente en slim

RUN apt-get update && apt-get install -y --no-install-recommends \

    apt-utils \

    build-essential \

    curl \

    git \

    && rm -rf /var/lib/apt/lists/*

 

# Clonar el repo

# RUN https://github.com/MiguelPerezF/aplicativo_turnos.git .

 

# Instalar dependencias de Python

RUN pip install --no-cache-dir -r requirements.txt

 

EXPOSE 8501

 

HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

 

ENTRYPOINT ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]