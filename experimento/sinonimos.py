"""Casamento entre os nomes que os modelos dão aos CS e o catálogo (itens L6 e D4).

A lista fica em dados/sinonimos.csv, uma linha por sinônimo (cs_id, sinonimo,
origem, tipo), fixada antes da execução completa. Um nome de resposta casa com
um sinônimo quando contém as palavras dele, na mesma ordem e com no máximo uma
palavra entre duas delas, depois de normalizar os dois do mesmo jeito. Se casar
com sinônimos específicos de dois CS e um contiver o outro, vale o mais longo.

- tipo "especifico": nomeia aquele CS (o nome do catálogo, os nomes usados pelos
  estudos da RSL, os nomes de regra das ferramentas, as formas usuais na
  literatura e em português). O casamento conta como detecção, se o trecho
  apontado for o injetado (D4).
- tipo "amplo": nome genérico que pode cobrir vários CS (ex.: God Class, código
  morto, estilo de código). O casamento não decide sozinho: vai para o
  julgamento manual (L10).

Normalização (simétrica, aplicada aos sinônimos e às respostas): camelCase
separado em palavras; minúsculas; sem acentos; o que não é letra ou dígito vira
espaço; plural em "s" e final "a" unificados ("variáveis não utilizadas" e
"variável não utilizada" ficam iguais); "utilizado", "usado" e flexões viram
"usado". Como a separação do camelCase depende da capitalização ("JavaScript"
vira "java script", e "javascript" fica inteiro), o casamento compara também
as duas formas sem separar o camelCase; casa se qualquer uma das comparações
casar. A comparação sem separar entrou em 05/10/2026, durante a execução
completa (decisão do autor): sem ela, os sinônimos em minúsculas com
"javascript" não casavam com respostas que escreviam "JavaScript".
"""

from __future__ import annotations

import csv
import re
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
LISTA = RAIZ / "dados" / "sinonimos.csv"
PARTICIPIOS = {"utilizado", "utilizada", "usado", "usada", "utilizavel"}


def _palavra(p: str) -> str:
    if len(p) > 3 and p.endswith("s") and not p.endswith("ss"):
        p = p[:-1]
    if p.endswith("ei") and len(p) > 4:          # "variáveis" -> "variavei" -> "variavel"
        p = p[:-2] + "el"
    if len(p) > 3 and p.endswith("a"):
        p = p[:-1] + "o"
    return "usado" if p in PARTICIPIOS else p


def normalizar(texto: str, separar: bool = True) -> tuple[str, ...]:
    """As palavras normalizadas; com separar=False, o camelCase não é separado."""
    if separar:
        texto = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", texto)
        texto = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", texto)
    texto = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn").lower()
    texto = "".join(c if c.isalnum() else " " for c in texto)
    return tuple(_palavra(p) for p in texto.split())


FOLGA = 1  # palavras que podem aparecer entre duas palavras do sinônimo ("tag HTML não fechada")


def contem(nome: tuple[str, ...], sinonimo: tuple[str, ...]) -> bool:
    """As palavras do sinônimo aparecem no nome, na mesma ordem, com no máximo
    FOLGA palavras entre uma e a seguinte."""
    def a_partir(i: int, j: int) -> bool:
        if j == len(sinonimo):
            return True
        limite = len(nome) if j == 0 else min(len(nome), i + FOLGA + 1)
        return any(nome[k] == sinonimo[j] and a_partir(k + 1, j + 1) for k in range(i, limite))
    return bool(sinonimo) and a_partir(0, 0)


def carregar(caminho: Path = LISTA) -> list[dict]:
    with open(caminho, encoding="utf-8") as f:
        linhas = list(csv.DictReader(f))
    for l in linhas:
        l["palavras"] = normalizar(l["sinonimo"])
        l["unidas"] = normalizar(l["sinonimo"], separar=False)
    return linhas


def casar(nome: str, lista: list[dict]) -> dict[str, set[str]]:
    """Os CS com que o nome casa, separados por tipo do sinônimo.

    Entre os específicos, vale o mais específico: se o sinônimo que casou para
    um CS está contido no que casou para outro ("too many methods" em "too many
    public methods"), fica só o outro."""
    palavras, unidas = normalizar(nome), normalizar(nome, separar=False)
    casou = {"especifico": set(), "amplo": set()}
    especificos = []
    for l in lista:
        if (l["palavras"] and contem(palavras, l["palavras"])) or (l["unidas"] and contem(unidas, l["unidas"])):
            if l["tipo"] == "especifico":
                especificos.append(l)
            else:
                casou["amplo"].add(l["cs_id"])
    def contido(l, o):   # o sinônimo l está dentro do o, mais longo, em alguma das duas formas
        return ((len(o["palavras"]) > len(l["palavras"]) and contem(o["palavras"], l["palavras"]))
                or (len(o["unidas"]) > len(l["unidas"]) and contem(o["unidas"], l["unidas"])))
    for l in especificos:
        if not any(o["cs_id"] != l["cs_id"] and contido(l, o) for o in especificos):
            casou["especifico"].add(l["cs_id"])
    return casou


def conferir(lista: list[dict], catalogo: list[dict]) -> list[str]:
    """Problemas na lista: CS sem sinônimo, id ou tipo inválido, sinônimo vazio
    depois de normalizar, nome do catálogo que não casa com o próprio CS."""
    ids = {c["id"] for c in catalogo}
    problemas = []
    for l in lista:
        if l["cs_id"] not in ids:
            problemas.append(f"cs_id inválido: {l['cs_id']} ({l['sinonimo']})")
        if l["tipo"] not in ("especifico", "amplo"):
            problemas.append(f"tipo inválido: {l['tipo']} ({l['sinonimo']})")
        if not l["palavras"]:
            problemas.append(f"sinônimo vazio depois de normalizar: {l['sinonimo']!r}")
    for c in catalogo:
        if not any(l["cs_id"] == c["id"] and l["tipo"] == "especifico" for l in lista):
            problemas.append(f"{c['id']} sem sinônimo específico")
        if c["id"] not in casar(c["nome"], lista)["especifico"]:
            problemas.append(f"o nome do catálogo de {c['id']} ({c['nome']}) não casa com ele")
    return problemas
