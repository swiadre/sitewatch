FROM python:3.12-slim

ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION} DATA_DIR=/data PORT=8080

WORKDIR /app
COPY app.py .
RUN mkdir /data

EXPOSE 8080
CMD ["python", "-u", "app.py"]
