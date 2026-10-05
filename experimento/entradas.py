"""Fontes, neutralização e montagem das 90 entradas do experimento (item L5).

Uma entrada é o que um modelo recebe numa chamada (decisão D11, opção a): os
arquivos que a variante toca, cada um com o caminho e as linhas numeradas. A
linha de base ("base") é a CaixaController original.

Fontes, conferidas por SHA-256 antes de qualquer uso:
- a CaixaController do PDVLaravel no commit 98cddb8, a mesma que as ferramentas
  analisaram (o PDVLaravel não declara licença, então o arquivo fica em
  trabalho/, fora do git);
- as 89 variantes do artigo de ferramentas, na release v1.0 do tools-cs-php,
  conferidas contra experimento/exemplos.sha256. No pacote de replicação, elas
  vêm copiadas em experimento/exemplos/ (MIT; decisão do autor, F3) e não são
  baixadas.

As variantes são aplicadas como no executar.py do artigo de ferramentas, depois
da neutralização da L4 (experimento/neutralizacao.csv), que tira o que entregaria
o CS ou o experimento a um modelo sem mudar o código que as ferramentas viram.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import shutil
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

BASE = Path(__file__).resolve().parent
RAIZ = BASE.parent
TRABALHO = BASE / "trabalho"
RESULTADOS = BASE / "resultados"

CONTROLLER = "app/Http/Controllers/Admin/CaixaController.php"
PDVLARAVEL_COMMIT = "98cddb84521765c29ff7ed691d7f5ba325cc7edc"
URL_CONTROLLER = f"https://raw.githubusercontent.com/Lucasczm/PDVLaravel/{PDVLARAVEL_COMMIT}/{CONTROLLER}"
SHA_CONTROLLER = "c7fd39edb41ff9c71b4bb7afff5ee815b74c76440a96709ae338be82c3c4dd31"
VARIANTES_RELEASE = "v1.0"  # tag do tools-cs-php (commit 628c62c)
URL_VARIANTES = f"https://github.com/charlesazevedo/tools-cs-php/archive/refs/tags/{VARIANTES_RELEASE}.zip"
MANIFESTO = BASE / "exemplos.sha256"
EXEMPLOS_PACOTE = BASE / "exemplos"   # só existe no pacote de replicação (F3)


def sha256(dados: bytes | str) -> str:
    if isinstance(dados, str):
        dados = dados.encode("utf-8")
    return hashlib.sha256(dados).hexdigest()


# --------------------------------------------------------------------------
# Fontes
# --------------------------------------------------------------------------

def obter_controller() -> Path:
    """Baixa a CaixaController original (ou copia de PDVLARAVEL_BASE) e confere o SHA-256."""
    destino = TRABALHO / "base" / "CaixaController.php"
    if not destino.exists():
        destino.parent.mkdir(parents=True, exist_ok=True)
        local = os.environ.get("PDVLARAVEL_BASE")
        if local:
            shutil.copy2(Path(local) / CONTROLLER, destino)
        else:
            with urllib.request.urlopen(URL_CONTROLLER, timeout=60) as r:
                destino.write_bytes(r.read())
    obtido = sha256(destino.read_bytes())
    if obtido != SHA_CONTROLLER:
        raise SystemExit(f"CaixaController com SHA-256 inesperado ({obtido}); apague {destino} e rode de novo")
    return destino


def obter_variantes() -> Path:
    """Baixa as variantes da release v1.0 do tools-cs-php (ou copia de EXEMPLOS, ou da cópia
    do pacote de replicação) e confere o manifesto."""
    destino = TRABALHO / "exemplos"
    if not destino.exists():
        local = os.environ.get("EXEMPLOS") or (EXEMPLOS_PACOTE if EXEMPLOS_PACOTE.is_dir() else None)
        if local:
            shutil.copytree(local, destino, ignore=shutil.ignore_patterns("__pycache__", "gerar", "validar.py"))
        else:
            with urllib.request.urlopen(URL_VARIANTES, timeout=120) as r:
                pacote = zipfile.ZipFile(io.BytesIO(r.read()))
            prefixo = next(n for n in pacote.namelist() if n.endswith("/experimento/exemplos/"))
            for nome in pacote.namelist():
                if nome.startswith(prefixo) and not nome.endswith("/"):
                    rel = nome[len(prefixo):]
                    if rel.startswith("gerar/") or rel == "validar.py":
                        continue
                    alvo = destino / rel
                    alvo.parent.mkdir(parents=True, exist_ok=True)
                    alvo.write_bytes(pacote.read(nome))
    esperado = {}
    for linha in MANIFESTO.read_text(encoding="utf-8").splitlines():
        h, rel = linha.split(maxsplit=1)
        esperado[rel] = h
    presentes = {p.relative_to(destino).as_posix() for p in destino.rglob("*") if p.is_file()}
    falhas = sorted(set(esperado) ^ presentes)
    falhas += [rel for rel in esperado if rel in presentes and sha256((destino / rel).read_bytes()) != esperado[rel]]
    if falhas:
        raise SystemExit(f"variantes diferentes do manifesto ({len(falhas)} arquivo(s), ex.: {falhas[:3]}); "
                         f"apague {destino} e rode de novo")
    return destino


# --------------------------------------------------------------------------
# Neutralização (L4, validada pelo autor). Cada regra cita o id de
# experimento/neutralizacao.csv e diz quantas vezes tem de se aplicar; se não
# se aplicar o número esperado de vezes, a montagem para.
# --------------------------------------------------------------------------

@dataclass
class Regra:
    id: str
    variantes: tuple[str, ...]        # ("*",) = toda variante com o tipo de arquivo da regra
    de: str
    para: str
    alvo: str = "conteudo"           # "conteudo" ou "caminho"
    regex: bool = False
    vezes: int | None = None         # ocorrências esperadas por arquivo afetado (None = ao menos uma)
    arquivo: str | None = None       # nome exato do arquivo de origem afetado


REGRAS = [
    # N01/N02: namespace e caminho das classes novas.
    Regra("N01", ("*",), r"App\\Experimento\\C\d{2}\\V\d", r"App\\Pdv", regex=True),
    Regra("N02", ("*",), r"^app/Experimento/C\d{2}/V\d/", "app/Pdv/", alvo="caminho", regex=True),
    # N03/N04: views na pasta das views do projeto, sem o prefixo cxx-vn-.
    Regra("N03", ("*",), r"^resources/views/experimento/c\d{2}-v\d-(.+)$", r"resources/views/admin/caixa/\1",
          alvo="caminho", regex=True),
    Regra("N03", ("*",), r"experimento\.c\d{2}-v\d-([\w-]+)", r"admin.caixa.\1", regex=True, vezes=None),
    Regra("N04", ("C09-v1",), "resources/views/admin/caixa/sangria.blade.php",
          "resources/views/admin/caixa/nova-sangria.blade.php", alvo="caminho"),
    Regra("N04", ("C09-v1",), "resources/views/admin/caixa/entrada.blade.php",
          "resources/views/admin/caixa/nova-entrada.blade.php", alvo="caminho"),
    # N05–N09: C03, o docblock declara o privilégio que cada rotina exige.
    Regra("N05", ("C03-v1",), "Registra uma sangria no caixa; exige o privilégio caixa.sangria.",
          "Registra uma sangria no caixa.", vezes=1),
    Regra("N06", ("C03-v1",), "Confere o saldo contado com o saldo do sistema; exige o privilégio caixa.visualizar.",
          "Confere o saldo contado com o saldo do sistema.", vezes=1),
    Regra("N07", ("C03-v1",), "registrarSangriaAutorizada", "registrarSangriaManual"),
    Regra("N08", ("C03-v2",), "Exclui uma entrada de caixa; exige o privilégio caixa.excluir.",
          "Exclui uma entrada de caixa.", vezes=1),
    Regra("N09", ("C03-v2",), "Exibe uma entrada de caixa; exige o privilégio caixa.visualizar.",
          "Exibe uma entrada de caixa.", vezes=1),
    # N10/N11: C04-v1, o docblock enuncia o CS.
    Regra("N10", ("C04-v1",), "Registra no Gate os privilégios de exclusão do PDV, um para cada componente.",
          "Registra no Gate os privilégios de exclusão do PDV.", vezes=1),
    Regra("N11", ("C04-v1",),
          " *\n * Os quatro privilégios têm a mesma semântica (excluir registros, permitido só\n"
          " * aos gerentes), mas são definidos separadamente para caixa, vendas, estoque e\n"
          " * clientes.\n", "", vezes=1),
    # N13–N15: C08, os docblocks dizem que o HTML é montado em partes ou que o script fica em outra classe.
    Regra("N13", ("C08-v1",),
          " *\n * A abertura da tabela, as linhas e o fechamento (com o total) são produzidos\n"
          " * por métodos diferentes e só formam um elemento <table> completo depois de\n"
          " * concatenados em renderizar().\n", "", vezes=1),
    Regra("N14", ("C08-v2",),
          " *\n * O comportamento do formulário (atualizar o saldo restante enquanto o valor é\n"
          " * digitado) fica em outra classe, ScriptDoFormularioDeSangria, que depende dos\n"
          " * ids dos elementos gerados aqui.\n", "", vezes=1, arquivo="FormularioDeSangria.php"),
    Regra("N15", ("C08-v2",),
          " *\n * O script manipula os elementos valor-sangria e saldo-restante, que são\n"
          " * gerados por FormularioDeSangria.\n", "", vezes=1, arquivo="ScriptDoFormularioDeSangria.php"),
    # N16/N17: C17, "públicos" e o nome da classe apontam para o CS.
    Regra("N16", ("C17-v1", "C17-v2"), "Painel do caixa com indicadores públicos, carregados sob demanda, por grupo.",
          "Painel do caixa com indicadores carregados sob demanda, por grupo.", vezes=1),
    Regra("N17", ("C17-v1", "C17-v2"), "PainelPublicoDoCaixa", "PainelDoCaixa"),
    Regra("N17", ("C17-v1", "C17-v2"), "PainelPublicoDoCaixa.php", "PainelDoCaixa.php", alvo="caminho"),
]
# Mantidos de propósito (neutralizacao.csv): N12 (C04-v2), N18 (C29-v2), N19 (C22).
MANTIDOS = ("N12", "N18", "N19")

# O que não pode sobrar em nenhuma entrada depois da neutralização.
VAZAMENTO = re.compile(r"experimento|fragmento|variante|\bC\d{2}\b|\bc\d{2}-v\d", re.IGNORECASE)


def aplicar_regras(entrada_id: str, caminho_origem: str, caminho: str, texto: str, log: list[str]):
    for r in REGRAS:
        if r.variantes != ("*",) and entrada_id not in r.variantes:
            continue
        if r.arquivo and Path(caminho_origem).name != r.arquivo:
            continue
        sujeito = caminho if r.alvo == "caminho" else texto
        if r.regex:
            novo, n = re.subn(r.de, r.para, sujeito, flags=re.M)
        else:
            n = sujeito.count(r.de)
            novo = sujeito.replace(r.de, r.para)
        if r.vezes is not None and r.variantes != ("*",) and n != r.vezes:
            raise SystemExit(f"{entrada_id} {caminho_origem}: regra {r.id} se aplicou {n} vez(es), esperado {r.vezes}")
        if n:
            log.append(r.id)
            if r.alvo == "caminho":
                caminho = novo
            else:
                texto = novo
    return caminho, texto


# --------------------------------------------------------------------------
# Montagem
# --------------------------------------------------------------------------

@dataclass
class Entrada:
    id: str                                  # "base" ou "C13-v1"
    cs_id: str | None
    variante: str | None
    tipo: str                                # "base", "membros", "arquivos", "membros+arquivos"
    arquivos: dict[str, str]                 # caminho (como o modelo vê) -> conteúdo
    injetado: list[dict] = field(default_factory=list)  # o que a variante injetou (critério da D4)
    regras: list[str] = field(default_factory=list)     # neutralização aplicada

    def texto(self) -> str:
        """Os arquivos como o modelo os recebe: cabeçalho com o caminho e linhas numeradas."""
        blocos = []
        for caminho, conteudo in self.arquivos.items():
            linhas = conteudo.rstrip("\n").split("\n")
            numeradas = "\n".join(f"{i:4d} | {l}" for i, l in enumerate(linhas, 1))
            blocos.append(f"=== arquivo: {caminho} ===\n{numeradas}")
        return "\n\n".join(blocos)


def inserir_membros(controller: str, membros: str) -> tuple[str, dict]:
    """Igual a executar.inserir_membros do artigo de ferramentas: o corpo de
    `class Fragmento { ... }` entra antes da chave que fecha a CaixaController,
    precedido de uma linha em branco. Devolve o texto e a faixa inserida."""
    m = re.search(r"^class\s+Fragmento\s*\{\s*?\n", membros, re.M)
    fim = membros.rstrip().rfind("}")
    corpo = membros[m.end():fim].rstrip("\n").split("\n")
    linhas = controller.split("\n")
    fecha = max(i for i, l in enumerate(linhas) if l.rstrip() == "}")
    novas = [""] + corpo
    linhas[fecha:fecha] = novas
    inicio = fecha + 1
    return "\n".join(linhas), {"arquivo": CONTROLLER, "inicio": inicio, "fim": inicio + len(novas) - 1,
                               "deslocamento": len(novas), "linha_fecha_base": fecha + 1}


def montar() -> list[Entrada]:
    controller = obter_controller().read_text(encoding="utf-8")
    exemplos = obter_variantes()
    entradas = [Entrada("base", None, None, "base", {CONTROLLER: controller})]
    with open(exemplos / "variantes.csv", encoding="utf-8") as f:
        variantes = list(csv.DictReader(f))
    for v in variantes:
        eid = f"{v['cs_id']}-{v['variante']}"
        pasta = next(exemplos.glob(f"{v['cs_id']}-*/{v['variante']}"))
        e = Entrada(eid, v["cs_id"], v["variante"], v["tipo"], {})
        if "membros" in v["tipo"]:
            _, membros = aplicar_regras(eid, "membros.php", "membros.php",
                                        (pasta / "membros.php").read_text(encoding="utf-8"), e.regras)
            texto, faixa = inserir_membros(controller, membros)
            e.arquivos[CONTROLLER] = texto
            e.injetado.append(faixa)
        if "arquivos" in v["tipo"]:
            origem = pasta / "arquivos"
            for arq in sorted(p for p in origem.rglob("*") if p.is_file()):
                rel = arq.relative_to(origem).as_posix()
                caminho, texto = aplicar_regras(eid, rel, rel, arq.read_text(encoding="utf-8"), e.regras)
                e.arquivos[caminho] = texto
                e.injetado.append({"arquivo": caminho, "novo": True})
        e.regras = sorted(set(e.regras))
        entradas.append(e)
    conferir(entradas)
    return entradas


def conferir(entradas: list[Entrada]) -> None:
    """Para a montagem se algo não bate: número de entradas, vazamento, regras não aplicadas."""
    problemas = []
    if len(entradas) != 90:
        problemas.append(f"{len(entradas)} entradas; esperado 90 (89 variantes + linha de base)")
    for e in entradas:
        for caminho, conteudo in e.arquivos.items():
            for m in VAZAMENTO.finditer(caminho + "\n" + conteudo):
                problemas.append(f"{e.id} {caminho}: sobrou {m.group(0)!r}")
    aplicadas = {r for e in entradas for r in e.regras}
    for r in {r.id for r in REGRAS}:
        if r not in aplicadas:
            problemas.append(f"regra {r} não se aplicou a nenhuma entrada")
    if problemas:
        raise SystemExit("montagem com problemas:\n  " + "\n  ".join(problemas[:30]))


def registrar(entradas: list[Entrada]) -> Path:
    """Grava resultados/entradas.json (metadados, sem código) e trabalho/entradas/*.txt (o texto enviado)."""
    pasta_txt = TRABALHO / "entradas"
    pasta_txt.mkdir(parents=True, exist_ok=True)
    meta = []
    for e in entradas:
        texto = e.texto()
        (pasta_txt / f"{e.id}.txt").write_text(texto + "\n", encoding="utf-8")
        meta.append({
            "id": e.id, "cs_id": e.cs_id, "variante": e.variante, "tipo": e.tipo,
            "arquivos": [{"caminho": c, "linhas": t.rstrip("\n").count("\n") + 1, "sha256": sha256(t)}
                         for c, t in e.arquivos.items()],
            "injetado": e.injetado, "neutralizacao": e.regras, "sha256_texto": sha256(texto),
        })
    RESULTADOS.mkdir(exist_ok=True)
    destino = RESULTADOS / "entradas.json"
    destino.write_text(json.dumps({
        "fontes": {"pdvlaravel_commit": PDVLARAVEL_COMMIT, "caixacontroller_sha256": SHA_CONTROLLER,
                   "variantes": f"tools-cs-php {VARIANTES_RELEASE}", "manifesto": MANIFESTO.name},
        "entradas": meta,
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return destino
