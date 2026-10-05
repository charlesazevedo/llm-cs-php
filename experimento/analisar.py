#!/usr/bin/env python3
"""Análise das respostas pelo critério de detecção da D4 (item L9 do plano).

Um modelo detecta uma variante, num modo, quando a resposta tem uma citação que:

  1. nomeia o CS da variante: no modo aberto, um nome que casa com um sinônimo
     *específico* do CS (dados/sinonimos.csv); no forçado, o item do CS marcado
     como presente;
  2. aponta para o que a variante injetou: um trecho num arquivo novo ou que
     cruza as linhas inseridas na CaixaController;
  3. não é a mesma da linha de base: o mesmo CS, no mesmo lugar, na resposta do
     mesmo modelo e modo à CaixaController sem injeção. "Mesmo lugar" é o mesmo
     intervalo de linhas, com TOLERANCIA linhas de folga nas pontas, depois de
     corrigir o deslocamento das linhas que vêm depois da injeção (3 linhas,
     confirmadas pelo autor em 03/10/2026). Assim, uma citação da classe
     inteira que a linha de base já fazia não conta, e uma citação das linhas
     injetadas conta.

Uma citação que satisfaz 2 e 3 com um nome *amplo* que cobre o CS da variante
(ex.: Large Class para Excessive Class Length) fica "a julgar" no julgamento
manual (L10). As outras citações entram só como contagem ("outros CS citados").

Julgamento manual (L10). Se julgamento/resultado.csv existe (gravado por
julgamento/apurar.py), o voto final de cada caso julgado entra no resultado:
  - nos "a julgar" e nas não detectadas com citação no código injetado, um
    "sim" conta como detecção, e um "não" num "a julgar" vira não detectada;
  - nas detecções da amostra, o voto só mede o casamento automático e não muda
    o resultado.
O resultado automático fica na coluna `automatico`, e o voto, em `julgamento`.
Um caso julgado cujo resultado automático não é o de agora para a análise: o
julgamento foi montado com outra análise. `--sem-julgamento` dá só o automático.

Uso, da raiz do repositório (só lê; não faz chamada nenhuma):

    uv run --no-project --with-requirements experimento/requirements.txt \\
        python experimento/analisar.py [--amostra piloto] [--saida PASTA] [--sem-julgamento]

Grava em PASTA (padrão: experimento/resultados/):
  - deteccoes-variantes.csv: uma linha por variante, modelo e modo, com o
    resultado (detectada, a_julgar, nao_detectada), o motivo, o resultado
    automático, o voto do julgamento e as contagens;
  - deteccoes-cs.csv: por CS, modelo e modo, quantas variantes foram
    detectadas (e quantas delas pelo julgamento) e o resumo (todas, algumas,
    nenhuma), como no artigo de ferramentas;
  - linha-de-base.csv: os CS do catálogo que cada modelo aponta na linha de base;
  - a-julgar.csv: as citações que vão para o julgamento manual (L10), pelo
    resultado automático.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import entradas as E  # noqa: E402
import harness as H  # noqa: E402
import prompts as P  # noqa: E402
import provedores as V  # noqa: E402
import sinonimos as S  # noqa: E402

TOLERANCIA = 3   # linhas de folga nas pontas para "o mesmo lugar" da linha de base (condição 3)
JULGAMENTO = Path(__file__).resolve().parent / "julgamento" / "resultado.csv"   # gravado por julgamento/apurar.py


# --------------------------------------------------------------------------
# Citações
# --------------------------------------------------------------------------

def citacoes(modo: str, resposta, catalogo: list[dict], sinonimos: list[dict]) -> list[dict]:
    """Cada citação: o nome dado, os CS que ele nomeia (específicos e amplos), os trechos e a
    justificativa (que o critério não usa; vai para a página do julgamento manual)."""
    if not isinstance(resposta, dict):
        return []
    lista = []
    if modo == "aberto":
        for s in resposta.get("smells") or []:
            casou = S.casar(str(s.get("nome") or ""), sinonimos)
            lista.append({"nome": s.get("nome"), "especifico": casou["especifico"],
                          "amplo": casou["amplo"] - casou["especifico"],
                          "trechos": [{"arquivo": s.get("arquivo"), "linha_inicio": s.get("linha_inicio"),
                                       "linha_fim": s.get("linha_fim")}],
                          "justificativa": s.get("justificativa")})
    else:
        for a in resposta.get("avaliacoes") or []:
            n = a.get("item")
            if a.get("presente") and isinstance(n, int) and 1 <= n <= len(catalogo):
                lista.append({"nome": f"item {n}: {catalogo[n - 1]['nome']}", "especifico": {catalogo[n - 1]["id"]},
                              "amplo": set(), "trechos": a.get("trechos") or [],
                              "justificativa": a.get("justificativa")})
    return lista


def _arquivo(nome, caminhos: list[str]) -> str | None:
    """O caminho da entrada a que o trecho se refere (igual, ou pelo nome do arquivo)."""
    if nome in caminhos:
        return nome
    base = Path(str(nome or "")).name
    achados = [c for c in caminhos if Path(c).name == base]
    return achados[0] if len(achados) == 1 else None


def _intervalo(t: dict) -> tuple[int, int] | None:
    ini, fim = t.get("linha_inicio"), t.get("linha_fim")
    if isinstance(ini, int) and isinstance(fim, int):
        return (min(ini, fim), max(ini, fim))
    return None


def no_injetado(t: dict, entrada: E.Entrada, injecoes: list[dict]) -> bool:
    """Condição 2: o trecho está num arquivo novo ou cruza as linhas inseridas."""
    arq = _arquivo(t.get("arquivo"), list(entrada.arquivos))
    if not arq:
        return False
    for inj in injecoes:
        if inj["arquivo"] != arq:
            continue
        if inj.get("novo"):
            return True
        faixa = _intervalo(t)
        if faixa and faixa[0] <= inj["fim"] and faixa[1] >= inj["inicio"]:
            return True
    return False


def mapear_base(faixa: tuple[int, int], injecoes: list[dict], arquivo: str) -> tuple[int, int]:
    """Uma faixa da linha de base em números de linha da variante (o que vem depois da injeção desce)."""
    def linha(n: int) -> int:
        for inj in injecoes:
            if inj["arquivo"] == arquivo and not inj.get("novo") and n >= inj["linha_fecha_base"]:
                n += inj["deslocamento"]
        return n
    return (linha(faixa[0]), linha(faixa[1]))


def igual_a_base(t: dict, cid: str, base_cits: list[dict], entrada: E.Entrada, injecoes: list[dict],
                 caminhos_base: list[str]) -> bool:
    """Condição 3 (negada): a linha de base cita o mesmo CS no mesmo lugar."""
    arq = _arquivo(t.get("arquivo"), list(entrada.arquivos))
    faixa = _intervalo(t)
    if not arq or not faixa or arq not in caminhos_base:
        return False          # arquivo novo: a linha de base não o tem
    for c in base_cits:
        if cid not in c["especifico"] | c["amplo"]:
            continue
        for b in c["trechos"]:
            if _arquivo(b.get("arquivo"), caminhos_base) != arq or not _intervalo(b):
                continue
            m = mapear_base(_intervalo(b), injecoes, arq)
            if abs(faixa[0] - m[0]) <= TOLERANCIA and abs(faixa[1] - m[1]) <= TOLERANCIA:
                return True
    return False


# --------------------------------------------------------------------------
# Análise
# --------------------------------------------------------------------------

def avaliar(entrada: E.Entrada, injecoes: list[dict], cits: list[dict], base_cits: list[dict],
            caminhos_base: list[str]) -> dict:
    cid = entrada.cs_id
    nomeou = [c for c in cits if cid in c["especifico"]]
    amplos = [c for c in cits if cid in c["amplo"]]

    def validas(lista):
        ok, so_base, fora = [], 0, 0
        for c in lista:
            boas = [t for t in c["trechos"] if no_injetado(t, entrada, injecoes)]
            if not boas:
                fora += 1
                continue
            novas = [t for t in boas if not igual_a_base(t, cid, base_cits, entrada, injecoes, caminhos_base)]
            if novas:
                ok.append(c)
            else:
                so_base += 1
        return ok, so_base, fora

    ok, so_base, fora = validas(nomeou)
    ok_amplo, _, _ = validas(amplos)
    if ok:
        resultado, motivo = "detectada", "nomeou o CS no código injetado"
    elif ok_amplo:
        resultado, motivo = "a_julgar", "só um nome amplo cobre o CS no código injetado"
    elif nomeou and so_base:
        resultado, motivo = "nao_detectada", "nomeou o CS no mesmo lugar que a linha de base"
    elif nomeou:
        resultado, motivo = "nao_detectada", "nomeou o CS fora do código injetado"
    else:
        resultado, motivo = "nao_detectada", "não nomeou o CS"
    outros = [c for c in cits if cid not in c["especifico"] | c["amplo"]]
    return {"resultado": resultado, "motivo": motivo, "citacoes": len(cits),
            "outros_citados": len(outros), "outros_do_catalogo": sum(1 for c in outros if c["especifico"]),
            "a_julgar": [c for c in ok_amplo] if resultado == "a_julgar" else []}


def julgamento(caminho: Path = JULGAMENTO) -> dict[tuple[str, str, str], dict]:
    """O voto final de cada caso julgado (L10), por (entrada, modelo, modo); {} se não há resultado.csv."""
    if not caminho.exists():
        return {}
    with open(caminho, encoding="utf-8") as f:
        return {(l["entrada"], l["modelo"], l["modo"]): l for l in csv.DictReader(f)}


class JulgamentoDeOutraAnalise(Exception):
    pass


def aplicar_julgamento(av: dict, caso: dict | None) -> dict:
    """O resultado final: o automático ou, se o caso foi julgado, o que o voto final determina."""
    automatico = av["resultado"]
    if caso is None:
        return {**av, "automatico": automatico, "julgamento": ""}
    if caso["automatico"] != automatico:
        raise JulgamentoDeOutraAnalise(
            f"julgamento/resultado.csv: o caso {caso['id']} ({caso['entrada']}, {caso['modelo']}, {caso['modo']}) "
            f"foi montado com o resultado automático {caso['automatico']!r}, mas a análise de agora dá "
            f"{automatico!r}: o julgamento é de outra análise")
    voto = caso["final"]
    resultado, motivo = automatico, av["motivo"]
    if caso["tipo"] in ("a_julgar", "nao_detectada") and voto == "sim":
        resultado, motivo = "detectada", "julgamento manual: a citação aponta o CS no código injetado"
    elif caso["tipo"] == "a_julgar":
        resultado, motivo = "nao_detectada", "julgamento manual: o nome amplo não descreve o CS"
    return {**av, "resultado": resultado, "motivo": motivo, "automatico": automatico, "julgamento": voto}


def analisar(args) -> dict:
    cfg, acesso, configurados = H.carregar_config()
    todas = E.montar()
    entradas, modelos, modos = H.selecionar(todas, configurados, args)
    injetado = {e.id: e.injetado for e in todas}
    catalogo = P.ordem_do_catalogo()
    sinonimos = S.carregar()
    base = next(e for e in todas if e.id == "base")
    caminhos_base = list(base.arquivos)
    julgados = {} if getattr(args, "sem_julgamento", False) else julgamento()

    variantes, linha_base, julgar, faltam = [], [], [], 0
    for m in modelos:
        rota = V.roteamento(acesso, m)
        for modo in modos:
            estado_b, rb = H.situacao(m, rota, modo, base, cfg["max_tokens"])
            base_cits = citacoes(modo, rb.get("resposta") if rb else None, catalogo, sinonimos)
            for c in base_cits:
                for cid in sorted(c["especifico"]):
                    linha_base.append({"modelo": m.nome, "modo": modo, "cs_id": cid, "nome": c["nome"],
                                       "trechos": "; ".join(f"{t.get('linha_inicio')}-{t.get('linha_fim')}"
                                                            for t in c["trechos"])})
            for e in entradas:
                if e.id == "base":
                    continue
                estado, r = H.situacao(m, rota, modo, e, cfg["max_tokens"])
                if estado != "valida" or rb is None or estado_b != "valida":
                    faltam += 1
                    continue
                cits = citacoes(modo, r.get("resposta"), catalogo, sinonimos)
                av = avaliar(e, injetado[e.id], cits, base_cits, caminhos_base)
                if not isinstance(r.get("resposta"), dict):   # JSON inválido conta como resposta do modelo
                    av["motivo"] = "resposta inválida (JSON incompleto ou malformado)"
                av = aplicar_julgamento(av, julgados.get((e.id, m.nome, modo)))
                variantes.append({"cs_id": e.cs_id, "variante": e.variante, "entrada": e.id, "tipo": e.tipo,
                                  "modelo": m.nome, "modo": modo, "resultado": av["resultado"],
                                  "motivo": av["motivo"], "automatico": av["automatico"],
                                  "julgamento": av["julgamento"], "citacoes": av["citacoes"],
                                  "outros_citados": av["outros_citados"],
                                  "outros_do_catalogo": av["outros_do_catalogo"],
                                  "json_valido": isinstance(r.get("resposta"), dict)})
                for c in av["a_julgar"]:
                    julgar.append({"entrada": e.id, "cs_id": e.cs_id, "modelo": m.nome, "modo": modo,
                                   "nome_dado": c["nome"], "cs_possiveis": ",".join(sorted(c["amplo"])),
                                   "trechos": "; ".join(f"{t.get('arquivo')}:{t.get('linha_inicio')}-{t.get('linha_fim')}"
                                                        for t in c["trechos"])})
    por_cs = {}
    for v in variantes:
        chave = (v["cs_id"], v["modelo"], v["modo"])
        x = por_cs.setdefault(chave, {"variantes": 0, "detectadas": 0, "a_julgar": 0, "pelo_julgamento": 0})
        x["variantes"] += 1
        x["detectadas"] += v["resultado"] == "detectada"
        x["a_julgar"] += v["resultado"] == "a_julgar"
        x["pelo_julgamento"] += v["resultado"] == "detectada" and v["automatico"] != "detectada"
    cs = []
    for (cid, nome_m, modo), x in sorted(por_cs.items()):
        resumo = ("todas" if x["detectadas"] == x["variantes"] else "algumas" if x["detectadas"] else "nenhuma")
        cs.append({"cs_id": cid, "modelo": nome_m, "modo": modo, "variantes": x["variantes"],
                   "detectadas": x["detectadas"], "a_julgar": x["a_julgar"],
                   "pelo_julgamento": x["pelo_julgamento"], "resultado": resumo})
    return {"variantes": variantes, "cs": cs, "linha_base": linha_base, "julgar": julgar, "faltam": faltam,
            "julgados": sum(1 for v in variantes if v["julgamento"])}


def gravar(caminho: Path, linhas: list[dict]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        if not linhas:
            f.write("")
            return
        w = csv.DictWriter(f, fieldnames=list(linhas[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(linhas)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--amostra", choices=["teste", "piloto"])
    p.add_argument("--modelo")
    p.add_argument("--modo", choices=P.MODOS)
    p.add_argument("--entrada", nargs="+")
    p.add_argument("--cs", nargs="+", help="só as variantes destes CS (ex.: C01 C05,C07 C11-C17)")
    p.add_argument("--saida", help="pasta dos CSV (padrão: experimento/resultados/)")
    p.add_argument("--sem-julgamento", action="store_true",
                   help="só o resultado automático, sem aplicar julgamento/resultado.csv")
    args = p.parse_args()
    try:
        res = analisar(args)
    except JulgamentoDeOutraAnalise as erro:
        print(erro)
        return 1
    pasta = Path(args.saida) if args.saida else E.RESULTADOS
    gravar(pasta / "deteccoes-variantes.csv", res["variantes"])
    gravar(pasta / "deteccoes-cs.csv", res["cs"])
    gravar(pasta / "linha-de-base.csv", res["linha_base"])
    gravar(pasta / "a-julgar.csv", res["julgar"])
    contagem = {}
    for v in res["variantes"]:
        contagem.setdefault((v["modelo"], v["modo"]), {}).setdefault(v["resultado"], 0)
        contagem[v["modelo"], v["modo"]][v["resultado"]] += 1
    for (nome_m, modo), c in contagem.items():
        print(f"  {nome_m:9s} {modo:8s} detectadas {c.get('detectada', 0):3d}  a julgar {c.get('a_julgar', 0):3d}  "
              f"não detectadas {c.get('nao_detectada', 0):3d}")
    if res["faltam"]:
        print(f"  {res['faltam']} combinação(ões) sem resposta válida (ou sem a linha de base) ficaram de fora")
    if res["julgados"]:
        mudaram = [v for v in res["variantes"] if v["julgamento"] and v["resultado"] != v["automatico"]]
        print(f"  julgamento manual aplicado a {res['julgados']} combinação(ões): {len(mudaram)} mudaram de resultado "
              f"({sum(v['resultado'] == 'detectada' for v in mudaram)} passaram a detectadas)")
    elif not getattr(args, "sem_julgamento", False) and not JULGAMENTO.exists():
        print("  sem julgamento manual (julgamento/resultado.csv não existe): resultado só automático")
    try:
        mostrar = pasta.resolve().relative_to(E.RAIZ)
    except ValueError:
        mostrar = pasta
    print(f"CSV em {mostrar}/; nenhuma chamada foi feita.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
