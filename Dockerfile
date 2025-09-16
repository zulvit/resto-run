FROM python:3.12-slim

WORKDIR /app

# Системные зависимости, необходимые для сборки пакетов
RUN apt-get update && apt-get install -y gcc libffi-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/

# Устанавливаем pip и зависимости
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . /app

CMD ["python", "main.py"]