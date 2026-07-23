FROM python:3.12-slim

WORKDIR /app

COPY services/loader/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared ./shared
COPY services/loader/main.py ./

CMD ["python", "main.py"]
