FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

# Ubuntu 22.04 n'a aucun paquet python3.12, et son pip vise Python 3.10.
# On garde la base CUDA (elle porte cuDNN) et uv installe un Python 3.12
# autonome, indépendant de la distribution, dans un environnement virtuel.
# build-essential : Triton, tiré par PyTorch, compile un petit module GPU au premier
# usage et il lui faut un compilateur C (le spike S1 a échoué exactement là).
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates build-essential && rm -rf /var/lib/apt/lists/*

ENV UV_INSTALL_DIR=/usr/local/bin \
    UV_NO_MODIFY_PATH=1 \
    UV_PYTHON_INSTALL_DIR=/opt/python \
    UV_PYTHON_PREFERENCE=only-managed \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && uv python install 3.12 \
    && uv venv --python 3.12 /opt/venv

WORKDIR /app
COPY requirements.txt .
RUN uv pip install --no-cache --python /opt/venv/bin/python -r requirements.txt
COPY serveur.py .
# La voix d'Atlas voyage avec l'image : la paire audio + texte exact, indissociable.
COPY voix/ /voix/

EXPOSE 9011
CMD ["/opt/venv/bin/python", "-m", "uvicorn", "serveur:app", "--host", "0.0.0.0", "--port", "9011"]
