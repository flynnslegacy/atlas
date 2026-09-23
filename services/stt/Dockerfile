FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

# Ubuntu 22.04 n'a aucun paquet python3.12, et son pip vise Python 3.10.
# On garde la base CUDA (elle porte cuDNN) et uv installe un Python 3.12
# autonome, indépendant de la distribution, dans un environnement virtuel.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates && rm -rf /var/lib/apt/lists/*

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

EXPOSE 9010
CMD ["/opt/venv/bin/python", "-m", "uvicorn", "serveur:app", "--host", "0.0.0.0", "--port", "9010"]
