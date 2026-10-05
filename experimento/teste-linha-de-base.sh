#!/usr/bin/env bash
# Etapa 1, antes do piloto: a linha de base (a CaixaController sem CS injetado)
# nos quatro modelos e nos dois modos, 8 chamadas. GASTA CRÉDITOS (centavos; o
# valor estimado aparece antes, e o script pede confirmação).
#
# Mostra se a chave e a conta funcionam, se cada chamada foi ao provedor fixado,
# se as respostas vêm em JSON válido e com linhas dentro do arquivo, e o custo e
# os tokens de raciocínio reais, que refazem a estimativa do piloto e da
# execução completa. No fim, compila tudo em
# experimento/resultados/relatorio-teste.md (o mesmo que
# experimento/compilar-resultados.sh faz a qualquer momento, sem custo).
#
# As respostas ficam em experimento/resultados/respostas/<modelo>/<modo>/base.json
# e são reaproveitadas pelo piloto e pela execução completa, que não as refazem
# enquanto o prompt, o modelo, a rota, os parâmetros e o limite de tokens forem
# os mesmos. Rodar o script de novo não gasta nada: só mostra o resultado do que
# já está gravado. Se algo disso mudou, as respostas antigas ficam desatualizadas
# e o script as refaz (e as substitui), com confirmação.
#
# Uso, de qualquer pasta:
#   experimento/teste-linha-de-base.sh                 # os dois modos, 8 chamadas
#   experimento/teste-linha-de-base.sh --modo aberto   # só um modo, 4 chamadas
#   experimento/teste-linha-de-base.sh --modelo DeepSeek   # só um modelo, 2 chamadas
#   experimento/teste-linha-de-base.sh --modelo DeepSeek --modo forcado   # 1 chamada
#   experimento/teste-linha-de-base.sh --sequencial    # uma chamada por vez, sem as filas em paralelo
#   experimento/teste-linha-de-base.sh --sim           # sem a pergunta de confirmação
#
# Os modelos são os de modelos.yaml: ChatGPT, Claude, Gemini, DeepSeek. Com
# --modelo ou --modo, o relatório do fim mostra só o que foi escolhido, num
# arquivo próprio (ex.: relatorio-teste-deepseek-forcado.md). O trabalho é
# feito pelo rodar-amostra.sh, o mesmo do rodar-piloto.sh.

exec "$(dirname "$0")/rodar-amostra.sh" teste "$@"
