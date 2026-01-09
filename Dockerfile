FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ .

EXPOSE 8000

# 使用 Gunicorn 启动
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8000", "app:app"]
