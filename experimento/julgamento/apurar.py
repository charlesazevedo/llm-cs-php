#!/usr/bin/env python3
"""Apura o julgamento manual (L10): concordância entre os juízes e o resultado final.

Os juízes são o primeiro autor e um desenvolvedor convidado, identificados só
como juiz-1 e juiz-2 (decisão do autor, 05/10/2026).

Passos:
  1. Cada juiz julga na página (julgamento.html) e baixa votos-juiz-1.csv ou
     votos-juiz-2.csv, que vai para esta pasta.
  2. `apurar.py` calcula o kappa de Cohen entre os dois juízes, sobre todos os
     casos, e grava divergencias.csv com os casos em que os votos diferem ou em
     que algum juiz votou "dúvida".
  3. Os juízes discutem as divergências e preenchem a coluna `consenso` (sim ou
     nao) de divergencias.csv, que salvam como consenso.csv. Num caso em que não
     cheguem a acordo, o segundo autor (o orientador) decide, e a coluna
     `decidido_por` passa de `consenso` a `segundo_autor`.
  4. `apurar.py` de novo junta tudo em resultado.csv (a chave, os votos e o voto
     final de cada caso). Nos "a julgar" e nas não detectadas, um voto final
     "sim" passa a contar como detecção; nas detecções da amostra e nas não
     detectadas, ele mede quanto o casamento automático concorda com o
     julgamento humano.

Uso, da raiz do repositório (só lê os CSV; não faz chamada nenhuma):

    python3 experimento/julgamento/apurar.py [--pasta PASTA] [votos-A.csv votos-B.csv]

Sem arquivos, usa os votos-*.csv da pasta (precisam ser exatamente dois). A pasta
padrão é experimento/julgamento/, onde estão a chave e onde saem os CSV.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

AQUI = Path(__file__).resolve().parent
CATEGORIAS = ("sim", "nao", "duvida")


def ler(caminho: Path) -> list[dict]:
    with open(caminho, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def gravar(caminho: Path, linhas: list[dict]) -> None:
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(linhas)


def kappa(pares: list[tuple[str, str]], categorias=CATEGORIAS) -> float | None:
    """Kappa de Cohen entre dois avaliadores (None se não há pares ou a concordância esperada é 1)."""
    n = len(pares)
    if not n:
        return None
    po = sum(1 for a, b in pares if a == b) / n
    ma, mb = Counter(a for a, _ in pares), Counter(b for _, b in pares)
    pe = sum(ma[c] * mb[c] for c in categorias) / (n * n)
    return None if pe == 1 else (po - pe) / (1 - pe)


def fmt(k: float | None) -> str:
    return "indefinido" if k is None else f"{k:.2f}".replace(".", ",")


def main() -> int:
    global AQUI
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--pasta", help="pasta com a chave e os votos (padrão: experimento/julgamento/)")
    p.add_argument("votos", nargs="*", help="os dois arquivos de votos")
    args = p.parse_args()
    if args.pasta:
        AQUI = Path(args.pasta)
    arquivos = [Path(a) for a in args.votos] or sorted(AQUI.glob("votos-*.csv"))
    if len(arquivos) != 2:
        print(f"preciso de exatamente dois arquivos de votos; achei {len(arquivos)}: {[a.name for a in arquivos]}")
        return 1
    chave = {c["id"]: c for c in ler(AQUI / "chave.csv")}
    juizes, votos = [], []
    for a in arquivos:
        linhas = ler(a)
        juizes.append(linhas[0]["juiz"] if linhas else a.stem)
        votos.append({l["id"]: l for l in linhas})
    faltam = {j: sorted(i for i in chave if not v.get(i, {}).get("voto")) for j, v in zip(juizes, votos)}
    for j, f in faltam.items():
        if f:
            print(f"{j}: {len(f)} caso(s) sem voto: {', '.join(f)}")
    if any(faltam.values()):
        print("Complete os votos antes de apurar.")
        return 1

    ids = sorted(chave)
    pares = [(votos[0][i]["voto"], votos[1][i]["voto"]) for i in ids]
    print(f"{len(ids)} casos; juízes {juizes[0]} e {juizes[1]}")
    print(f"concordância simples: {sum(a == b for a, b in pares)} de {len(ids)}; kappa de Cohen: {fmt(kappa(pares))}")

    divergentes = [i for i, (a, b) in zip(ids, pares) if a != b or "duvida" in (a, b)]
    consenso = {}
    decidido_por = {}
    if (AQUI / "consenso.csv").exists():
        linhas_consenso = ler(AQUI / "consenso.csv")
        # O consenso tem de ser destes votos: mesmos casos divergentes e os mesmos votos de cada juiz.
        # Um consenso.csv de uma apuração anterior (com outro arquivo de votos) não pode ser reaplicado.
        outro = {l["id"] for l in linhas_consenso} != set(divergentes) or any(
            l.get(f"voto_{j}") != v[l["id"]]["voto"] for l in linhas_consenso
            for j, v in zip(juizes, votos) if l["id"] in v)
        if outro:
            print("consenso.csv é de outra apuração: os casos divergentes ou os votos mudaram. Tire-o da pasta "
                  "(com o divergencias.csv e o resultado.csv antigos) e rode de novo, para gerar as divergências "
                  "destes votos.")
            return 1
        consenso = {l["id"]: l["consenso"].strip().lower() for l in linhas_consenso}
        decidido_por = {l["id"]: (l.get("decidido_por") or "consenso").strip().lower() for l in linhas_consenso}
    elif divergentes:
        gravar(AQUI / "divergencias.csv", [{
            "id": i, f"voto_{juizes[0]}": votos[0][i]["voto"], f"voto_{juizes[1]}": votos[1][i]["voto"],
            f"comentario_{juizes[0]}": votos[0][i].get("comentario", ""),
            f"comentario_{juizes[1]}": votos[1][i].get("comentario", ""), "consenso": "",
            "decidido_por": "consenso"} for i in divergentes])
        print(f"{len(divergentes)} caso(s) para discutir em divergencias.csv: preencham a coluna consenso (sim ou "
              "nao; decidido_por = segundo_autor onde não houver acordo), salvem o arquivo como consenso.csv e rodem "
              "de novo.")
        return 0
    sem_consenso = [i for i in divergentes if consenso.get(i) not in ("sim", "nao")]
    if sem_consenso:
        print(f"falta o consenso (sim ou nao) de {len(sem_consenso)} caso(s) em consenso.csv: {', '.join(sem_consenso)}")
        return 1

    final = {i: (consenso[i] if i in divergentes else votos[0][i]["voto"]) for i in ids}
    resultado = [{**chave[i], f"voto_{juizes[0]}": votos[0][i]["voto"], f"voto_{juizes[1]}": votos[1][i]["voto"],
                  "final": final[i], "decidido_por": decidido_por.get(i, "consenso") if i in divergentes else "juizes"}
                 for i in ids]
    gravar(AQUI / "resultado.csv", resultado)
    pelo_segundo = sum(r["decidido_por"] == "segundo_autor" for r in resultado)
    print(f"divergências: {len(divergentes)}, decididas por consenso {len(divergentes) - pelo_segundo} "
          f"e pelo segundo autor {pelo_segundo}")

    for tipo, rotulo in (("a_julgar", "a julgar"), ("nao_detectada", "não detectadas com citação no código injetado")):
        grupo = [r for r in resultado if r["tipo"] == tipo]
        if grupo:
            print(f"{rotulo}: {sum(r['final'] == 'sim' for r in grupo)} de {len(grupo)} passam a contar como detecção")
    # Concordância entre o casamento automático e o julgamento: nas detecções da amostra e em todas as
    # não detecções julgadas (os "a julgar" ficam de fora: o automático não os decide).
    decididos = [r for r in resultado if r["tipo"] in ("amostra_detectada", "nao_detectada")]
    if decididos:
        auto = [("sim" if r["automatico"] == "detectada" else "nao", r["final"]) for r in decididos]
        amostra = [r for r in decididos if r["tipo"] == "amostra_detectada"]
        print(f"detecções da amostra confirmadas pelo julgamento: {sum(r['final'] == 'sim' for r in amostra)} de "
              f"{len(amostra)}")
        print(f"casamento automático × julgamento: concordam em {sum(a == b for a, b in auto)} de {len(auto)} casos; "
              f"kappa: {fmt(kappa(auto, ('sim', 'nao')))}")
        for r in amostra:
            if r["final"] != "sim":
                print(f"  {r['id']}: detecção automática não confirmada ({r['entrada']}, {r['modelo']}, {r['modo']})")
    print("resultado.csv gravado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
