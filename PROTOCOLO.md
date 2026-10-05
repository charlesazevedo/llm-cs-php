# Protocolo do experimento

Experimento de avaliação de modelos de linguagem, planejado segundo Wohlin et al. (2012) e relatado segundo o roteiro de Jedlitschka et al. (2008):
- os **tratamentos** são os modelos e os modos de pergunta;
- os **objetos** são as variantes de cada CS;
- a **variável dependente** é a detecção de cada variante.

## Objetivo e questões de pesquisa

No formato GQM: *analisar* quatro modelos de linguagem *com o propósito de* avaliar sua capacidade de detectar CS e o custo dessa detecção *com respeito aos* CS relatados em estudos sobre aplicações web PHP, *do ponto de vista de* desenvolvedores e pesquisadores, *no contexto de* uma aplicação web Laravel de código aberto.

- **QP1:** Quais CS cada modelo detecta, com e sem o catálogo de CS no *prompt*?
- **QP2:** Quanto os modelos concordam entre si?
- **QP3:** Quanto custa a detecção, em *tokens*, tempo e dinheiro?

## Code Smells

Os 38 CS são o catálogo de uma revisão sistemática anterior dos autores (https://github.com/charlesazevedo/rls-cs-web-app-php), que reuniu os CS relatados nos estudos sobre aplicações web PHP (`dados/cs-experimento.csv`).

## Variantes e projeto

As 89 variantes e a forma de injetá-las vêm de um estudo anterior dos autores, com ferramentas de análise estática, e estão publicadas no pacote dele (https://github.com/charlesazevedo/tools-cs-php, release v1.0). Aqui são usadas sem alteração, copiadas em `experimento/exemplos/` e conferidas arquivo por arquivo contra `experimento/exemplos.sha256`. As convenções estão em `experimento/exemplos/README.md`: duas variantes para 25 CS e três para 13, escritas a partir da definição de cada CS.

Projeto: PDVLaravel (https://github.com/Lucasczm/PDVLaravel), commit `98cddb84521765c29ff7ed691d7f5ba325cc7edc`. Cada variante é aplicada à versão original, uma de cada vez:
- **Membros** (52 variantes): o corpo da classe `Fragmento` do `membros.php` da variante é inserido no fim da classe `app/Http/Controllers/Admin/CaixaController.php` (232 linhas), antes da chave que a fecha, depois de uma linha em branco. As linhas originais, exceto a chave final, não mudam de número.
- **Arquivos** (36 variantes): classes e *views* novas, para os CS de classe e os de HTML, CSS e JavaScript.
- **Membros e arquivos** (1 variante): os dois tipos combinados.

O arquivo de apoio `Referencias.php` do estudo de origem, que só cita as classes novas para uma das ferramentas, não entra.

## Entradas

Cada entrada tem só os arquivos que a variante toca: a `CaixaController` com os membros inseridos, os arquivos novos, ou os dois. Cada arquivo vem com o caminho e as linhas numeradas, para que o modelo possa apontar onde está cada CS. A linha de base é a `CaixaController` sem injeção. São 90 entradas (`experimento/resultados/entradas.json`).

### Neutralização

No estudo de origem, as variantes não precisavam esconder o CS de quem lê o código; um modelo lê nomes e comentários. Antes do experimento, uma auditoria leu o que o modelo veria em cada variante (`experimento/auditoria/`) e registrou o que poderia entregar o CS ou o próprio experimento (`experimento/neutralizacao.csv`, validado pelo primeiro autor):
- o *namespace* e os caminhos com o identificador do CS (`App\Experimento\C11\V1`, `resources/views/experimento/...`), trocados por `App\Pdv` e pelas pastas de *views* do projeto;
- os comentários que descrevem o CS, em cinco variantes;
- dois nomes de método e de classe.

A troca é feita na montagem das entradas, por substituição exata de texto, sem editar as variantes e sem mudar o número das linhas inseridas. Cada regra tem de se aplicar o número esperado de vezes; depois, nenhuma entrada pode conter "experimento", "fragmento", "variante" nem um identificador de CS. A neutralização alcança 39 das 90 entradas.

## Modelos e acesso

| Modelo | Id no OpenRouter | *Snapshot* | Provedor fixado | Resposta | Temperatura |
|---|---|---|---|---|---|
| ChatGPT | `openai/gpt-5.6-sol` | `openai/gpt-5.6-sol-20260709` | OpenAI | esquema JSON | não aceita o parâmetro |
| Claude | `anthropic/claude-opus-5.5` | `anthropic/claude-opus-5.5-20260921` | Anthropic | esquema JSON | não aceita o parâmetro |
| Gemini | `google/gemini-3.1-pro-preview` | `google/gemini-3.1-pro-preview-20260219` | Google AI Studio | esquema JSON | padrão (1), recomendada pelo fabricante |
| DeepSeek | `deepseek/deepseek-v4-pro-0813` | `deepseek/deepseek-v4-pro-20260813` | DeepSeek | JSON válido, sem esquema | 0 |

- **Intermediário:** todas as chamadas vão ao OpenRouter (https://openrouter.ai), com uma chave só. Cada chamada fixa o endpoint do provedor de origem (`provider: {order: [<provedor>], allow_fallbacks: false, require_parameters: true}`): o pedido não vai a outro provedor, e falha se o provedor não aceitar algum parâmetro, em vez de seguir sem ele.
- **Recursos desligados:** os *plugins* que a conta pode ligar por padrão (correção de JSON, compressão do *prompt*, busca na web) e o cache de respostas do OpenRouter. Nos modelos da OpenAI e da Anthropic, o OpenRouter submete a entrada a uma moderação de conteúdo, que não a altera.
- **Registro:** cada resposta guarda o *snapshot* e o provedor que a serviram, os metadados de roteamento, os *tokens*, o tempo e o custo cobrado. Uma resposta servida fora da rota é gravada com os `desvios`.
- **Política de dados:** só provedores que não treinam com os *prompts* (`data_collection: "deny"`), menos a DeepSeek, cujo endpoint oficial treina com eles (`"allow"`). O código enviado é público.
- **Parâmetros:** os padrões de cada modelo, inclusive o raciocínio. O limite de saída é de 64.000 *tokens*, perto do máximo do provedor mais restrito, para que nenhuma resposta seja cortada.

## *Prompts*

Os *prompts* estão em `experimento/prompts.py`, em português e iguais para todos os modelos, inclusive a instrução de formato. O *prompt* de sistema é neutro. Há dois modos:
- **Aberto:** o modelo recebe só o código e o pedido de uma verificação completa, e lista os CS que encontrar, com nome, arquivo, intervalo de linhas e justificativa.
- **Forçado:** o modelo recebe também o catálogo dos 38 CS, com as descrições da revisão sistemática, e diz, para cada item, se ele está presente e onde. Os itens são numerados numa ordem sorteada (semente `20261001`), a mesma para todos os modelos e entradas, para que o número não sugira o CS.

A resposta é JSON. O esquema é validado pelo provedor onde ele aceita; na DeepSeek, só a validade do JSON é garantida.

## Procedimento

1. **Preparação:** download da `CaixaController` no commit fixado, conferência das fontes pelo SHA-256, neutralização e montagem das 90 entradas (`harness.py preparar`).
2. **Teste:** a linha de base nos quatro modelos e dois modos (8 chamadas), para conferir a rota, o formato e o custo.
3. **Piloto:** a linha de base, a primeira variante de cada uma das nove categorias do catálogo e a única variante de membros e arquivos (11 entradas, 88 chamadas), para conferir o critério de detecção e a lista de sinônimos. As 88 respostas entraram na execução completa; depois do piloto, só a lista de sinônimos mudou (ver abaixo).
4. **Execução completa:** as 90 entradas nos quatro modelos e dois modos, 720 chamadas, uma por entrada, modelo e modo. As chamadas de cada modelo seguem uma depois da outra, e os quatro modelos rodam em paralelo; as chamadas são independentes, sem conversa nem cache.
5. **Análise:** o critério de detecção é aplicado às respostas gravadas (`analisar.py`).
6. **Julgamento manual:** os casos que o critério não decide e uma amostra das decisões automáticas (`julgamento/`); o voto final entra na análise (`analisar.py` de novo).

- **Respostas inválidas:** uma resposta com JSON inválido conta como resposta do modelo, com o CS não detectado, e não é refeita, inclusive a que repete o mesmo trecho até o limite de *tokens*.
- **Repetições:** só se tenta de novo, até 6 vezes, o que o provedor recusou antes de gerar qualquer coisa e que não é cobrado (limite de requisições, reserva de crédito cheia, erro do servidor), inclusive quando o OpenRouter devolve o erro do servidor dentro de uma resposta sem nenhuma resposta do modelo. Um tempo limite, uma conexão caída ou uma resposta sem resposta do modelo e sem erro repetível viram erro, e a chamada é refeita numa rodada seguinte. O tempo limite de cada chamada é de 20 minutos.

A execução completa foi de 02/10/2026 a 05/10/2026 (o teste e o piloto, em 02/10, entraram nela; o resto rodou em 03/10 e 05/10, por categoria de CS). As 720 respostas foram atendidas pelo provedor fixado, na primeira tentativa, sem desvio de rota; 719 vieram completas e em JSON válido. A única inválida é a do Gemini, no modo forçado, à variante C05-v2, que repetiu o mesmo trecho até o limite de 64.000 *tokens*; pelo protocolo, ela conta como resposta do modelo, com o CS não detectado. Custo total: US$ 35,62.

## Critério de detecção

Um modelo detecta uma variante, num modo, quando a resposta tem uma citação que satisfaz três condições:

1. **Nomeia o CS da variante.** No modo aberto, com um nome que casa com um sinônimo *específico* do CS em `dados/sinonimos.csv`; no forçado, marcando como presente o item do CS.
2. **Aponta para o que a variante injetou:** um arquivo novo ou um intervalo de linhas que cruza as linhas inseridas na `CaixaController`.
3. **Não é a citação que a linha de base já fazia:** o mesmo CS, no mesmo intervalo de linhas, com até três linhas de folga nas pontas, depois de corrigir o deslocamento das linhas que vêm depois da injeção.

Uma citação que satisfaz as condições 2 e 3 com um sinônimo *amplo* do CS (como *Large Class* ou "código morto", que podem cobrir vários CS) não conta como detecção nem como erro: vai para o julgamento manual. As outras citações de cada resposta entram só como contagem, sem julgamento de cada uma, e por isso a precisão não é medida.

Um CS é detectado por um modelo, num modo, quando ao menos uma das suas variantes é detectada.

## Lista de sinônimos

`dados/sinonimos.csv` tem 490 nomes: 331 específicos, que nomeiam um CS só, e 159 amplos. Cada um tem a origem:
- `catalogo`: o nome no catálogo;
- `rsl`: os nomes usados nos estudos da revisão sistemática;
- `regra:Psalm`: nomes de regra do Psalm, uma ferramenta de análise estática para PHP;
- `proposta`: formas usuais na literatura e em português;
- `piloto`: 15 nomes certos que os modelos usaram para o código injetado, no piloto e nas variantes dos dez primeiros CS (C01–C10), e que a lista não tinha.

A lista foi validada pelo primeiro autor e fechada com esses acréscimos, antes do resto da execução completa (C11–C38); o que as respostas trouxeram de novo depois disso não entrou.

O casamento é feito por script (`experimento/sinonimos.py`), com o nome e o sinônimo normalizados da mesma forma: *camelCase* separado, sem acento nem pontuação, plural e gênero unificados. Como a separação do *camelCase* depende da capitalização ("JavaScript" vira duas palavras, "javascript" fica uma), as duas formas também são comparadas sem separar o *camelCase*, e o nome casa se qualquer uma das comparações casar. Essa comparação foi acrescentada durante a execução completa, quando se viu que sinônimos em minúsculas com "javascript" não casavam com respostas que escreviam "JavaScript"; a lista não mudou, e o efeito, nas 361 combinações gravadas até ali, foi de 5 não detecções que passaram a detecções, todas no modo aberto. Um nome casa com um sinônimo quando contém as palavras dele na mesma ordem, com no máximo uma palavra entre duas delas. Entre dois específicos em que um contém o outro, vale o mais longo. Cada CS tem ao menos três sinônimos específicos, e nenhum específico casa com outro CS.

## Julgamento manual

Dois juízes julgam, cada um por si: o primeiro autor e um desenvolvedor convidado, com 5 anos de experiência com PHP e com aplicações web, que já conhecia CS e não participou do desenho do estudo. Nos dados, eles aparecem só como juiz 1 e juiz 2. Os casos são:
- **todos os casos "a julgar":** só um nome amplo liga a citação ao CS da variante;
- **todas as não detecções com citação no código injetado** que não usa nenhum nome do CS, específico ou amplo, porque o CS pode ter sido descrito com palavras que a lista de sinônimos não tem. As citações que nomeiam o CS e caem pela condição 3 não são mostradas, porque o critério as decide. As não detecções sem citação no código injetado não entram;
- **uma amostra sorteada** (semente `20261003`) de 20 detecções automáticas.

Nos casos "a julgar" e nas não detecções, um voto final "sim" conta como detecção. Nas não detecções e nas detecções da amostra, o voto também mede quanto o casamento automático concorda com o julgamento humano. O desenho inicial julgava só 20 não detecções sorteadas, para essa medida; ele foi ampliado antes do julgamento, durante a execução completa.

O juiz não vê qual modelo respondeu: os casos têm ids neutros (J01, J02...) em ordem sorteada, e o modelo e o modo ficam só na chave. A página de julgamento mostra a definição do CS, a forma da variante, o código injetado e as citações da resposta nesse código, com a justificativa do modelo, e pergunta se alguma aponta o CS descrito (sim, não ou dúvida). Antes dos casos, ela dá as orientações de como decidir e três exemplos comentados, para a calibração: uma detecção no modo aberto, uma no forçado e uma não detecção, que o critério decide e que ficam fora da amostra. A concordância entre os juízes é medida pelo kappa de Cohen. As divergências e as dúvidas são decididas por consenso entre os dois e, onde não houver acordo, pelo segundo autor.

Foram julgados 225 casos: 54 a julgar, 151 não detecções com citação no código injetado e 20 detecções da amostra. Os juízes concordaram em 217 (kappa de Cohen 0,85), sem nenhum voto de dúvida; as 8 divergências foram resolvidas por consenso, nenhuma pelo segundo autor. Passaram a contar como detecção 8 casos (4 a julgar e 4 não detecções), todos no modo aberto: 3 do ChatGPT, 3 do Claude e 2 do Gemini; os outros 50 casos a julgar ficaram como não detecção. As 20 detecções da amostra foram confirmadas. Nos 171 casos que o critério decide (as não detecções e a amostra), o casamento automático concorda com o julgamento em 167 (kappa 0,90).

## Análise

A análise é descritiva, sem testes estatísticos. Para cada CS, modelo e modo, o resultado é "todas", "algumas" ou "nenhuma" variante detectada. A partir daí:
- **QP1:** os CS detectados por cada modelo, em cada modo;
- **QP2:** a concordância entre os modelos, variante a variante, e a cobertura acumulada, com os modelos somados na ordem que mais acrescenta CS;
- **QP3:** os *tokens* de entrada, de saída e de raciocínio, o tempo e o custo por modelo e modo, das respostas gravadas.
