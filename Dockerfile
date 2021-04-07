FROM python:3.8.3-alpine3.12

ENV APP_HOME=/data
VOLUME [ "/data" ]
ENV PORT=3000
ENV LOG_LEVEL=INFO
ENV FLASK_ENV=production
ENV WAITRESS_THREADS=64

WORKDIR /app
COPY main.py .
COPY requirements.txt .

RUN pip install -r requirements.txt

CMD ["python", "main.py"]
