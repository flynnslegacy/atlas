# SPIKE S1 — JETABLE. Compare Qwen3-TTS et Piper Tom à l'aveugle. Ne pas intégrer.
# Pas de flash-attn : sa compilation prendrait trop longtemps pour un simple test.
FROM python:3.12-slim
RUN pip install --no-cache-dir torch qwen-tts soundfile numpy soxr
# Triton (tiré par PyTorch) compile un petit module GPU au premier usage : il lui faut
# un compilateur C. Couche placée APRÈS pip pour réutiliser le cache de PyTorch.
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /spike
COPY spike.py .
CMD ["python", "spike.py"]
