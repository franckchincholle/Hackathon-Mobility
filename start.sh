#!/usr/bin/env bash
# Lance le site d'optimisation des stations Citiz (dossier optimisation/) en une commande.
#
#   ./start.sh               installe si besoin, copie les tables de Fabric, lance le site
#   ./start.sh --hors-ligne  sans Azure ni copie : lance le site sur la copie déjà présente
#   ./start.sh --direct      lance le site en lecture directe de Fabric (plus lent)
#   ./start.sh --tests       lance les tests du site
#   ./start.sh --aide        affiche cette aide
#
# Par défaut, le site lit la copie locale des tables (OPTIM_SOURCE=local) : l'affichage est
# immédiat et rien ne dépend du réseau pendant la démo. Relancé, le script ne réinstalle rien
# tant que les fichiers de dépendances n'ont pas changé.

set -euo pipefail

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPTIM="$RACINE/optimisation"
VENV="$OPTIM/.venv"
TENANT="901cb4ca-b862-4029-9306-e5cd0f6d9f86"   # tenant Epitech, où vit l'espace Fabric
PORT_DEPART=8501

etape()  { printf '\n[%s] %s\n' "$1" "$2"; }
avertir() { printf 'Attention : %s\n' "$*" >&2; }
erreur() { printf 'Erreur : %s\n' "$*" >&2; exit 1; }

