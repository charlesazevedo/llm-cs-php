#!/usr/bin/env bash
# Etapa 0, antes de qualquer chamada paga: confere o acesso ao OpenRouter sem
# gastar nada e sem fazer nenhuma chamada de inferência.
#
#   1. a chave em experimento/.env vale? qual o limite de gasto e o uso dela?
#   2. modelos.yaml bate com o catálogo público do OpenRouter (snapshot,
#      endpoint fixado, parâmetros aceitos, preço)?
#   3. as 720 chamadas do experimento montam sem erro (nenhuma é enviada)?
#
# Uso, de qualquer pasta:
#   experimento/conferir-acesso.sh
#
# Sai com código 1 se algum dos três passos apontar problema.

set -uo pipefail
cd "$(dirname "$0")/.."

h() { uv run --no-project --with-requirements experimento/requirements.txt python experimento/harness.py "$@"; }

status=0
echo "=== 1/3 Chave do OpenRouter"
h conta || status=1
echo
echo "=== 2/3 Modelos no catálogo público"
h modelos || status=1
echo
echo "=== 3/3 Chamadas montadas, sem envio"
h testar || status=1
echo
if [ "$status" -eq 0 ]; then
    echo "Tudo certo. Nenhuma chamada de inferência foi feita; o próximo passo é experimento/teste-linha-de-base.sh."
else
    echo "Há problema(s) acima (linhas PROBLEMA). Nenhuma chamada de inferência foi feita."
fi
exit "$status"
