#!/usr/bin/env bash
# Piloto (L7): a amostra de 11 entradas nos quatro modelos e nos dois modos,
# 88 chamadas. GASTA CRÉDITOS (~US$ 6 e ~32 min com as filas em paralelo, pela
# estimativa do teste; o valor e o tempo atualizados aparecem antes, e o script
# pede confirmação).
#
# A amostra: a linha de base, a primeira variante de cada uma das 9 categorias
# do catálogo (C01-v1, C11-v1, C18-v1, C21-v1, C24-v1, C25-v1, C29-v1, C30-v1,
# C35-v1) e a C24-v3, a única que mexe na CaixaController e cria um arquivo. É
# a primeira vez que os modelos veem variantes com CS injetado: o relatório
# mostra se eles apontam o CS injetado, se as linhas batem, que nomes usam (e
# quais a lista de sinônimos não reconhece), se o modo forçado funciona e o
# custo e o tempo reais.
#
# As respostas já gravadas e válidas (as 8 da linha de base, do teste) não são
# refeitas nem pagas de novo. Se o piloto não pedir ajuste, as 88 entram na
# execução completa; se pedir (prompt, parâmetros), as afetadas ficam
# desatualizadas e são refeitas. Ajustes depois do piloto ficam registrados no
# plano.
#
# Uso, de qualquer pasta:
#   experimento/rodar-piloto.sh                     # as 88 chamadas (as que faltam)
#   experimento/rodar-piloto.sh --modelo DeepSeek   # só um modelo, 22 chamadas
#   experimento/rodar-piloto.sh --modo aberto       # só um modo, 44 chamadas
#   experimento/rodar-piloto.sh --sequencial        # uma chamada por vez (~1h10)
#   experimento/rodar-piloto.sh --sim               # sem a pergunta de confirmação
#
# Ctrl+C durante as chamadas para com segurança: as em andamento terminam e são
# gravadas, e rodar de novo continua de onde parou. O resultado fica em
# experimento/resultados/relatorio-piloto.md (refeito a qualquer momento, sem
# custo, com experimento/compilar-resultados.sh piloto).

exec "$(dirname "$0")/rodar-amostra.sh" piloto "$@"
