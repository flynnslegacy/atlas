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
