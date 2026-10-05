# Experimento

O experimento do artigo: quatro modelos de linguagem, chamados por API, analisam
as 89 variantes dos 38 CS do artigo de ferramentas, aplicadas à `CaixaController`
do PDVLaravel no commit `98cddb8`, e a linha de base. Os quatro são chamados pelo
[OpenRouter](https://openrouter.ai/docs/quickstart), com uma chave e uma
cobrança só (L5b). Os ids entre parênteses (L5, D4...) são itens do plano de
revisão do artigo, que não faz parte do pacote de replicação; o `PROTOCOLO.md`
do pacote descreve o que cada decisão estabeleceu.

| arquivo | papel | item |
|---|---|---|
| `harness.py` | os comandos: `preparar`, `testar`, `estimar`, `modelos`, `conta`, `rodar`, `resumo` | L5 |
| `conferir-acesso.sh`, `teste-linha-de-base.sh` | o teste antes do piloto: o acesso, sem custo, e a linha de base nos quatro modelos e dois modos (8 chamadas) | L7 |
| `rodar-piloto.sh` | o piloto: as 11 entradas da amostra nos quatro modelos e dois modos (88 chamadas) | L7 |
| `rodar-completa.sh` | a execução completa: as 90 entradas, 720 chamadas, sem suspender o computador e com a saída num log | L8 |
| `rodar-amostra.sh` | o núcleo dos três scripts acima: chave, estimativa, confirmação, chamadas e relatório | L7, L8 |
| `analisar.py` | a análise pelo critério da D4: detecção por variante, modelo e modo, resumo por CS, linha de base e os casos para o julgamento manual (CSV em `resultados/` ou em `--saida`); aplica o voto final de `julgamento/resultado.csv` quando ele existe (`--sem-julgamento` dá só o automático) | L9, L10 |
| `julgamento/` | o julgamento manual (L10): `montar.py` (casos, chave e a página `julgamento.html`), `pagina.html` (o modelo da página) e `apurar.py` (kappa, divergências e resultado) | L10 |
| `relatorio.py`, `compilar-resultados.sh` | o relatório das respostas gravadas (`resultados/relatorio-<amostra>.md`), sem custo | L7 |
| `entradas.py` | baixa e confere as fontes, aplica a neutralização e monta as 90 entradas | L5 |
| `prompts.py` | os prompts e os esquemas de resposta dos modos aberto e forçado; a ordem sorteada do catálogo | L5 |
| `provedores.py` | a chamada pelo OpenRouter (SDK `openai`), com o provedor de origem fixado, e a consulta ao catálogo público | L5, L5b |
| `sinonimos.py` | normalização e casamento dos nomes que os modelos dão aos CS com `../dados/sinonimos.csv` | L6 |
| `modelos.yaml` | o acesso (API, chave, política de dados) e os modelos: id, *snapshot*, provedor fixado, formato, parâmetros e preços | L5, L5b (modelos e política de dados a confirmar antes da L7) |
| `exemplos.sha256` | manifesto das variantes da release v1.0 do `tools-cs-php` | L5 |
| `exemplos/` | só no pacote de replicação: as variantes, copiadas sem alteração da release v1.0 do `tools-cs-php` (MIT); fora dele, o `preparar` as baixa | F3 |
| `requirements.txt`, `.env.example` | dependências e a chave do OpenRouter que precisa existir | L5, L5b |
| `neutralizacao.csv` | o que, nas variantes, pode entregar o CS ou o experimento a um modelo, e o que fazer em cada caso | L4 (validado pelo autor em 01/10/2026) |
| `auditoria/` | `extrair.py` e `tokens.php` (o texto que o modelo leria em cada variante) e `tamanho.py` (tokens das 90 entradas; estimativa anterior ao piloto, fora do pacote de replicação) | L4 |
| `resultados/entradas.json` | as 90 entradas: arquivos, linhas, SHA-256, faixas injetadas e neutralização aplicada (sem código) | L5 |
| `resultados/respostas/` | uma resposta por modelo, modo e entrada (L8) | L5, L8 |
| `resultados/ambiente.json` | versões, rota pedida e o que serviu cada modelo, custo, datas e condições, para a tabela do protocolo (C3) | L5, L8 |
| `trabalho/` | fora do git: a `CaixaController` original (o PDVLaravel não tem licença), as variantes baixadas, o texto das entradas e os prompts | L5 |

## Como rodar

O Python do sistema é gerenciado pelo Debian; o `uv` monta um ambiente temporário
com as dependências. Da raiz do repositório:

```bash
h() { uv run --no-project --with-requirements experimento/requirements.txt python experimento/harness.py "$@"; }
h preparar                 # baixa e confere as fontes, monta as 90 entradas, grava resultados/entradas.json
h testar                   # monta as 720 chamadas sem enviar nenhuma
h testar --mostrar C03-v1 --modo forcado    # imprime um prompt inteiro
h estimar                  # chamadas, tokens e custo (preços de modelos.yaml)
h modelos                  # confere modelos.yaml no catálogo público do OpenRouter (sem chave, sem custo)
h conta                    # confere a chave: limite de gasto e uso (sem custo)
h rodar --amostra teste    # teste: a linha de base x 4 modelos x 2 modos = 8 chamadas
h resumo --amostra teste   # o que veio: provedor, snapshot, tokens, custo, CS citados, trechos fora do código
h rodar --amostra piloto   # piloto (L7): 11 entradas x 4 modelos x 2 modos = 88 chamadas
h rodar                    # execução completa (L8): 720 chamadas, uma fila por modelo em paralelo
```

Por padrão, o `rodar` faz as quatro filas em paralelo, uma por modelo (ver
*Paralelismo*, no Protocolo). Para rodar um de cada vez:

```bash
h rodar --amostra piloto --sequencial        # todos os modelos, uma chamada por vez
h rodar --amostra piloto --modelo DeepSeek   # só um modelo (a fila dele, uma chamada por vez)
h rodar --cs C11-C17                         # só as variantes destes CS, nos 4 modelos e 2 modos
h rodar --cs C01,C05,C24                     # idem, para uma lista de CS
h rodar --modelo Claude --modo aberto --entrada C13-v1   # uma chamada só
h rodar --amostra piloto --refazer           # refaz também as desatualizadas (o aviso diz o que mudou)
```

Sem `--amostra`, os mesmos comandos valem para a execução completa. O `--cs`
aceita ids (`C24`), intervalos (`C11-C17`) e listas (`C01,C05,C24` ou
`"C01 C05 C24"`). Como os ids estão em sequência por categoria, um intervalo pega
uma categoria inteira:

| `--cs` | Categoria | CS | Variantes |
|---|---|---|---|
| `C01-C10` | PHP e aplicações web | 10 | 24 |
| `C11-C17` | Tamanho | 7 | 14 |
| `C18-C20` | Complexidade | 3 | 6 |
| `C21-C23` | Herança e acoplamento | 3 | 6 |
| `C24` | Duplicação | 1 | 3 |
| `C25-C28` | Código não utilizado | 4 | 11 |
| `C29` | Exceções | 1 | 3 |
| `C30-C34` | Documentação | 5 | 12 |
| `C35-C38` | Estilo | 4 | 10 |

Cada variante dá 8 chamadas (4 modelos × 2 modos). Por exemplo, só a categoria
de tamanho (14 variantes, 112 chamadas), pelo script da execução completa:

```bash
experimento/rodar-completa.sh --cs C11-C17
```

Os filtros
`--amostra`, `--modelo`, `--modo`, `--entrada` e `--cs` valem também para
`estimar`, `resumo`, `relatorio.py` e `analisar.py`. Uma resposta gravada e válida nunca é refeita: dá
para rodar um modelo de cada vez, em dias ou horários diferentes, e cada rodada
só completa o que falta. Uma resposta gravada com outro *prompt*, modelo, rota,
parâmetros ou limite de *tokens* fica desatualizada: o `rodar` a aponta e a
pula, e só a refaz com `--refazer`.

A chave do OpenRouter fica em `experimento/.env` (copie de `.env.example`); sem
ela, `rodar` não faz nenhuma chamada. Cada `rodar` real gasta créditos: rode o
piloto antes e confira o custo com `estimar`. Sem rede, `preparar` aceita as
fontes locais: `EXEMPLOS=<pasta das variantes>` e `PDVLARAVEL_BASE=<raiz de uma
cópia do PDVLaravel no commit 98cddb8>`, conferidas pelo SHA-256 como as
baixadas. No pacote de replicação, as variantes já vêm em `exemplos/`.

### Teste e piloto pelos scripts

Para quem não quer usar o harness direto, há scripts para cada etapa, na ordem:
`conferir-acesso.sh` (sem custo), `teste-linha-de-base.sh` (8 chamadas),
`rodar-piloto.sh` (88 chamadas), `rodar-completa.sh` (720 chamadas) e
`compilar-resultados.sh` (o relatório, sem custo, a qualquer momento). Os três
que fazem chamadas usam o mesmo núcleo,
`rodar-amostra.sh`: conferem a chave, mostram quantas chamadas faltam com o
custo e o tempo estimados, pedem confirmação, fazem as chamadas (uma fila por
modelo, em paralelo) e terminam com o relatório. Aceitam as mesmas opções:
`--sim`, `--modelo NOME`, `--modo aberto|forcado` e `--sequencial`.

#### Teste antes do piloto

Dois scripts, para rodar na ordem, de qualquer pasta:

```bash
experimento/conferir-acesso.sh
```

Não gasta nada nem faz chamada de inferência: confere a chave (limite de gasto e
uso), `modelos.yaml` no catálogo público e as 720 chamadas montadas.

```bash
experimento/teste-linha-de-base.sh
```

Manda a linha de base (a `CaixaController` sem CS injetado) aos quatro modelos,
nos dois modos: 8 chamadas, cobradas. Mostra a estimativa e pede confirmação
antes. As opções (as mesmas do `rodar-piloto.sh` e do `rodar-completa.sh`, que aceita também `--cs`, por exemplo `experimento/rodar-completa.sh --cs C11-C17` para uma categoria):

```bash
experimento/teste-linha-de-base.sh --sim            # sem a pergunta de confirmação
experimento/teste-linha-de-base.sh --modo aberto    # só um modo: 4 chamadas
experimento/teste-linha-de-base.sh --modelo DeepSeek               # só um modelo: 2 chamadas
experimento/teste-linha-de-base.sh --modelo DeepSeek --modo forcado    # 1 chamada
experimento/teste-linha-de-base.sh --sequencial     # uma chamada por vez, sem as filas em paralelo
```

No fim, ele compila o resultado no relatório (`resultados/relatorio-teste.md`,
ver abaixo), com o que veio em cada resposta e a estimativa do piloto e da
execução completa refeita com os *tokens* e os tempos medidos. As respostas
ficam em `resultados/respostas/` e são reaproveitadas pelo piloto e pela
execução completa. Rodar o script de novo não gasta nada, a não ser que algo
tenha mudado: aí ele refaz as desatualizadas, com a estimativa e a confirmação
antes. Antes de rodar, vale pôr um
limite de gasto na chave (openrouter.ai/settings/keys) e conferir se a
configuração de privacidade da conta permite endpoints pagos que treinam com os
*prompts* (a DeepSeek precisa disso).

#### Piloto (L7)

```bash
experimento/rodar-piloto.sh
```

A linha de base, a primeira variante de cada uma das 9 categorias do catálogo
(C01-v1, C11-v1, C18-v1, C21-v1, C24-v1, C25-v1, C29-v1, C30-v1, C35-v1) e a
C24-v3, a única que mexe na `CaixaController` e cria um arquivo: 11 entradas,
88 chamadas, ~US$ 6 e ~32 min pela estimativa do teste. As 8 da linha de base,
já feitas no teste, não são refeitas. É a primeira vez que os modelos veem
variantes com CS injetado: o relatório (`resultados/relatorio-piloto.md`)
mostra se eles apontam o CS injetado, se as linhas batem, que nomes usam e quais
a lista de sinônimos não reconhece. Se o piloto não pedir ajuste, as 88
respostas entram na execução completa; se pedir, as afetadas ficam
desatualizadas e são refeitas, e o ajuste fica registrado no plano.

#### Execução completa (L8)

```bash
experimento/rodar-completa.sh
```

As 90 entradas nos quatro modelos e dois modos: 720 chamadas, ~US$ 44 e ~3h40
com as filas em paralelo, pela estimativa do piloto. As 88 já feitas no teste e
no piloto não são refeitas. Roda depois de aprovado o protocolo (L7). Por ser
longa, o script impede o computador de suspender enquanto roda
(`systemd-inhibit`; fechar a tampa ou desligar ainda interrompe) e grava toda a
saída em `trabalho/logs/execucao-completa-<data>.log`, fora do git. A DeepSeek
cobra o dobro nos dias úteis das 22h à 1h e das 3h às 7h (horário de Brasília):
começar fora desses horários sai mais barato. O resultado fica em
`resultados/relatorio.md`.

#### Relatório

```bash
experimento/compilar-resultados.sh           # o teste; também: piloto, tudo
```

Compila as respostas gravadas em `resultados/relatorio-teste.md` (ou
`relatorio-piloto.md`, `relatorio.md`), sem custo: um resumo, o que pede atenção
e o que fazer, a rota de cada chamada, se as respostas vieram inteiras, os CS que
cada modelo apontou (casados com o catálogo pela lista de sinônimos), uma prévia de quais variantes tiveram o CS injetado apontado (pelo nome, sem conferir as linhas ainda), os nomes
que a lista não reconhece, o custo, os tokens e a projeção do piloto e da
execução completa, e o detalhe de cada resposta. O `teste-linha-de-base.sh`
chama o mesmo relatório no fim. Com `--modelo` ou `--modo` (ex.: `compilar-resultados.sh teste --modelo DeepSeek`), o relatório mostra só o escolhido, num arquivo próprio (`relatorio-teste-deepseek.md`).

### Julgamento manual (L10)

Depois da execução completa, dois juízes julgam, cada um por si, os casos que
o casamento automático não decide e uma amostra das decisões automáticas: o
primeiro autor e um desenvolvedor convidado, que não participou do desenho do
estudo (decisão do autor, 05/10/2026). Os dois aparecem só como juiz 1 e juiz 2.

```bash
uv run --no-project --with-requirements experimento/requirements.txt python experimento/julgamento/montar.py
```

Monta os casos em `julgamento/`:
- **todos os "a julgar":** só um nome amplo cobre o CS injetado no código injetado (ex.: *Large Class* numa variante de *Excessive Class Length*);
- **todas as não detecções com citação no código injetado** que não usa nenhum nome do CS, específico ou amplo: o CS pode ter sido descrito com palavras que a lista de sinônimos não tem (decisão do autor, 05/10/2026; até ali, eram 20 sorteadas). As citações que nomeiam o CS e caem pela condição 3, iguais às da linha de base, não aparecem: o critério as decide. As não detecções sem citação no código injetado não entram;
- **uma amostra sorteada** (semente fixa) de 20 detecções automáticas, para medir o casamento automático.

Nos "a julgar" e nas não detecções, um voto final "sim" conta como detecção.

O juiz não vê qual modelo respondeu: os casos têm ids neutros (J01, J02...) em
ordem sorteada, e o modelo fica só em `chave.csv`, que não deve ser aberto antes
de julgar. A página (`julgamento.html`) abre no navegador, sem internet: mostra
a definição do CS, a forma da variante, o código injetado (só o das variantes,
de licença MIT, com realce de sintaxe nas cores do VS Code e as linhas citadas
destacadas) e as citações da resposta nesse código, com a justificativa do
modelo, e pergunta se alguma aponta o CS descrito (sim, não ou dúvida, com
comentário). Antes, a página dá as orientações de como decidir e três exemplos
comentados, para a calibração: uma detecção no modo aberto, uma no forçado e uma
não detecção, que o critério decide e que ficam fora da amostra. O `montar.py`
imprime os exemplos: confira-os antes de mandar a página. Os votos ficam salvos
no navegador; no fim, cada juiz baixa `votos-juiz-1.csv` ou `votos-juiz-2.csv`
e o põe nesta pasta. O CSV baixado no meio do caminho serve de cópia de
segurança: com **Retomar de um CSV baixado**, a página carrega os votos dele
(do mesmo juiz) e continua do primeiro caso sem voto, em outro navegador ou
computador. Para o segundo juiz, basta mandar `julgamento.html`: a página tem
tudo e funciona sem internet.

```bash
python3 experimento/julgamento/apurar.py
```

Calcula o kappa de Cohen entre os dois juízes e grava `divergencias.csv` com os
casos em que os votos diferem ou em que houve dúvida. Os juízes discutem esses
casos, preenchem a coluna `consenso` (sim ou nao) e salvam como `consenso.csv`;
onde não houver acordo, o segundo autor (o orientador) decide, e a coluna
`decidido_por` fica `segundo_autor`.
Rodando de novo, o `apurar.py` grava `resultado.csv` (chave, votos e voto final)
e mede, na amostra, quanto o casamento automático concorda com o julgamento.

Com o `resultado.csv` na pasta, o `analisar.py` passa a aplicar o voto final:
nos "a julgar" e nas não detecções, um "sim" vira `detectada` e um "não" num
"a julgar" vira `nao_detectada`; a amostra não muda de resultado. Em
`deteccoes-variantes.csv`, `automatico` guarda o resultado do critério e
`julgamento`, o voto; em `deteccoes-cs.csv`, `pelo_julgamento` conta as
variantes detectadas pelo voto. Se um caso julgado tiver outro resultado
automático na análise de agora, o `analisar.py` para: o julgamento é de outra
análise. Rode `analisar.py` de novo depois de apurar, e depois `make tabelas
figuras` na raiz. `--sem-julgamento` dá só o resultado automático.

Resultado (05/10/2026): 225 casos (54 a julgar, 151 não detecções com citação
no código injetado e 20 detecções da amostra); os juízes concordaram em 217
(kappa de Cohen 0,85), e as 8 divergências foram resolvidas por consenso,
nenhuma pelo segundo autor. Passaram a contar como detecção 8 casos (4 a julgar
e 4 não detecções), todos no modo aberto; as 20 detecções da amostra foram
confirmadas. Nos 171 casos que o critério decide (não detecções e amostra), o
casamento automático concorda com o julgamento em 167 (kappa 0,90).

## Protocolo

- **Fontes.** A `CaixaController` é baixada do GitHub no commit `98cddb8` e conferida por SHA-256 (`c7fd39ed…`, a mesma que as ferramentas analisaram). As variantes vêm da release v1.0 do `tools-cs-php` e são conferidas arquivo por arquivo contra `exemplos.sha256`.
- **Entradas (D11).** Uma entrada tem só os arquivos que a variante toca, cada um com a linha `=== arquivo: <caminho> ===` e as linhas numeradas. As variantes do tipo `membros` entram na `CaixaController` como no `executar.py` do artigo de ferramentas: o corpo da classe `Fragmento` vai antes da chave que fecha a classe, depois de uma linha em branco. A faixa inserida e os arquivos novos ficam em `entradas.json`, para o critério da D4. O arquivo de apoio do Psalm (`Referencias.php`) é coisa do braço das ferramentas e não entra.
- **Neutralização (L4).** É aplicada na montagem, por substituição exata de texto, regra a regra (`entradas.REGRAS`, com os ids de `neutralizacao.csv`). Cada regra tem de se aplicar o número esperado de vezes. Depois, nenhuma entrada pode conter "experimento", "fragmento", "variante" nem um id de CS; se contiver, a montagem para.
- **Modos e prompts (D12).** O texto é o mesmo para todos os provedores, em português. No modo aberto, o modelo lista os CS que achar, com arquivo e linhas. No forçado, avalia cada um dos 38 itens do catálogo, com as descrições da RSL, na ordem sorteada pela semente `20261001`, a mesma para todos. O prompt de sistema é neutro. A resposta é JSON, com esquema validado pelo provedor onde ele aceita (OpenAI, Anthropic, Google AI Studio) e só JSON válido na DeepSeek.
- **Acesso (L5b).** Todas as chamadas vão ao OpenRouter, com o id do modelo no formato `<autor>/<modelo>` (nunca um apelido *latest*) e o endpoint do provedor de origem fixado: `provider: {order: [<provedor>], allow_fallbacks: false, require_parameters: true}`. Sem *fallback*, a chamada não muda de provedor; com `require_parameters`, ela falha se o provedor não aceitar algum parâmetro, em vez de seguir sem ele. Os plugins que a conta pode ligar por padrão (correção de JSON, compressão do prompt, busca na web) e o cache de respostas do OpenRouter são desligados em toda chamada. Cada resposta guarda o *snapshot* e o provedor que a serviram, o custo cobrado e os metadados de roteamento; uma resposta servida por outro provedor, depois de outra tentativa ou com algum plugin no caminho é gravada com os `desvios` e acusada no fim do `rodar`. Política de dados: `data_collection: "deny"` (só provedores que não treinam com os *prompts*) em todos, menos na DeepSeek, que vai com `"allow"` porque o endpoint oficial dela treina com eles; a conta do OpenRouter tem de permitir endpoints pagos que treinam. O comando `modelos` confere cada modelo no catálogo público: *snapshot*, data de saída, parâmetros que o endpoint aceita e preço.
- **Paralelismo.** O `rodar` faz uma fila por modelo, as quatro em paralelo; cada fila faz as entradas do seu modelo uma depois da outra. Nunca há mais de uma chamada por fabricante ao mesmo tempo, e o tempo total é o do modelo mais lento (a DeepSeek: ~3 min por entrada nos dois modos; ~32 min no piloto e ~4h40 na execução completa, pela duração média do teste). As chamadas são independentes, sem conversa nem cache, e o paralelismo não muda as respostas; cada resposta registra a forma de execução (`execucao`). No começo, o `rodar` diz quantas respostas já estão gravadas e quantas chamadas vai fazer; cada chamada concluída sai com o contador (`[23/80]`), quantas faltam e o tempo previsto (pela duração média das chamadas do modelo mais demorado, ou da soma, em sequência); e, a cada 2 min sem chamada concluída, ele mostra as que estão em andamento e há quanto tempo. Ctrl+C para de começar chamadas novas e espera as em andamento terminarem e serem gravadas; um segundo Ctrl+C, mais de 2 s depois, sai na hora, e as em andamento, já cobradas, se perdem.
- **Recusas e tempo limite.** O SDK fica sem repetição automática, porque ele reenviaria um pedido que passou do tempo limite, e um pedido que o servidor terminasse depois disso seria cobrado duas vezes. O tempo limite é de 20 min (a chamada mais longa do teste levou 134 s). Só se tenta de novo, até 6 vezes, o que foi recusado antes de o modelo gerar qualquer coisa e não é cobrado: limite de requisições do fabricante (429), reserva de crédito das chamadas em andamento cheia (402 `in_flight_budget_exhausted`, que o OpenRouter aplica a contas novas ou com saldo baixo) e erro do servidor (5xx), respeitando o `Retry-After`. Um tempo limite ou uma conexão caída viram erro, e a chamada é refeita na próxima rodada. Uma resposta 200 do OpenRouter sem nenhuma escolha do modelo (sem modelo servido, tokens nem texto) não é gravada: se o erro que vem no corpo tem código repetível (5xx ou 429, como o 502 `provider_unavailable` da OpenAI sobrecarregada), ela é tentada de novo como as outras recusas; sem código, ou depois das 6 tentativas, vira erro e é refeita na próxima rodada. Até 05/10/2026, essas respostas eram gravadas como vazias: as 5 gravadas assim (ChatGPT, modo forçado, em C11–C17) ficaram como "falha" e foram refeitas.
- **Execução (D13).** Uma chamada por modelo, modo e entrada, com temperatura 0 onde o endpoint fixado aceita, menos no Gemini: só a DeepSeek vai com 0. O GPT-5.6 e o Claude Opus 5.5 não aceitam o parâmetro, e o Gemini fica com a temperatura padrão (1), que o Google recomenda nos Gemini 3 (abaixo de 1, o modelo pode entrar em laço ou ter desempenho pior). Nenhum fallback de modelo: uma recusa fica registrada como resposta. Uma resposta com JSON inválido também fica gravada, com o texto bruto, e conta como resposta do modelo, com o CS não detectado; vale também para uma resposta que entra em laço e repete o mesmo trecho até o limite de *tokens*, que o relatório identifica (decisão do autor, 03/10/2026: não se refaz).
- **Cache.** Cada resposta guarda o hash da condição (sistema, prompt, esquema e, no forçado, o catálogo), o SHA-256 da entrada, o modelo, a rota, o formato e os parâmetros pedidos. Uma resposta em que algum deles mudou é acusada como desatualizada e só é refeita com `--refazer`.

## Lista de sinônimos (L6)

`../dados/sinonimos.csv` tem a lista validada pelo autor e **fechada em 03/10/2026**: 490 sinônimos (331 específicos, 159 amplos), com a origem de cada um. Dos 490, 15 entraram depois do piloto (origem `piloto`): nomes certos que os modelos usaram para o código injetado e que a lista não tinha. A lista não muda mais; o `make conferir` confere o SHA-256 do arquivo.

- **Origens:** o nome no catálogo, os nomes que os estudos da RSL usaram (com a tradução entre parênteses), os nomes da V3, os nomes de regra do PHPMD e do Psalm, formas usuais na literatura e em português (`proposta`) e os acréscimos do piloto (`piloto`).
- **Tipos:** um sinônimo **específico** nomeia aquele CS, e o casamento conta como detecção se o trecho apontado for o injetado (D4). Um **amplo** é genérico e pode cobrir vários CS (*God Class*, código morto, estilo de código); ele não decide sozinho e vai para o julgamento manual (L10).
- **Casamento:** `sinonimos.py` normaliza os dois lados igualmente (camelCase separado, sem acento nem pontuação, plural e gênero unificados, "utilizado"/"usado" unificados). Como a separação do camelCase depende da capitalização ("JavaScript" vira "java script", e "javascript" fica inteiro), ele compara também as duas formas sem separar o camelCase, e casa se qualquer uma casar; a regra do mais longo vale nas duas. Essa comparação entrou em 05/10/2026, durante a execução completa (decisão do autor), quando se viu que os sinônimos em minúsculas com "javascript", três deles acrescentados no piloto, não casavam com respostas que escreviam "JavaScript": nas 361 combinações gravadas até ali, 5 passaram de não detectada a detectada, todas no modo aberto, em C05 e C07. Um nome casa com um sinônimo quando contém as palavras dele na mesma ordem, com no máximo uma palavra entre duas delas; entre dois específicos em que um contém o outro, vale o mais longo ("too many public methods" fica com C15, e não com C14).
- **Conferências:** cada CS tem ao menos três específicos, o nome do catálogo casa com o próprio CS, e nenhum específico casa com outro CS. A única ambiguidade encontrada, os nomes de regra `ComplexMethod` e `ComplexFunction` do Psalm (mapeados para C18 e C19 no artigo de ferramentas), ficou específica para C18 e ampla para C19.

## Auditoria das variantes (L4)

As variantes foram escritas para ferramentas, que não leem comentários nem
nomes; um modelo lê. A auditoria leu o que cada variante mostraria pela opção
(a) da D11: nas do tipo `membros`, só o que é inserido na `CaixaController` (o
*docblock* da classe `Fragmento` fica de fora); nas do tipo `arquivos`, os
arquivos novos com o caminho.

```bash
python3 experimento/auditoria/extrair.py
```

Resultado, em `neutralizacao.csv` (19 linhas, validadas pelo autor em 01/10/2026):

- **Caminhos e *namespace* (N01–N04), forte, 37 variantes.** O *namespace* `App\Experimento\Cxx\Vn` e as *views* em `resources/views/experimento/cxx-vn-*` dizem que o código foi injetado e trazem o id do CS. A proposta é `App\Pdv`, `app/Pdv/` e `resources/views/admin/caixa/<nome>`, como as *views* do projeto.
- **Comentários que descrevem o CS (N05–N15), forte, 5 variantes:** C03-v1 e C03-v2 (os *docblocks* declaram o privilégio que cada rotina exige), C04-v1 (o *docblock* diz que os privilégios têm a mesma semântica e são definidos por componente), C08-v1 e C08-v2 (os *docblocks* dizem que o HTML é montado em partes ou que o script fica em outra classe).
- **Pistas leves (N07, N16, N17).** O nome `registrarSangriaAutorizada` (C03-v1) e a classe `PainelPublicoDoCaixa` (C17) mudam.
- **Mantidos (N12, N18, N19), com justificativa:** os *docblocks* de C04-v2, o comentário do `catch` de C29-v2 (é a forma da variante) e o da hierarquia de C22.

O resto das 89 variantes não tem comentário, nome ou *string* que entregue o CS.
Os *docblocks* dos métodos são descrições do domínio, exigidas pela regra de
isolamento das variantes.

A neutralização é aplicada pelo *harness* na preparação (L5), por substituição
exata de texto, sem editar as variantes. Nas variantes `membros`, as trocas são
dentro da mesma linha, e as linhas inseridas não mudam de número. Nas de
arquivos, remover linhas não afeta o critério, que conta pelo arquivo (D4).

**Consequência para a D12:** no modo forçado, o catálogo não pode ser numerado
na ordem C01–C38. Sem a N01, o número do item sairia do *namespace*. Mesmo com
ela, convém sortear a ordem dos itens, com semente fixa e igual para todos os
modelos.

## Tamanho das entradas

Estimativa feita antes do piloto, para as decisões D10–D13; o script lê a
área de trabalho do artigo de ferramentas e não entra no pacote de replicação.
O piloto mediu os *tokens* de verdade, que estão em cada resposta gravada.

```bash
uv run --no-project --with tiktoken python experimento/auditoria/tamanho.py
```

Com as linhas numeradas e o tokenizador `o200k_base` (aproximação; os outros
provedores contam de outro jeito):

- 90 entradas: mediana de 3.122 *tokens* de código. A menor tem 167; as maiores são a C11-v2 (classe de 2.000 linhas, 22.026), a C11-v1 (11.135) e a C23-v2 (31 arquivos, 10.535);
- uma rodada (90 entradas, um modelo, uma repetição): ~297 mil *tokens* de entrada no modo aberto e ~377 mil no forçado, que leva o catálogo com as descrições (894 *tokens*);
- 4 modelos, 2 modos e 5 repetições: 3.600 chamadas, ~13,5 M *tokens* de entrada e ~4,7 M de saída;
- 4 modelos, 2 modos e 10 repetições: 7.200 chamadas, ~27,0 M de entrada e ~9,4 M de saída.

A saída é suposta (600 *tokens* por resposta no modo aberto, 2.000 no
forçado) e não inclui os *tokens* de raciocínio dos modelos que os cobram.
O piloto (L7) mede os dois.
