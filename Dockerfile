FROM python:3.8.3-alpine3.12

ENV PORT=3000
ENV LOG_LEVEL=INFO
# Allow statements and log messages to immediately appear in the Knative logs
ENV PYTHONUNBUFFERED=True
ENV CPUS=1

WORKDIR /app
COPY requirements.txt .

RUN apk add --no-cache --update --virtual .temp-deps gcc musl-dev libffi-dev &&\
    pip install -r requirements.txt &&\
    apk del .temp-deps

COPY main.py .
COPY multi_reaction_add multi_reaction_add

# Run the web service on container startup. Here we use the gunicorn
# webserver, with one worker process and 8 threads.
# For environments with multiple CPU cores, increase the number of workers
# to be equal to the cores available.
# Timeout is set to 0 to disable the timeouts of the workers to allow Cloud Run to handle instance scaling.
CMD exec gunicorn --bind :$PORT --workers $CPUS --threads 8 --timeout 0 --worker-class aiohttp.GunicornWebWorker main:entrypoint
