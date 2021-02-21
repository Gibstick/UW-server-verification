FROM python:3.8-slim-buster

RUN useradd -ms /bin/sh andrew && mkdir /db && chown andrew /db

USER andrew

WORKDIR /app

COPY requirements.txt ./

RUN pip install --no-cache-dir --no-warn-script-location -r requirements.txt

COPY static static
COPY templates templates
COPY *.py ./

# No entrypoint, because we use one image for both server and bot.
