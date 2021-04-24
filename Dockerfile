FROM python:3.8.3-alpine3.12

ENV PORT=3000
ENV LOG_LEVEL=INFO
ENV ENVIRONMENT=production

WORKDIR /app
COPY requirements.txt .

RUN apk add --no-cache --update --virtual .temp-deps gcc musl-dev libffi-dev &&\
    pip install -r requirements.txt &&\
    apk del .temp-deps

COPY main.py .
COPY multi_reaction_add .

CMD ["python", "main.py"]
