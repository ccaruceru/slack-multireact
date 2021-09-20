### STEP 1: build dependencies

FROM python:3.8-alpine3.14 as builder

RUN apk add gcc==10.3.1_git20210424-r2 musl-dev==1.2.2-r3

COPY requirements.txt .

RUN pip install -r requirements.txt


### STEP 2: assemble runtime

FROM python:3.8-alpine3.14

ENV GUNICORN_PORT=3000
ENV GUNICORN_WORKERS=1
ENV GUNICORN_THREADS=8
ENV GOOGLE_APPLICATION_CREDENTIALS=/credentials.json

EXPOSE ${GUNICORN_PORT}

LABEL maintainer="ccaruceru"

# copy built packages
COPY --from=builder /usr/local/lib/python3.8 /usr/local/lib/python3.8

WORKDIR /app

COPY multi_reaction_add multi_reaction_add
COPY resources resources

ENTRYPOINT [ "/bin/sh", "-c" ]

CMD ["python -m gunicorn --bind :${GUNICORN_PORT} --workers ${GUNICORN_WORKERS} \
     --threads ${GUNICORN_THREADS} --timeout 0 --worker-class aiohttp.GunicornWebWorker \
     multi_reaction_add.handlers:entrypoint"]
