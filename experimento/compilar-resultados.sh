#!/usr/bin/env bash
# Compila as respostas gravadas num relatório fácil de ler, em Markdown:
#   - em resumo: quantas respostas, se a rota foi a configurada, se vieram
#     inteiras, o que os modelos apontaram, o custo e a projeção;
#   - o que pede atenção, com o que fazer em cada caso;
#   - tabelas da rota, das respostas, dos CS apontados por modelo (casados com o
#     catálogo pela lista de sinônimos), do custo e dos tokens;
#   - o detalhe de cada resposta, com a justificativa de cada CS.
#
# Só lê experimento/resultados/respostas/: não faz chamada nenhuma, não usa a
# chave e não gasta nada. Pode ser rodado quantas vezes quiser.
#
# Uso, de qualquer pasta:
#   experimento/compilar-resultados.sh           # o teste (a linha de base)
#   experimento/compilar-resultados.sh piloto    # a amostra do piloto (L7)
#   experimento/compilar-resultados.sh tudo      # todas as 720 combinações
#   experimento/compilar-resultados.sh teste --modelo DeepSeek   # só um modelo
#   experimento/compilar-resultados.sh tudo --cs C11-C17         # só estes CS
#
# O relatório fica em experimento/resultados/relatorio-<teste|piloto>.md (ou
# relatorio.md, com "tudo"). Abra no VS Code com a pré-visualização do Markdown
# (Ctrl+Shift+V) ou no GitHub. Sai com código 1 se alguma resposta pedir atenção.

set -uo pipefail
cd "$(dirname "$0")/.."

case "${1:-teste}" in
    teste) filtro=(--amostra teste) ;;
    piloto) filtro=(--amostra piloto) ;;
    tudo) filtro=() ;;
    *) echo "uso: $0 [teste|piloto|tudo] [--modelo NOME] [--modo aberto|forcado] [--cs LISTA]" >&2; exit 2 ;;
esac
shift $(( $# > 0 ? 1 : 0 ))

uv run --no-project --with-requirements experimento/requirements.txt python experimento/relatorio.py "${filtro[@]}" "$@"