aide() {
  sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

# ---------- Python 3.12 ou plus ----------
# Les versions figées de numpy, scipy et pyproj demandent Python 3.12.
python_valable() {
  "$1" -c 'import sys; sys.exit(sys.version_info < (3, 12))' 2>/dev/null
}

trouver_python() {
  local candidat
  for candidat in python3 python3.14 python3.13 python3.12; do
    if command -v "$candidat" >/dev/null 2>&1 && python_valable "$candidat"; then
      PYTHON="$(command -v "$candidat")"
      return 0
    fi
  done
  PYTHON=""
  return 1
}

# ---------- Environnement Python dans optimisation/.venv ----------
preparer_venv() {
  etape python "Environnement Python (optimisation/.venv)"
  if [ -x "$VENV/bin/python" ]; then
    python_valable "$VENV/bin/python" \
      || erreur "optimisation/.venv utilise un Python trop ancien : le supprimer, puis relancer."
    echo "Déjà prêt : $("$VENV/bin/python" --version)."
    return 0
  fi
  if trouver_python; then
    echo "Création avec $("$PYTHON" --version)."
  elif command -v uv >/dev/null 2>&1; then
    echo "Pas de Python 3.12 sur ce poste : uv va en installer un."
    PYTHON="3.12"
  else
    erreur "Python 3.12 ou plus est requis (sous Ubuntu : sudo apt install python3.12 python3.12-venv)."
  fi
  if command -v uv >/dev/null 2>&1; then
    uv venv --quiet --python "$PYTHON" "$VENV"
  else
    "$PYTHON" -m venv "$VENV" \
      || erreur "création impossible (sous Ubuntu : sudo apt install python3-venv), puis relancer."
  fi
}

# Empreinte d'un contenu : sha256sum sous Linux, shasum sous macOS.
empreinte_de() {
  if command -v sha256sum >/dev/null 2>&1; then sha256sum; else shasum -a 256; fi | cut -d' ' -f1
}

# Installe un fichier de dépendances, seulement s'il a changé depuis la dernière installation.
installer() {
  local fichier="$OPTIM/$1" marque empreinte
  marque="$VENV/.installe-$1"
  empreinte="$(cat "$OPTIM/requirements.txt" "$fichier" | empreinte_de)"
  if [ -f "$marque" ] && [ "$(cat "$marque")" = "$empreinte" ]; then
    echo "Dépendances à jour ($1)."
    return 0
  fi
  echo "Installation des dépendances ($1)..."
  if command -v uv >/dev/null 2>&1; then
    uv pip install --quiet --python "$VENV/bin/python" -r "$fichier"
  else
    "$VENV/bin/python" -m pip --version >/dev/null 2>&1 || "$VENV/bin/python" -m ensurepip --upgrade
    "$VENV/bin/python" -m pip install --quiet --disable-pip-version-check -r "$fichier"
  fi
  echo "$empreinte" > "$marque"
}

# ---------- Session Azure sur le tenant Epitech ----------
session_valable() {
  [ "$(az account show --query tenantId -o tsv 2>/dev/null)" = "$TENANT" ] \
    && az account get-access-token --resource https://storage.azure.com -o none >/dev/null 2>&1
}

connecter_azure() {
  etape azure "Session Azure (tenant Epitech)"
  command -v az >/dev/null 2>&1 || { avertir "Azure CLI (az) est introuvable."; return 1; }
  if session_valable; then
    echo "Connecté : $(az account show --query user.name -o tsv)."
    return 0
  fi
  # Déjà connu d'az, mais pas en compte par défaut : on le reprend sans nouvelle connexion
  if az account set --subscription "$TENANT" >/dev/null 2>&1 && session_valable; then
    echo "Connecté : $(az account show --query user.name -o tsv)."
    return 0
  fi
  echo "Connexion nécessaire : une page de connexion Microsoft va s'ouvrir."
  if grep -qi microsoft /proc/version 2>/dev/null && command -v powershell.exe >/dev/null 2>&1; then
    # Sous WSL, le navigateur par défaut de Python passe inaperçu : on ouvre celui de Windows
    export BROWSER="powershell.exe -NoProfile -Command \"Start-Process '%s'\""
  fi
  # Si le navigateur ne s'ouvre pas, repli sur un code à saisir sur microsoft.com/devicelogin
  az login --tenant "$TENANT" --allow-no-subscriptions -o none \
    || az login --tenant "$TENANT" --allow-no-subscriptions --use-device-code -o none \
    || { avertir "connexion à Azure impossible."; return 1; }
  session_valable || { avertir "la session Azure n'est pas sur le tenant Epitech."; return 1; }
}

# ---------- Données ----------
copie_presente() {
  (cd "$OPTIM" && "$VENV/bin/python" scripts/telecharger_lakehouse.py --verifier)
}

copier_donnees() {
  etape données "Copie des tables Fabric dans optimisation/data/reel/ (environ 30 s)"
  (cd "$OPTIM" && "$VENV/bin/python" scripts/telecharger_lakehouse.py)
}

# ---------- Site ----------
port_libre() {
  local port="$PORT_DEPART"
  until "$VENV/bin/python" -c '
import socket, sys
s = socket.socket()
try:
    s.bind(("", int(sys.argv[1])))
except OSError:
    sys.exit(1)
finally:
    s.close()' "$port"; do
    port=$((port + 1))
  done
  echo "$port"
}

lancer_site() {
  local source="$1" port
  port="$(port_libre)"
  etape site "Lancement du site (lecture : $source)"
  echo "Adresse : http://localhost:$port    (Ctrl+C pour arrêter)"
  # Lancé depuis optimisation/, pour que .streamlit/config.toml applique le thème Citiz
  cd "$OPTIM"
  OPTIM_SOURCE="$source" exec "$VENV/bin/python" -m streamlit run app/streamlit_app.py \
    --server.headless true --server.port "$port"
}

# ---------- Programme ----------
MODE="defaut"
for argument in "$@"; do
  case "$argument" in
    --hors-ligne) nouveau="hors-ligne" ;;
    --direct)     nouveau="direct" ;;
    --tests)      nouveau="tests" ;;
    --aide|-h|--help) aide; exit 0 ;;
    *) aide; erreur "option inconnue : $argument" ;;
  esac
  [ "$MODE" = "defaut" ] || [ "$MODE" = "$nouveau" ] || erreur "une seule option à la fois."
  MODE="$nouveau"
done

preparer_venv

case "$MODE" in
  tests)
    installer requirements-dev.txt
    etape tests "Tests du site"
    cd "$OPTIM"
    exec "$VENV/bin/python" -m pytest tests -q
    ;;
  hors-ligne)
    installer requirements.txt
    etape données "Copie locale (pas de connexion à Fabric)"
    copie_presente || erreur "pas de copie utilisable : lancer ./start.sh une fois avec une connexion à Fabric."
    lancer_site local
    ;;
  direct)
    installer requirements.txt
    connecter_azure || erreur "sans session Azure, la lecture directe est impossible : essayer ./start.sh --hors-ligne."
    lancer_site fabric
    ;;
  defaut)
    installer requirements.txt
    if connecter_azure && copier_donnees; then
      :
    elif copie_presente; then
      avertir "copie depuis Fabric impossible : le site part de la copie déjà présente."
    else
      erreur "copie depuis Fabric impossible et aucune copie locale : vérifier la connexion, puis relancer."
    fi
    lancer_site local
    ;;
esac
