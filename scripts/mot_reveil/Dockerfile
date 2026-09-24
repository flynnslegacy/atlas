# Environnement d'entraînement du mot de réveil « Hey Atlas » (Unraid, GPU).
# Pile figée qui marche d'après l'issue openWakeWord #317 : Python 3.10, torch 1.13.1+cu117.
#
# Construction, depuis la racine du dépôt cloné sur l'Unraid :
#   docker build -f scripts/mot_reveil/Dockerfile -t atlas-mot-reveil .
# Lancement : --runtime=nvidia -e NVIDIA_VISIBLE_DEVICES=all (ou --gpus all),
#   --shm-size=32g, -v <dossier-travail-unraid>:/travail
FROM python:3.10-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential git curl unzip ca-certificates libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# 1. openWakeWord figé au commit vérifié, avec sa pile d'entraînement.
# train.py y déclare ses options booléennes avec default="False" : une chaîne, donc vraie.
# --convert_to_tflite, testé par sa seule vérité, se déclenchait toujours, et TensorFlow 2.8.1
# plantait (conflit protobuf 3.9.2 / 3.20.3) juste après l'export ONNX, le seul format utile.
# La construction échoue si le motif subsiste.
RUN git clone https://github.com/dscripka/openWakeWord /opt/openWakeWord \
    && git -C /opt/openWakeWord checkout 368c037 \
    && sed -i 's/default="False",/default=False,/' /opt/openWakeWord/openwakeword/train.py \
    && ! grep -q 'default="False"' /opt/openWakeWord/openwakeword/train.py
RUN pip install --no-cache-dir torch==1.13.1+cu117 torchaudio==0.13.1+cu117 \
        --extra-index-url https://download.pytorch.org/whl/cu117 \
    && pip install --no-cache-dir -e "/opt/openWakeWord[full]" \
        "numpy<2" "tensorflow-cpu==2.8.1" "pyarrow<15" "fsspec<2024.1.0" soundfile soxr httpx \
    && python -c "import numpy, torch; torch.from_numpy(numpy.zeros(1)); assert numpy.__version__.startswith('1.')" \
    && python -c "import openwakeword.utils as u; u.download_models()"

# 2. train.py importe generate_samples même sans génération : un bouchon suffit.
RUN mkdir -p /opt/psg && printf '%s\n' \
        'def generate_samples(*args, **kwargs):' \
        '    raise RuntimeError("génération désactivée : extraits fournis par scripts/mot_reveil")' \
        > /opt/psg/generate_samples.py

# 3. Piper 1.3.0 dans son propre environnement, pour ne pas heurter la pile figée.
RUN python -m venv /opt/piper \
    && /opt/piper/bin/pip install --no-cache-dir piper-tts==1.3.0 soundfile soxr numpy httpx

WORKDIR /app
COPY scripts/ /app/scripts/
CMD ["bash"]
