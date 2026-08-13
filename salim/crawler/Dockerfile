FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py ./
COPY concrete_crawlers ./concrete_crawlers

CMD ["python", "scheduler.py"]
