#!/usr/bin/env bash
# Deploy da Marina pra VPS (desde 25/09 ela roda lá; o PC é só onde se edita e testa).
#
#   bash scripts/deploy_vps.sh            # manda o último commit, checagem rápida, reinicia se ela estiver livre
#   bash scripts/deploy_vps.sh --full     # + suíte inteira lá (automático quando o requirements.txt muda)
#   bash scripts/deploy_vps.sh --now      # reinicia mesmo se o Patrick falou com ela há pouco
#
# Só vai o que está COMMITADO. A biblioteca (data/feedback) nunca vai: ela é
# escrita lá pelo /bom, /ruim e /registro. O banco e os logs também ficam lá.
set -euo pipefail

HOST=root@82.29.60.214
DIR=/root/bots/marina
SSH=(ssh -i "$HOME/.ssh/marina_vps" -o BatchMode=yes "$HOST")
QUIET_MIN=5          # não reinicia se a última mensagem foi há menos que isso
QUICK_TESTS="tests.test_response_rhythm tests.test_bubbles_luna tests.test_chat_naturalness tests.test_abreviacoes tests.test_patrick_doente tests.test_intimacy_c1 tests.test_photo_director"
ENVS="TZ=America/Sao_Paulo PYTHONUTF8=1"

full=0; now=0
for arg in "$@"; do
  case "$arg" in
    --full) full=1 ;;
    --now) now=1 ;;
    *) echo "opção desconhecida: $arg"; exit 1 ;;
  esac
done

cd "$(git rev-parse --show-toplevel)"
rev=$(git rev-parse --short HEAD)
if ! git diff --quiet HEAD -- . ':(exclude)data/feedback'; then
  echo "[aviso] há mudanças não commitadas fora da biblioteca: elas NÃO vão."
fi

prev=$("${SSH[@]}" "cat $DIR/.deployed 2>/dev/null || true")
echo "== deploy $prev -> $rev"

# 1) código commitado, sem a biblioteca
git archive --format=tar HEAD -- . ':(exclude)data/feedback' | "${SSH[@]}" "cd $DIR && tar -xf -"

# arquivos apagados desde o último deploy também saem de lá
if [ -n "$prev" ] && git cat-file -e "$prev^{commit}" 2>/dev/null; then
  gone=$(git diff --name-only --diff-filter=D "$prev" HEAD -- . ':(exclude)data/feedback' || true)
  if [ -n "$gone" ]; then
    echo "$gone" | "${SSH[@]}" "cd $DIR && xargs -r rm -f --"
    echo "   removidos: $(echo "$gone" | wc -l) arquivo(s)"
  fi
  if ! git diff --quiet "$prev" HEAD -- requirements.txt; then
    echo "   requirements.txt mudou: instalando e rodando a suíte inteira"
    full=1
    "${SSH[@]}" "cd $DIR && venv/bin/pip install -q -r requirements.txt"
  fi
fi

# 2) checagem lá: o que difere é o ambiente, não o código (que já passou aqui)
echo "== checagem rápida"
quick=$("${SSH[@]}" "cd $DIR && $ENVS venv/bin/python -c 'import bot' >/dev/null 2>&1 && echo '   bot carrega' || echo '   FALHA: bot não carrega'; $ENVS venv/bin/python scripts/soak_preflight.py 2>&1 | tail -1; $ENVS venv/bin/python -m unittest $QUICK_TESTS 2>&1 | tail -1")
echo "$quick"
if echo "$quick" | grep -qE 'FALHA|ERRO|FAILED' || [ "$(echo "$quick" | tail -1 | cut -c1-2)" != OK ]; then
  echo "[erro] checagem lá falhou: código já foi, mas NÃO reiniciei (a Marina segue na versão anterior em memória)"
  exit 2
fi
if [ "$full" = 1 ]; then
  echo "== suíte inteira (~5 min)"
  result=$("${SSH[@]}" "cd $DIR && $ENVS timeout 1200 venv/bin/python -m unittest discover -s tests > /tmp/marina_testes.log 2>&1; grep -E '^(FAIL|ERROR):' /tmp/marina_testes.log | head -20; tail -1 /tmp/marina_testes.log")
  echo "$result"
  case "$(echo "$result" | tail -1)" in
    OK*) ;;
    *) echo "[erro] suíte falhou lá: não reinicio"; exit 2 ;;
  esac
fi
"${SSH[@]}" "echo $rev > $DIR/.deployed"

# 3) reinicia só com ela livre (respostas pendentes sobrevivem ao restart; a conversa em andamento não)
mins=$("${SSH[@]}" "cd $DIR && $ENVS venv/bin/python -c \"
import sqlite3; from datetime import datetime
c = sqlite3.connect('file:marin_memory.db?mode=ro', uri=True)
t = c.execute('select max(timestamp) from conversas').fetchone()[0]
print(int((datetime.now() - datetime.fromisoformat(t)).total_seconds() // 60) if t else 9999)
\"" | tr -d '\r')
if [ "$now" = 0 ] && [ "$mins" -lt "$QUIET_MIN" ]; then
  echo "== NÃO reiniciei: a última mensagem foi há $mins min. Código já está lá; rode de novo com --now ou mais tarde."
  exit 3
fi
echo "== reiniciando (última mensagem há $mins min)"
"${SSH[@]}" "systemctl restart marina && sleep 12 && systemctl is-active marina && journalctl -u marina --since '-20s' --no-pager | grep -E 'startup recovery|Application started|ERROR|Traceback' | sed 's/^.*python\[[0-9]*\]: //' | tail -4"
