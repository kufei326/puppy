FROM python:3.12.4-alpine

ENV TZ=Asia/Shanghai

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 4532

CMD ["python", "index.py"]