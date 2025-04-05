FROM python:3.13-bookworm as builder

RUN pip install --no-cache --upgrade pip && \
    pip install --no-cache pyinstaller

WORKDIR /builder

COPY ./package/p115strmhelper/. .

RUN pip install --no-cache -r requirements.txt

RUN pyinstaller p115updatedb.spec

FROM scratch

COPY --from=builder --chmod=755 /builder/dist/p115updatedb /p115updatedb
