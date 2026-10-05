"""Extrai, de cada uma das 89 variantes, o texto que um modelo leria (item L4).

Considera a opção (a) da D11: as variantes do tipo `membros` chegam dentro da
CaixaController (só o que está entre as chaves da classe Fragmento é inserido;
o docblock da Fragmento fica de fora) e as do tipo `arquivos`, como arquivos
novos com o caminho. Para cada arquivo, lista os comentários (sem repetição,
com a primeira linha em que aparecem) e os nomes declarados; as views Blade são
lidas inteiras na auditoria, porque não têm comentários.

Grava experimento/auditoria/texto-lido.txt (fora do git), a leitura que
sustenta experimento/neutralizacao.csv.

    python3 experimento/auditoria/extrair.py

Precisa do PHP no PATH (o tokenizador do PHP separa comentários, nomes e
strings) e das variantes: as do caminho da variável de ambiente EXEMPLOS, a
cópia do pacote de replicação (experimento/exemplos/) ou as que o
`harness.py preparar` baixa (experimento/trabalho/exemplos/), nesta ordem.
"""

import csv
import json
import os
import re
import subprocess
from pathlib import Path

AQUI = Path(__file__).resolve().parent
EXEMPLOS = Path(os.environ.get("EXEMPLOS") or next(
    (p for p in (AQUI.parent / "exemplos", AQUI.parent / "trabalho" / "exemplos") if p.is_dir()),
    AQUI.parent / "trabalho" / "exemplos"))
CONTROLADOR = "app/Http/Controllers/Admin/CaixaController.php"


def tokens(arquivo):
    saida = subprocess.run(["php", str(AQUI / "tokens.php"), str(arquivo)],
                           capture_output=True, text=True, check=True).stdout
    return json.loads(saida)


def corpo_do_fragmento(arquivo):
    """Linhas (1-based, exclusivas) entre a chave que abre e a que fecha a classe Fragmento."""
    linhas = arquivo.read_text(encoding="utf-8").splitlines()
    inicio = next(n for n, l in enumerate(linhas) if re.match(r"\s*class Fragmento\b", l))
    abre = next(n for n in range(inicio, len(linhas)) if "{" in linhas[n])
    fecha = max(n for n, l in enumerate(linhas) if l.strip() == "}")
    return abre + 1, fecha + 1


def lido(arquivo, faixa=None):
    comentarios, declarados = {}, []
    for t in tokens(arquivo):
        if faixa and not faixa[0] < t["linha"] < faixa[1]:
            continue
        if t["tipo"] in ("T_COMMENT", "T_DOC_COMMENT"):
            texto = re.sub(r"\s+", " ", re.sub(r"\s*\n\s*\*?\s*", " | ", t["texto"].strip()))
            comentarios.setdefault(texto, t["linha"])
        elif t["tipo"] == "T_STRING" and t["decl"]:
            declarados.append(f"{t['decl'].removeprefix('T_').lower()} {t['texto']}")
    return comentarios, declarados


saida = []
for v in csv.DictReader(open(EXEMPLOS / "variantes.csv", encoding="utf-8")):
    pasta = next(EXEMPLOS.glob(f"{v['cs_id']}-*/{v['variante']}"))
    saida.append(f"\n##### {v['cs_id']}-{v['variante']} [{v['tipo']}] {v['forma']}")
    for arquivo in sorted(p for p in pasta.rglob("*") if p.is_file()):
        relativo = arquivo.relative_to(pasta).as_posix()
        if relativo == "membros.php":
            faixa = corpo_do_fragmento(arquivo)
            caminho, linhas = f"{CONTROLADOR} (membros inseridos)", faixa[1] - faixa[0] - 1
        else:
            faixa = None
            caminho = relativo.removeprefix("arquivos/")
            linhas = arquivo.read_text(encoding="utf-8").count("\n") + 1
        saida.append(f"  -- {caminho} ({linhas} l.)")
        if caminho.endswith(".blade.php"):
            saida.append("    (view Blade: ler o arquivo inteiro)")
            continue
        comentarios, declarados = lido(arquivo, faixa)
        saida += [f"    {ln}: {c}" for c, ln in comentarios.items()]
        if declarados:
            saida.append("    declara: " + ", ".join(declarados))

(AQUI / "texto-lido.txt").write_text("\n".join(saida) + "\n", encoding="utf-8")
print(f"experimento/auditoria/texto-lido.txt ({len(saida)} linhas)")
