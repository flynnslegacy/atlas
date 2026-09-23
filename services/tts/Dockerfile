# --- Ce que `docker run` doit fournir, en plus de cette image -------------
#
# Cette image n'embarque ni pilote ni runtime GPU : sans ce que `docker run`
# lui donne ci-dessous, Qwen3 ne trouve aucun GPU et échoue à charger.
#
#   docker run --runtime=nvidia -e NVIDIA_VISIBLE_DEVICES=all \   # ou --gpus all
#     -v <cache-huggingface-hote>:/root/.cache/huggingface \
#     -v <dossier-modeles-hote>:/modeles \
#     -p 9011:9011 atlas-tts
#
# - Le runtime NVIDIA : --runtime=nvidia avec NVIDIA_VISIBLE_DEVICES, ou
#   --gpus all. Sans lui, pas de GPU dans le conteneur.
# - Un volume persistant sur /root/.cache/huggingface : sinon chaque
#   recréation du conteneur retélécharge le modèle Qwen3, et les premières
#   requêtes qui suivent peuvent dépasser le délai de 60 s du Core.
# - Le montage de /modeles, pour les voix de repli Piper (MoteurPiper).

# La base qui a tourné sur le GPU pendant le spike S1 : un Python 3.12 officiel, sans
# image CUDA. torch apporte ses propres bibliothèques CUDA (paquets nvidia-*) ; une
# base CUDA en ajouterait d'autres, d'une autre version, jamais éprouvées avec elles.
FROM python:3.12-slim

# build-essential : Triton, tiré par PyTorch, compile un petit module GPU au premier
# usage et il lui faut un compilateur C (le spike S1 a échoué exactement là).
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
# Les dépendances avant le code : modifier serveur.py ne réinstalle pas torch.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY serveur.py .
# La voix d'Atlas voyage avec l'image : la paire audio + texte exact, indissociable.
COPY voix/ /voix/

EXPOSE 9011
CMD ["python", "-m", "uvicorn", "serveur:app", "--host", "0.0.0.0", "--port", "9011"]
