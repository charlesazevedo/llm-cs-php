"""Prompts e esquemas de resposta dos dois modos (decisão D12).

- aberto: o modelo lista os CS que encontrar, sem receber o catálogo; é o uso
  de quem pergunta sem saber o que procurar.
- forcado: o modelo recebe o catálogo dos 38 CS, com as descrições da RSL, numa
  ordem sorteada (semente fixa, a mesma para todos os modelos e entradas), e diz
  quais estão presentes. Os itens são numerados nessa ordem, não pelos ids
  C01–C38, que o código das variantes poderia sugerir.

O texto é o mesmo para todos os provedores, inclusive a instrução de formato:
a DeepSeek só garante JSON válido (sem esquema), então o formato precisa estar
no prompt para todos. O prompt de sistema é neutro e igual para todos.
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SEMENTE_CATALOGO = 20261001
MODOS = ("aberto", "forcado")

SISTEMA = "Você analisa código-fonte e responde somente com o JSON pedido."

INTRODUCAO = (
    "A seguir está o código de uma aplicação web em PHP (Laravel): {quantos}. "
    "Cada arquivo começa com uma linha \"=== arquivo: <caminho> ===\", e as linhas estão numeradas."
)

ABERTO = INTRODUCAO + """

Faça uma verificação completa neste código para localizar se existe algum code smell em seu conteúdo e monte uma lista de todos os code smells encontrados. Para cada code smell, informe o nome, o arquivo, o intervalo de linhas e uma justificativa de uma frase. Se o mesmo code smell aparecer em trechos diferentes, liste cada trecho. Se não encontrar nenhum, devolva uma lista vazia.

Responda em JSON, exatamente neste formato:
{{"smells": [{{"nome": "...", "arquivo": "...", "linha_inicio": 1, "linha_fim": 9, "justificativa": "..."}}]}}

Informe o intervalo de linhas (linha_inicio e linha_fim), nunca uma lista linha por linha.

Código:

{codigo}"""

FORCADO = INTRODUCAO + """

Abaixo há um catálogo numerado de code smells, com a descrição de cada um. Para CADA item do catálogo, informe se ele está presente neste código.

Catálogo:
{catalogo}

Responda em JSON, exatamente neste formato, com um objeto para cada um dos {n} itens do catálogo:
{{"avaliacoes": [{{"item": 1, "presente": true, "trechos": [{{"arquivo": "...", "linha_inicio": 1, "linha_fim": 9}}], "justificativa": "..."}}]}}

Para os itens ausentes, use "presente": false, "trechos": [] e "justificativa": "". Para os presentes, informe todos os trechos em que o item ocorre, cada um com o arquivo e o intervalo de linhas (nunca uma lista linha por linha).

Código:

{codigo}"""

_TRECHO = {
    "type": "object",
    "properties": {"arquivo": {"type": "string"}, "linha_inicio": {"type": "integer"},
                   "linha_fim": {"type": "integer"}},
    "required": ["arquivo", "linha_inicio", "linha_fim"],
    "additionalProperties": False,
}

ESQUEMAS = {
    "aberto": {
        "type": "object",
        "properties": {"smells": {"type": "array", "items": {
            "type": "object",
            "properties": {"nome": {"type": "string"}, "arquivo": {"type": "string"},
                           "linha_inicio": {"type": "integer"}, "linha_fim": {"type": "integer"},
                           "justificativa": {"type": "string"}},
            "required": ["nome", "arquivo", "linha_inicio", "linha_fim", "justificativa"],
            "additionalProperties": False,
        }}},
        "required": ["smells"],
        "additionalProperties": False,
    },
    "forcado": {
        "type": "object",
        "properties": {"avaliacoes": {"type": "array", "items": {
            "type": "object",
            "properties": {"item": {"type": "integer"}, "presente": {"type": "boolean"},
                           "trechos": {"type": "array", "items": _TRECHO},
                           "justificativa": {"type": "string"}},
            "required": ["item", "presente", "trechos", "justificativa"],
            "additionalProperties": False,
        }}},
        "required": ["avaliacoes"],
        "additionalProperties": False,
    },
}


def ordem_do_catalogo() -> list[dict]:
    """Os 38 CS de dados/cs-experimento.csv na ordem sorteada; o item n é ordem[n - 1]."""
    with open(RAIZ / "dados" / "cs-experimento.csv", encoding="utf-8") as f:
        catalogo = list(csv.DictReader(f))
    random.Random(SEMENTE_CATALOGO).shuffle(catalogo)
    return catalogo


def texto_do_catalogo() -> str:
    return "\n".join(f"{i}. {c['nome']}: {c['descricao']}" for i, c in enumerate(ordem_do_catalogo(), 1))


def montar(modo: str, codigo: str, n_arquivos: int) -> str:
    quantos = "um arquivo" if n_arquivos == 1 else f"{n_arquivos} arquivos"
    if modo == "aberto":
        return ABERTO.format(quantos=quantos, codigo=codigo)
    return FORCADO.format(quantos=quantos, catalogo=texto_do_catalogo(), n=len(ordem_do_catalogo()), codigo=codigo)


def hash_condicao(modo: str) -> str:
    """Identifica a condição experimental: sistema, modelo de prompt, esquema e catálogo.
    Mudou qualquer um, as respostas antigas deixam de valer."""
    h = hashlib.sha256()
    h.update(modo.encode())
    h.update(SISTEMA.encode())
    h.update((ABERTO if modo == "aberto" else FORCADO).encode())
    h.update(json.dumps(ESQUEMAS[modo], sort_keys=True).encode())
    if modo == "forcado":
        h.update(texto_do_catalogo().encode())
    return h.hexdigest()[:16]
