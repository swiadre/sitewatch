# build from the repo root: docker build -f remediation/Dockerfile .
FROM python:3.12-slim

WORKDIR /app
COPY remediation/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY remediation/ remediation/
# source of the demo app, the remediator builds its images on deploy
COPY demo/ /demo/

# runs as root because it needs the docker socket (only on my own machine, see README)
EXPOSE 9000
CMD ["python", "-u", "-m", "remediation"]
