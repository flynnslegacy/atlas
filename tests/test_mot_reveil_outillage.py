import re
import subprocess
from pathlib import Path

DOSSIER = Path("scripts/mot_reveil")


def test_les_scripts_shell_sont_syntaxiquement_valides():
    for script in ("telecharger_donnees.sh", "entrainer.sh"):
        assert subprocess.run(["bash", "-n", str(DOSSIER / script)]).returncode == 0


def test_le_dockerfile_fige_la_pile_verifiee():
    texte = (DOSSIER / "Dockerfile").read_text()
    for attendu in (
        "FROM python:3.10-slim",
        "torch==1.13.1+cu117",
        "checkout 368c037",
        "piper-tts==1.3.0",
        "tensorflow-cpu==2.8.1",
        '"pyarrow<15"',
        '"fsspec<2024.1.0"',
        '"numpy<2"',
        "/opt/psg/generate_samples.py",
    ):
        assert attendu in texte


def test_le_dockerfile_verifie_numpy_1_au_build():
    texte = (DOSSIER / "Dockerfile").read_text()
    assert "torch.from_numpy(numpy.zeros(1))" in texte
    assert "numpy.__version__.startswith(" in texte
    assert "1.'" in texte or '1."' in texte


def test_la_procedure_ne_publie_aucune_adresse():
    for fichier in (DOSSIER / "LISEZMOI.md", DOSSIER / "Dockerfile"):
        assert not re.search(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", fichier.read_text())


def test_l_ancienne_procedure_a_disparu():
    assert not Path("scripts/entrainer_mot_reveil.md").exists()


def test_le_telechargement_reprend_via_un_fichier_partiel():
    texte = (DOSSIER / "telecharger_donnees.sh").read_text()
    assert ".partiel" in texte
    assert re.search(r"curl[^\n]*-C -[^\n]*\.partiel", texte)
    assert re.search(r"mv\s+\S*\.partiel\S*\s+\S*\"\$2\"", texte)


def test_l_enrichissement_tourne_sur_le_processeur_et_l_entrainement_sur_le_gpu():
    # Le cuFFT de CUDA 11.7 (torch 1.13.1+cu117) plante sur les cartes Ada (RTX 40xx) dans le
    # décalage de hauteur de l'enrichissement : constaté à l'essai à blanc, le 24 septembre 2026.
    lignes = [
        ligne.strip()
        for ligne in (DOSSIER / "entrainer.sh").read_text().splitlines()
        if "openwakeword/train.py" in ligne
    ]
    enrichir = [ligne for ligne in lignes if "--augment_clips" in ligne]
    entrainer = [ligne for ligne in lignes if "--train_model" in ligne]
    assert len(enrichir) == 1 and enrichir[0].startswith("CUDA_VISIBLE_DEVICES= python ")
    assert len(entrainer) == 1 and "CUDA_VISIBLE_DEVICES" not in entrainer[0]


def test_le_dockerfile_corrige_les_options_booleennes_de_train_py():
    """train.py déclare default="False" (une chaîne, donc vraie) : --convert_to_tflite se
    déclenchait toujours, et TensorFlow plantait (conflit protobuf) après l'export ONNX."""
    texte = (DOSSIER / "Dockerfile").read_text()
    expression = re.search(r"sed -i '([^']+)' /opt/openWakeWord/openwakeword/train\.py", texte)
    assert expression, "le correctif de train.py a disparu du Dockerfile"
    extrait_amont = (
        "    parser.add_argument(\n"
        '        "--convert_to_tflite",\n'
        '        help="Convert the trained ONNX model to TFLite format",\n'
        '        action="store_true",\n'
        '        default="False",\n'
        "        required=False\n"
        "    )\n"
    )
    corrige = subprocess.run(
        ["sed", expression.group(1)], input=extrait_amont, text=True, capture_output=True
    ).stdout
    assert 'default="False"' not in corrige and "default=False," in corrige
    # La construction échoue si le motif subsiste (commit épinglé changé, correctif sans effet).
    assert "! grep -q 'default=\"False\"' /opt/openWakeWord/openwakeword/train.py" in texte
