FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12 python3-pip && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt
COPY serveur.py .

EXPOSE 9011
CMD ["python3", "-m", "uvicorn", "serveur:app", "--host", "0.0.0.0", "--port", "9011"]
