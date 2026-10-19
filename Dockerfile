FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY prober/ prober/

# don't run as root inside the container
RUN useradd --create-home sitewatch
USER sitewatch

EXPOSE 8000
CMD ["python", "-u", "-m", "prober", "--metrics-port", "8000"]
