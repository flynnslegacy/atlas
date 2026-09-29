# Charge .env s'il existe (sans erreur s'il manque) et le passe à chaque recette.
-include .env
export

# Les variables que le .env a données à ce make : `run-core` ne les passe pas au make neuf qui
# relance le Core, pour qu'une variable retirée du .env ne survive pas à un redémarrage.
CLES_DU_ENV := $(shell sed -n 's/^[[:space:]]*\(export[[:space:]]\{1,\}\)\{0,1\}\([A-Za-z_][A-Za-z0-9_]*\)[[:space:]]*[:?+]\{0,2\}=.*/\2/p' .env 2>/dev/null)
COMMANDE_CORE ?= uv run uvicorn atlas_core.hub:app --host 0.0.0.0 --port 8080

.PHONY: install test test-web test-swift lint format bench run-core core run-audio run-poste

# Les dépendances des connecteurs (connecteurs/ et ~/.atlas/connecteurs/) s'installent après.
install:
	uv sync --extra core --extra audio --extra dev --extra poste
	uv run python -m atlas_core.registre installer

test:
	uv run pytest -v
	node --test "tests/web/*.test.mjs"

test-web:
	node --test "tests/web/*.test.mjs"

test-swift:
	swiftc -sanitize=thread src/atlas_aec/Sources/atlas-aec/Tampons.swift tests/aec/tampons/main.swift -o "$$TMPDIR/harnais" && "$$TMPDIR/harnais"

lint:
	uv run ruff check . && uv run ruff format --check .

format:
	uv run ruff format .

bench:
	uv run python bench/bench.py

# Le Core, relancé par un make neuf, qui relit le .env, chaque fois qu'il le demande en
# laissant la marque donnees/redemarrer (le bouton « Redémarrer » de la page) ; sinon, la
# boucle s'arrête avec lui (Ctrl-C, ou le Core qui tombe : launchd le relance sur le néo).
# Le SIGTERM de launchd (kickstart -k, bootout) passe au Core, que la boucle attend : il
# s'arrête proprement, sans orphelin. Un Ctrl-C, le Core le reçoit déjà du Terminal : la
# boucle l'attend sans rien lui renvoyer (un second signal lui ferait sauter son arrêt propre).
run-core:
	@trap 'kill -TERM $$enfant 2>/dev/null; wait $$enfant; exit 143' TERM; \
	trap 'wait $$enfant; exit 130' INT; \
	while :; do \
	  rm -f donnees/redemarrer; \
	  env $(addprefix -u ,$(CLES_DU_ENV)) $(MAKE) --no-print-directory core & enfant=$$!; \
	  wait $$enfant; code=$$?; \
	  [ -f donnees/redemarrer ] || exit $$code; \
	done

core:
	$(COMMANDE_CORE)

run-audio:
	uv run python -m atlas_audio.client

# Le poste, sur le Mac de David : ouvre, regarde et pilote pour Atlas.
run-poste:
	uv run python -m atlas_poste.client
