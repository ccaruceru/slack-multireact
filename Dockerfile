### STEP 1: build dependencies

FROM python:3.11-alpine3.17 as builder

RUN apk add gcc==12.2.1_git20220924-r4 musl-dev==1.2.3-r5

COPY requirements.txt .

RUN pip install -r requirements.txt


### STEP 2: assemble runtime

FROM python:3.11-alpine3.17

ENV UVICORN_PORT=3000
ENV UVICORN_WORKERS=1
ENV UVICORN_LOG_LEVEL=info
ENV UVICORN_HOST=0.0.0.0
ENV GOOGLE_APPLICATION_CREDENTIALS=/credentials.json

EXPOSE ${UVICORN_PORT}

LABEL maintainer="ccaruceru"

# copy built packages
COPY --from=builder /usr/local/lib/python3.11 /usr/local/lib/python3.11

WORKDIR /app

COPY multi_reaction_add multi_reaction_add
COPY resources resources

CMD python -m uvicorn multi_reaction_add.handlers:api --no-access-log --no-use-colors
