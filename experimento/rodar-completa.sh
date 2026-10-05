#!/usr/bin/env bash
# Execução completa (L8): as 90 entradas (89 variantes e a linha de base) nos
# quatro modelos e nos dois modos, 720 chamadas. GASTA CRÉDITOS (~US$ 44 e
# ~3h40 com as filas em paralelo, pela estimativa do piloto; o valor e o tempo
# atualizados aparecem antes, e o script pede confirmação). As respostas já
# gravadas e válidas (as 88 do teste e do piloto) não são refeitas.
#
# Pelo plano, roda depois que o protocolo for aprovado (L7). A lista de
# sinônimos (L6) não entra nas chamadas, só na análise, e pode ser fixada depois.
#
# Para uma execução longa, o script:
#   - impede o computador de suspender enquanto roda (systemd-inhibit, se
#     houver); fechar a tampa ou desligar ainda interrompe;
#   - grava toda a saída em experimento/trabalho/logs/execucao-completa-<data>.log
#     (fora do git), além de mostrá-la na tela.
#
# A DeepSeek cobra o dobro nos dias úteis das 22h à 1h e das 3h às 7h (horário
# de Brasília); começar fora desses horários sai mais barato. O preço dos
# outros modelos não muda com o horário.
#
# Uso, de qualquer pasta:
#   experimento/rodar-completa.sh                     # as 720 (as que faltam)
#   experimento/rodar-completa.sh --modelo DeepSeek   # só um modelo, 180 chamadas
#   experimento/rodar-completa.sh --modo aberto       # só um modo, 360 chamadas
#   experimento/rodar-completa.sh --cs C11-C17        # só os CS de tamanho, nos 4 modelos e 2 modos
#   experimento/rodar-completa.sh --cs C01,C05,C24    # só as variantes destes três CS
#   experimento/rodar-completa.sh --sequencial        # uma chamada por vez (~10 h)
#   experimento/rodar-completa.sh --sim               # sem a pergunta de confirmação
#
# Ctrl+C para com segurança: as chamadas em andamento terminam e são gravadas,
# e rodar de novo continua de onde parou, sem refazer nem pagar de novo o que já
# foi feito. O resultado fica em experimento/resultados/relatorio.md (refeito a
# qualquer momento, sem custo, com experimento/compilar-resultados.sh tudo). Com
# --cs, --modelo ou --modo, o relatório mostra só o escolhido, num arquivo
# próprio (ex.: relatorio-selecao-cs-c11-c17.md).

set -uo pipefail
script="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"
cd "$(dirname "$script")/.."

# 1. sem suspensão: o script se reexecuta dentro do systemd-inhibit
if [ -z "${EXECUCAO_INIBIDA:-}" ] && command -v systemd-inhibit >/dev/null 2>&1 \
        && systemd-inhibit --what=sleep:idle --why="teste" true >/dev/null 2>&1; then
    export EXECUCAO_INIBIDA=1
    exec systemd-inhibit --what=sleep:idle --who="experimento (artigo-ia)" \
        --why="execução completa do experimento (L8)" "$script" "$@"
fi
if [ -z "${EXECUCAO_INIBIDA:-}" ]; then
    echo "Aviso: não deu para impedir a suspensão; deixe o computador ligado e sem suspender até o fim."
fi

# 2. registro: a saída vai também para o log; o tee ignora o Ctrl+C, para não
#    cortar a saída do harness enquanto ele termina as chamadas em andamento
mkdir -p experimento/trabalho/logs
log="experimento/trabalho/logs/execucao-completa-$(date +%Y%m%d-%H%M%S).log"
exec > >(trap '' INT; exec tee -a "$log") 2>&1
echo "Registro desta execução: $log"

exec experimento/rodar-amostra.sh completa "$@"
