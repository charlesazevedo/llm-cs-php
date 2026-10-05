# Pacote de replicação: Quais Code Smells os Modelos de Linguagem Detectam em Aplicações PHP? Um Estudo Experimental

Charles de Azevedo Júnior e Wilkerson de Lucena Andrade — Universidade Federal de Campina Grande (UFCG).

Este pacote reúne o necessário para refazer o experimento do artigo:
- as variantes dos Code Smells (CS) e a neutralização aplicada a elas;
- os *prompts*, a configuração dos modelos e os scripts de execução;
- as respostas brutas dos modelos;
- a lista de sinônimos, o critério de detecção e o julgamento manual;
- os resultados.

O protocolo está em [PROTOCOLO.md](PROTOCOLO.md).

No experimento, 89 variantes de 38 CS, os do catálogo de uma revisão sistemática anterior dos autores, são injetadas uma de cada vez no PDVLaravel, uma aplicação Laravel de código aberto. Quatro modelos de linguagem (ChatGPT, Claude, Gemini e DeepSeek), chamados por API, analisam cada variante em dois modos: sem o catálogo de CS no *prompt* (aberto) e com ele (forçado).

## Conteúdo

| caminho | conteúdo | licença |
|---|---|---|
| `PROTOCOLO.md` | objetivo, questões de pesquisa, objetos, modelos e acesso, *prompts*, procedimento, critério de detecção, julgamento manual e análise | CC BY 4.0 |
| `dados/cs-experimento.csv` | os 38 CS (C01–C38): nome, categoria, especificidade (G genérico, W web, P ligado ao PHP), descrição e estudos de origem | CC BY 4.0 |
| `dados/sinonimos.csv` | a lista de sinônimos do modo aberto: 490 nomes, cada um com o CS, a origem e o tipo (específico ou amplo) | CC BY 4.0 |
| `experimento/exemplos/` | as 89 variantes (`Cxx-*/vN/`), com os metadados (`variantes.csv`) e as convenções (`README.md`), copiadas sem alteração da release v1.0 do [tools-cs-php](https://github.com/charlesazevedo/tools-cs-php) e conferidas por `experimento/exemplos.sha256` | MIT |
| `experimento/neutralizacao.csv` | a auditoria das variantes: o que nelas poderia entregar o CS ou o experimento a um modelo, e o que foi feito em cada caso | CC BY 4.0 |
| `experimento/auditoria/` | os scripts da auditoria (`extrair.py`, `tokens.php`) | MIT |
| `experimento/prompts.py` | os *prompts* e os esquemas de resposta dos dois modos, e a ordem sorteada do catálogo | MIT |
| `experimento/modelos.yaml` | os modelos: id no OpenRouter, *snapshot*, provedor fixado, formato da resposta, parâmetros e preços | MIT |
| `experimento/harness.py`, `entradas.py`, `provedores.py`, `sinonimos.py` | montagem das entradas, com a neutralização; chamadas; casamento dos nomes com a lista de sinônimos | MIT |
| `experimento/*.sh` | um script por etapa: conferir o acesso, teste com a linha de base, piloto, execução completa e relatório | MIT |
| `experimento/analisar.py`, `relatorio.py` | o critério de detecção e o relatório das respostas gravadas | MIT |
| `experimento/julgamento/` | o julgamento manual: os scripts e a página; os casos, a chave, os votos de cada juiz, as divergências com o consenso e o resultado | MIT (código), CC BY 4.0 (dados) |
| `experimento/resultados/` | as entradas, as respostas brutas, o ambiente e os resultados (abaixo) | CC BY 4.0 |
| `experimento/README.md` | os comandos e as opções de cada script | CC BY 4.0 |

As referências a itens como "L5", "L8" ou "D4" nos comentários dos scripts remetem ao plano de revisão do artigo, que não faz parte do pacote. O `PROTOCOLO.md` descreve o que cada decisão estabeleceu.

## Resultados

Em `experimento/resultados/`:

- **`respostas/<Modelo>/<modo>/<entrada>.json`:** uma resposta por modelo, modo e entrada (720). Cada uma guarda:
  - o que foi pedido: o modelo, a rota (`provider`), o formato, os parâmetros, o limite de *tokens*, o *hash* da condição (instruções, *prompt* e esquema) e o SHA-256 da entrada;
  - o que serviu: o *snapshot* (`modelo_servido`) e o provedor (`provedor_servido`), os metadados de roteamento do OpenRouter e os `desvios` da rota, se houve;
  - o custo: *tokens* de entrada, de saída e de raciocínio, duração e custo cobrado em US$;
  - a resposta: o JSON do modelo em `resposta` ou, se ele não for JSON válido, o texto em `texto_bruto`.
- **`entradas.json`:** as 90 entradas (a linha de base e as 89 variantes), sem o código: os arquivos com o número de linhas e o SHA-256, as faixas injetadas e a neutralização aplicada.
- **`ambiente.json`:** as versões do Python e das bibliotecas, a rota de cada modelo, o *snapshot* e o provedor que serviram as respostas, as datas da primeira e da última chamada e o *hash* das condições.
- **`deteccoes-variantes.csv`:** uma linha por variante, modelo e modo (712 linhas). As colunas são:
  - `resultado`: `detectada` ou `nao_detectada`, e o `motivo`; `automatico` é o resultado do critério sozinho (`detectada`, `a_julgar` ou `nao_detectada`) e `julgamento`, o voto final do julgamento manual, quando o caso foi julgado;
  - `citacoes`, `outros_citados`, `outros_do_catalogo`: quantos CS a resposta cita, quantos não são o CS da variante e quantos destes estão no catálogo;
  - `json_valido`: se a resposta veio em JSON válido.
- **`deteccoes-cs.csv`:** por CS, modelo e modo, quantas variantes foram detectadas (e quantas delas pelo julgamento manual, `pelo_julgamento`) e o resultado (`todas`, `algumas` ou `nenhuma`).
- **`linha-de-base.csv`:** os CS do catálogo que cada modelo aponta na `CaixaController` sem injeção.
- **`a-julgar.csv`:** as citações que só um nome amplo liga ao CS da variante, que foram ao julgamento manual.

A execução completa foi de 02/10/2026 a 05/10/2026: 720 respostas, todas pelo provedor fixado e sem desvio de rota; 719 completas e em JSON válido (a do Gemini no modo forçado à variante C05-v2 entrou em laço até o limite de *tokens* e conta como inválida); custo total US$ 35,62. No julgamento manual, os dois juízes julgaram 225 casos e concordaram em 217 (kappa de Cohen 0,85); 8 casos passaram a contar como detecção, todos no modo aberto. Os números estão no `PROTOCOLO.md`.

Em `experimento/julgamento/`: `casos.json` e `julgamento.html` (os casos, como os juízes os viram), `chave.csv` (o modelo e o modo de cada caso), `votos-juiz-1.csv` e `votos-juiz-2.csv`, `divergencias.csv` e `consenso.csv`, e `resultado.csv` (o voto final de cada caso e quem o decidiu).

## Como reproduzir

Há duas formas: reaplicar o critério às respostas publicadas, sem custo, ou chamar os modelos de novo.

Requisitos: o Python 3.12 (a versão usada) e o [uv](https://docs.astral.sh/uv/), que monta um ambiente temporário com as dependências de `experimento/requirements.txt`; o PHP só para refazer a auditoria das variantes. Os comandos rodam da raiz do pacote.

### Reaplicar o critério (sem custo, sem chave)

```bash
uv run --no-project --with-requirements experimento/requirements.txt python experimento/harness.py preparar
uv run --no-project --with-requirements experimento/requirements.txt python experimento/analisar.py
```

- `preparar` baixa a `CaixaController` do PDVLaravel no commit fixado, confere o SHA-256 dela e das variantes, aplica a neutralização e monta as 90 entradas. O `entradas.json` gerado deve ser idêntico ao publicado.
- `analisar.py` aplica o critério de detecção às respostas de `experimento/resultados/respostas/`, aplica o voto final do julgamento manual (`experimento/julgamento/resultado.csv`) e regrava os CSV de `experimento/resultados/`, que devem sair iguais aos publicados. Com `--sem-julgamento`, dá só o resultado do critério.
- `experimento/compilar-resultados.sh tudo` compila as respostas num relatório legível (`experimento/resultados/relatorio.md`).

### Chamar os modelos de novo (com custo)

1. Crie uma chave no [OpenRouter](https://openrouter.ai/settings/keys) e grave-a em `experimento/.env` (modelo em `experimento/.env.example`). A conta precisa permitir endpoints pagos que treinam com os *prompts*, porque o endpoint oficial da DeepSeek treina.
2. Confira o acesso, sem custo: a chave, os modelos no catálogo público e as 720 chamadas montadas.
   ```bash
   experimento/conferir-acesso.sh
   ```
3. Rode. Cada script mostra o custo e o tempo estimados e pede confirmação antes de chamar.
   ```bash
   experimento/teste-linha-de-base.sh     # a linha de base: 8 chamadas
   experimento/rodar-piloto.sh            # o piloto: 88 chamadas
   experimento/rodar-completa.sh          # tudo: 720 chamadas
   ```
   - A execução completa custou US$ 35,62 em 720 chamadas (02/10/2026 a 05/10/2026). Somadas, as chamadas de cada modelo levaram de 0,8 h (Claude) a 4,3 h (DeepSeek); os quatro modelos rodam em paralelo, uma fila cada.
   - Para rodar só um conjunto de CS ou um modelo: `--cs C11-C17`, `--modelo DeepSeek`, `--modo aberto` (detalhes em `experimento/README.md`).
   - As respostas publicadas estão em `experimento/resultados/respostas/` e não são refeitas: para chamar de novo, mova a pasta antes.
4. Analise e monte o julgamento manual:
   ```bash
   uv run --no-project --with-requirements experimento/requirements.txt python experimento/analisar.py
   uv run --no-project --with-requirements experimento/requirements.txt python experimento/julgamento/montar.py
   ```

Os modelos não são determinísticos, e os provedores trocam os *snapshots* e os retiram do catálogo. Uma nova execução pode dar respostas diferentes, mesmo com o mesmo *snapshot*. Por isso as respostas brutas estão publicadas: elas permitem conferir e refazer a análise sem chamar os modelos.

## O que não está incluído, e por quê

- **O PDVLaravel.** O projeto não declara licença. O `preparar` baixa do GitHub só a `CaixaController`, no commit `98cddb84521765c29ff7ed691d7f5ba325cc7edc`, e confere o SHA-256 dela. As variantes não contêm código do PDVLaravel.
- **O texto das entradas e os *prompts* montados.** Eles contêm a `CaixaController` e ficam na área de trabalho (`experimento/trabalho/`), que o `preparar` e o `testar` recriam.
- **A chave do OpenRouter** (`experimento/.env`).

## Apoio de IA generativa

Os *prompts*, os scripts de execução e de análise, a auditoria das variantes, que identificou o que nelas poderia entregar o CS a um modelo, e a lista de sinônimos foram elaborados com apoio de um assistente de IA generativa (o Claude Opus 5.5, da Anthropic). A auditoria e a lista de sinônimos foram validadas pelo primeiro autor, e os *prompts* e os scripts foram testados antes da execução completa, num teste com a linha de base e num piloto. O julgamento manual foi feito pelo primeiro autor e por um desenvolvedor convidado.

## Licenças

- **Código:** os scripts, os *prompts*, a configuração dos modelos, a página de julgamento e as variantes estão sob a licença MIT ([LICENSE](LICENSE)). As variantes vêm do tools-cs-php, dos mesmos autores e sob a mesma licença.
- **Dados e resultados:** `dados/`, `experimento/neutralizacao.csv`, `experimento/resultados/`, os dados do julgamento, este README e o protocolo estão sob a licença CC BY 4.0 ([LICENSE-DADOS](LICENSE-DADOS)).

## Como citar

Artigo: Charles de Azevedo Júnior e Wilkerson de Lucena Andrade. *Quais Code Smells os Modelos de Linguagem Detectam em Aplicações PHP? Um Estudo Experimental.* Manuscrito, 2026.

Pacote de replicação (este repositório): https://github.com/charlesazevedo/llm-cs-php

Variantes dos CS (origem): https://github.com/charlesazevedo/tools-cs-php

Revisão sistemática que originou o catálogo de CS: https://github.com/charlesazevedo/rls-cs-web-app-php
