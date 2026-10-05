#!/usr/bin/env bash
# Núcleo comum do teste-linha-de-base.sh e do rodar-piloto.sh: roda uma amostra
# do experimento com estimativa e confirmação antes e o relatório depois.
# GASTA CRÉDITOS.
#
#   1. confere a chave do OpenRouter (sem custo);
#   2. mostra quantas chamadas faltam, o custo e o tempo estimados;
#   3. pede confirmação e faz as chamadas que faltam, uma fila por modelo em
#      paralelo (refaz também as desatualizadas; as gravadas e válidas nunca
#      são refeitas nem pagas de novo);
#   4. compila o resultado em experimento/resultados/relatorio-<amostra>.md.
#
# Uso, de qualquer pasta (normalmente pelos dois scripts que o chamam):
#   experimento/rodar-amostra.sh teste|piloto|completa [opções]
#
# Opções:
#   --sim               sem a pergunta de confirmação
#   --modelo NOME       só um modelo de modelos.yaml (ChatGPT, Claude, Gemini, DeepSeek)
#   --modo aberto|forcado   só um modo
#   --cs LISTA          só as variantes destes CS: C01, C01-C10 ou C01,C05,C11-C17
#   --sequencial        uma chamada por vez, sem as filas em paralelo
#
# Ctrl+C durante as chamadas para de começar chamadas novas e espera as em
# andamento terminarem e serem gravadas; rodar de novo continua de onde parou.

set -uo pipefail
cd "$(dirname "$0")/.."

h() { uv run --no-project --with-requirements experimento/requirements.txt python experimento/harness.py "$@"; }

case "${1:-}" in
    teste) filtro=(--amostra teste); nome="do teste (a linha de base)" ;;
    piloto) filtro=(--amostra piloto); nome="do piloto (L7)" ;;
    completa) filtro=(); nome="da execução completa (L8)" ;;
    *) echo "uso: $0 teste|piloto|completa [--sim] [--sequencial] [--modelo NOME] [--modo aberto|forcado] [--cs LISTA]" >&2; exit 2 ;;
esac
amostra=$1
shift

so_rodar=(--refazer)
confirmar=1
while [ $# -gt 0 ]; do
    case "$1" in
        --sim) confirmar=0 ;;
        --sequencial) so_rodar+=(--sequencial) ;;
        --modo) filtro+=(--modo "${2:?--modo precisa de aberto ou forcado}"); shift ;;
        --modelo) filtro+=(--modelo "${2:?--modelo precisa do nome: ChatGPT, Claude, Gemini ou DeepSeek}"); shift ;;
        --cs) filtro+=(--cs "${2:?--cs precisa dos CS: C01, C01-C10 ou C01,C05,C11-C17}"); shift ;;
        *) echo "opção desconhecida: $1 (use --sim, --sequencial, --modelo NOME, --modo aberto|forcado ou --cs LISTA)" >&2; exit 2 ;;
    esac
    shift
done

echo "=== 1/4 Chave do OpenRouter"
h conta || { echo "Corrija a chave antes. Nenhuma chamada de inferência foi feita."; exit 1; }
echo
echo "=== 2/4 Estimativa $nome"
h estimar "${filtro[@]}" || { echo "Nada foi enviado."; exit 1; }
echo
if [ "$confirmar" -eq 1 ]; then
    read -r -p "Fazer as chamadas que faltam? Elas são cobradas. [s/N] " resposta
    case "$resposta" in
        s|S|sim|Sim) ;;
        *) echo "Nada foi enviado."; exit 0 ;;
    esac
fi
echo
echo "=== 3/4 Chamadas (Ctrl+C para com segurança: as em andamento terminam e são gravadas)"
h rodar "${filtro[@]}" "${so_rodar[@]}"
rodou=$?
echo
echo "=== 4/4 Resultado"
uv run --no-project --with-requirements experimento/requirements.txt python experimento/relatorio.py "${filtro[@]}"
relatorio=$?
echo
if [ "$rodou" -ne 0 ] || [ "$relatorio" -ne 0 ]; then
    echo "Algo pede atenção: veja a seção \"O que pede atenção\" do relatório."
    echo "Chamadas que deram erro ou não começaram (Ctrl+C) são feitas ao rodar o script de novo."
    echo "Se uma chamada da DeepSeek deu ERRO por política de dados, confira openrouter.ai/settings/privacy:"
    echo "a conta tem de permitir endpoints pagos que treinam com os prompts."
    exit 1
fi
echo "Concluído sem problemas ($amostra)."
