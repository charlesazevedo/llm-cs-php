#!/usr/bin/env python3
"""Monta o julgamento manual (L10): os casos, a chave e a página local de julgamento.

Os casos são (desenho de 03/10/2026, ampliado em 05/10/2026 por decisão do autor):
  - todos os "a julgar": combinações de variante, modelo e modo em que só um nome
    amplo cobre o CS injetado no código injetado (critério da D4);
  - todas as não detectadas com citação no código injetado que não usa nenhum
    nome do CS, específico ou amplo: o CS pode ter sido descrito com palavras
    que a lista de sinônimos não tem. As citações que nomeiam o CS e caem pela
    condição 3 (as mesmas da linha de base) não são mostradas: o critério as
    decide. As não detectadas sem citação no código injetado não entram;
  - uma amostra sorteada de AMOSTRA_DETECTADAS detecções automáticas, para medir
    quanto o casamento automático concorda com o julgamento humano.
Nos "a julgar" e nas não detectadas, um voto final "sim" conta como detecção.

O juiz não vê qual modelo respondeu (decisão do autor, 03/10/2026): os casos têm
ids neutros (J001, J002...) em ordem sorteada, e o modelo fica só na chave. A
página mostra a definição do CS, a forma da variante, o código injetado (que é
das variantes, de licença MIT; nada do resto da CaixaController) e as citações
da resposta que tocam o código injetado, com a justificativa do modelo.

Os juízes são o primeiro autor e um desenvolvedor convidado, identificados só
como juiz 1 e juiz 2 (decisão do autor, 05/10/2026). Antes dos casos, a página
mostra três exemplos comentados, para a calibração, todos tirados de detecções
automáticas que ficam fora da amostra: uma no modo aberto, uma no forçado e, de
uma terceira, só uma outra citação da resposta, que trata de outro problema
(o exemplo do "não"). Assim, nenhum caso a julgar vira exemplo.

Uso, da raiz do repositório (só lê as respostas; não faz chamada nenhuma):

    uv run --no-project --with-requirements experimento/requirements.txt \\
        python experimento/julgamento/montar.py [--saida PASTA]

Grava em PASTA (padrão: experimento/julgamento/): casos.json, chave.csv (não
abra antes de julgar) e julgamento.html, a página que os juízes abrem no
navegador. Rodar de novo com as mesmas respostas dá os mesmos casos (sementes
fixas). Monte o julgamento definitivo só depois da execução completa.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(AQUI.parent))
import analisar as A  # noqa: E402
import entradas as E  # noqa: E402
import harness as H  # noqa: E402
import prompts as P  # noqa: E402
import provedores as V  # noqa: E402
import sinonimos as S  # noqa: E402

SEMENTE = 20261003
AMOSTRA_DETECTADAS = 20
MODO = {"aberto": "aberto (o modelo listou os CS que achou)",
        "forcado": "forçado (o modelo recebeu o catálogo e marcou os itens presentes)"}


def codigo_injetado(entrada: E.Entrada) -> list[dict]:
    """Só o que a variante injetou: as linhas inseridas ou os arquivos novos, com a numeração da entrada."""
    blocos = []
    for inj in entrada.injetado:
        linhas = entrada.arquivos[inj["arquivo"]].rstrip("\n").split("\n")
        ini, fim = (1, len(linhas)) if inj.get("novo") else (inj["inicio"], inj["fim"])
        blocos.append({"arquivo": inj["arquivo"], "novo": bool(inj.get("novo")),
                       "linhas": [[n, linhas[n - 1]] for n in range(ini, fim + 1)]})
    return blocos


def citacao_para_juiz(c: dict, entrada: E.Entrada) -> dict:
    trechos = [t for t in c["trechos"] if A.no_injetado(t, entrada, entrada.injetado)]
    faixas = []
    for t in trechos:   # para a página destacar as linhas citadas no código
        arq, faixa = A._arquivo(t.get("arquivo"), list(entrada.arquivos)), A._intervalo(t)
        if arq and faixa:
            faixas.append({"arquivo": arq, "inicio": faixa[0], "fim": faixa[1]})
    return {"nome": c["nome"],
            "trechos": [f"{t.get('arquivo')}, linhas {t.get('linha_inicio')}-{t.get('linha_fim')}" for t in trechos],
            "faixas": faixas, "justificativa": c.get("justificativa") or ""}


def para_pagina(c: dict, cid: str, por_id: dict, forma: dict) -> dict:
    e = c["entrada"]
    return {
        "id": cid,
        "cs": {"id": e.cs_id, "nome": por_id[e.cs_id]["nome"], "descricao": por_id[e.cs_id]["descricao"]},
        "variante": {"id": e.id, "forma": forma.get(e.id, "")},
        "modo": MODO[c["modo"]],
        "codigo": codigo_injetado(e),
        "citacoes": [citacao_para_juiz(x, e) for x in c["citacoes"]],
    }


def exemplos_de_calibracao(detectadas: list[dict], por_id: dict) -> list[dict]:
    """Três exemplos para a calibração, de detecções automáticas que saem da amostra: uma no modo
    aberto, uma no forçado e, de uma terceira (aberto), só uma outra citação da resposta no código
    injetado, que não usa nenhum nome do CS. São os de código injetado mais curto, de CS diferentes
    (desempate pela entrada e pelo modelo), para o exemplo ser lido depressa. O do "não" diz que a
    citação trata de outro problema, o que o primeiro autor confere antes de mandar a página (o
    montar.py imprime os exemplos)."""
    def ordem(c):
        return sum(len(b["linhas"]) for b in codigo_injetado(c["entrada"])), c["entrada"].id, c["modelo"]
    usados, escolhidos = set(), []

    def primeiro(condicao):
        for c in sorted(detectadas, key=ordem):
            if c["entrada"].cs_id not in usados and condicao(c):
                usados.add(c["entrada"].cs_id)
                return c
        return None

    sim_aberto = primeiro(lambda c: c["modo"] == "aberto")
    sim_forcado = primeiro(lambda c: c["modo"] == "forcado")
    nao_aberto = primeiro(lambda c: c["modo"] == "aberto" and len(c["outras"]) == 1)
    for c, resposta in ((sim_aberto, "sim"), (sim_forcado, "sim"), (nao_aberto, "nao")):
        if c is None:
            continue
        e, nome = c["entrada"], por_id[c["entrada"].cs_id]["nome"]
        x = c["citacoes"][0] if resposta == "sim" else c["outras"][0]
        trecho = "; ".join(citacao_para_juiz(x, e)["trechos"])
        if resposta == "sim" and c["modo"] == "aberto":
            explicacao = (f"A citação «{x['nome']}» usa um nome do CS descrito ({nome}) e aponta {trecho}, "
                          "dentro do código injetado.")
        elif resposta == "sim":
            explicacao = (f"No modo forçado, o modelo marcou como presente o item do catálogo que é o CS descrito "
                          f"({nome}) e apontou {trecho}, dentro do código injetado.")
        else:
            outros = sorted(por_id[i]["nome"] for i in x["especifico"])
            sobre = f"outro CS do catálogo ({', '.join(outros)})" if outros else "outro problema"
            explicacao = (f"A citação «{x['nome']}» ({trecho}) trata de {sobre} e não descreve {nome}. "
                          "Para o exemplo, a página mostra só esta citação da resposta.")
        escolhidos.append({**c, "citacoes": [x], "resposta": resposta, "explicacao": explicacao})
    return escolhidos


def montar(saida: Path) -> dict:
    cfg, acesso, modelos = H.carregar_config()
    todas = E.montar()
    base = next(e for e in todas if e.id == "base")
    catalogo = P.ordem_do_catalogo()
    por_id = {c["id"]: c for c in catalogo}
    sinonimos = S.carregar()
    with open(E.TRABALHO / "exemplos" / "variantes.csv", encoding="utf-8") as f:
        forma = {f"{v['cs_id']}-{v['variante']}": v["forma"] for v in csv.DictReader(f)}

    a_julgar, detectadas, nao_detectadas = [], [], []
    for m in modelos:
        rota = V.roteamento(acesso, m)
        for modo in P.MODOS:
            estado_b, rb = H.situacao(m, rota, modo, base, cfg["max_tokens"])
            if estado_b != "valida":
                continue
            base_cits = A.citacoes(modo, rb.get("resposta"), catalogo, sinonimos)
            for e in todas:
                if not e.cs_id:
                    continue
                estado, r = H.situacao(m, rota, modo, e, cfg["max_tokens"])
                if estado != "valida":
                    continue
                cits = A.citacoes(modo, r.get("resposta"), catalogo, sinonimos)
                av = A.avaliar(e, e.injetado, cits, base_cits, list(base.arquivos))
                no_codigo = [c for c in cits if any(A.no_injetado(t, e, e.injetado) for t in c["trechos"])]
                # citações no código injetado que não usam nenhum nome do CS (as que usam são do critério)
                sem_nome = [c for c in no_codigo if e.cs_id not in c["especifico"] | c["amplo"]]
                caso = {"entrada": e, "modelo": m.nome, "modo": modo, "automatico": av["resultado"]}
                if av["resultado"] == "a_julgar":
                    a_julgar.append({**caso, "citacoes": av["a_julgar"]})
                elif av["resultado"] == "detectada":
                    detectadas.append({**caso, "citacoes": [c for c in no_codigo if e.cs_id in c["especifico"]],
                                       "outras": sem_nome})
                elif sem_nome and isinstance(r.get("resposta"), dict):
                    nao_detectadas.append({**caso, "citacoes": sem_nome})

    exemplos = exemplos_de_calibracao(detectadas, por_id)
    fora = {(x["entrada"].id, x["modelo"], x["modo"]) for x in exemplos}
    detectadas = [c for c in detectadas if (c["entrada"].id, c["modelo"], c["modo"]) not in fora]

    sorteio = random.Random(SEMENTE)
    amostra_d = sorteio.sample(detectadas, min(AMOSTRA_DETECTADAS, len(detectadas)))
    todos = ([("a_julgar", c) for c in a_julgar] + [("nao_detectada", c) for c in nao_detectadas]
             + [("amostra_detectada", c) for c in amostra_d])
    sorteio.shuffle(todos)

    casos, chave = [], []
    for i, (tipo, c) in enumerate(todos, 1):
        e = c["entrada"]
        cid = f"J{i:03d}"
        casos.append(para_pagina(c, cid, por_id, forma))
        chave.append({"id": cid, "tipo": tipo, "entrada": e.id, "cs_id": e.cs_id, "modelo": c["modelo"],
                      "modo": c["modo"], "automatico": c["automatico"]})

    saida.mkdir(parents=True, exist_ok=True)
    dados = {"semente": SEMENTE, "casos": casos,
             "exemplos": [{**para_pagina(x, f"E{i}", por_id, forma), "resposta": x["resposta"],
                           "explicacao": x["explicacao"], "entrada": x["entrada"].id}
                          for i, x in enumerate(exemplos, 1)]}
    (saida / "casos.json").write_text(json.dumps(dados, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    with open(saida / "chave.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(chave[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(chave)
    modelo_html = (AQUI / "pagina.html").read_text(encoding="utf-8")
    dados_js = json.dumps(dados, ensure_ascii=False).replace("</", "<\\/")
    (saida / "julgamento.html").write_text(modelo_html.replace("/*DADOS*/null", dados_js), encoding="utf-8")
    return {"a_julgar": len(a_julgar), "nao_detectadas": len(nao_detectadas), "detectadas": len(detectadas),
            "amostra_d": len(amostra_d), "casos": len(casos), "exemplos": dados["exemplos"]}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--saida", help="pasta de saída (padrão: experimento/julgamento/)")
    args = p.parse_args()
    saida = Path(args.saida) if args.saida else AQUI
    n = montar(saida)
    print(f"{n['casos']} casos: {n['a_julgar']} a julgar e {n['nao_detectadas']} não detectadas com citação no código "
          f"injetado (todos), e {n['amostra_d']} de {n['detectadas']} detecções automáticas (sorteadas, semente "
          f"{SEMENTE}).")
    print(f"{len(n['exemplos'])} exemplos de calibração (fora da amostra; confira-os antes de mandar a página):")
    for x in n["exemplos"]:
        print(f"  {x['id']} {x['entrada']} ({x['modo'].split(' ')[0]}), resposta {x['resposta']}: {x['explicacao']}")
    print(f"Página: {saida / 'julgamento.html'}; chave (não abra antes de julgar): {saida / 'chave.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
