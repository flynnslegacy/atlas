# SPIKE S1 — JETABLE. Compare Qwen3-TTS et Piper Tom à l'aveugle. Ne pas intégrer.
# Pas de flash-attn : sa compilation prendrait trop longtemps pour un simple test.
FROM python:3.12-slim
RUN pip install --no-cache-dir torch qwen-tts soundfile numpy soxr
WORKDIR /spike
COPY spike.py .
CMD ["python", "spike.py"]
