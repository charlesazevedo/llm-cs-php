#!/usr/bin/env python3
"""Harness do experimento com modelos de IA (item L5 do plano).

Cada chamada é um trio (modelo, modo, entrada): 4 modelos (D10) x 2 modos (D12)
x 90 entradas (89 variantes + linha de base, D11) x 1 execução (D13) = 720. A
resposta de cada chamada vai para resultados/respostas/<modelo>/<modo>/<entrada>.json,
com o snapshot e o provedor que serviram, os tokens, o custo, a data e os hashes
da condição e da entrada. Uma resposta só é reaproveitada se os hashes, o modelo,
o provedor e os parâmetros baterem; rodar de novo não refaz o que já está
gravado, e uma execução interrompida continua de onde parou.

Os modelos são chamados pelo OpenRouter, com uma chave só e o provedor de origem
de cada modelo fixado (L5b; ver provedores.py). O `rodar` faz uma fila por
modelo, as quatro em paralelo, e cada fila faz as entradas do seu modelo uma
depois da outra: nunca há mais de uma chamada por fabricante ao mesmo tempo, e
o tempo total é o do modelo mais lento. As chamadas são independentes (sem
conversa nem cache), então o paralelismo não muda as respostas. Ctrl+C para de
começar chamadas novas e espera as em andamento terminarem e serem gravadas;
um segundo Ctrl+C sai na hora, e as em andamento, já cobradas, se perdem.

Uso, da raiz do repositório (o uv instala o SDK num ambiente temporário):

    H="uv run --no-project --with-requirements experimento/requirements.txt python experimento/harness.py"
    $H preparar                    # baixa e confere as fontes, monta e grava as 90 entradas
    $H testar                      # monta as 720 chamadas sem enviar nenhuma
    $H testar --mostrar C03-v1 --modo forcado    # imprime um prompt inteiro
    $H estimar                     # chamadas, tokens e custo (com os preços de modelos.yaml)
    $H modelos                     # confere modelos.yaml no catálogo público do OpenRouter (sem chave)
    $H conta                       # confere a chave: limite de gasto e uso (sem custo)
    $H rodar --amostra teste       # teste antes do piloto: a linha de base, 4 modelos x 2 modos = 8 chamadas
    $H resumo --amostra teste      # o que veio nas respostas gravadas: rota, tokens, custo, CS citados
    $H rodar --amostra piloto      # piloto (L7): 11 entradas, todos os modelos e modos
    $H rodar                       # execução completa (L8)
    $H rodar --modelo Claude --modo aberto --entrada C13-v1
    $H rodar --sequencial          # uma chamada por vez, sem as filas em paralelo
    $H rodar --cs C11-C17          # só as variantes destes CS (uma categoria, aqui), nos 4 modelos e 2 modos

A chave do OpenRouter fica em experimento/.env (fora do git; ver .env.example).
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import importlib.metadata
import json
import os
import re
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import entradas as E  # noqa: E402
import prompts as P  # noqa: E402
import provedores as V  # noqa: E402
import sinonimos as S  # noqa: E402

BASE = E.BASE
RESPOSTAS = E.RESULTADOS / "respostas"
AMBIENTE = E.RESULTADOS / "ambiente.json"


# --------------------------------------------------------------------------
# Configuração
# --------------------------------------------------------------------------

def carregar_env() -> None:
    """Lê experimento/.env (KEY=valor por linha); o que já está no ambiente vale mais."""
    arq = BASE / ".env"
    if not arq.exists():
        return
    for linha in arq.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        k, _, v = linha.partition("=")
        k, v = k.strip().removeprefix("export ").strip(), v.strip().strip('"').strip("'")
        if k and v and k not in os.environ:
            os.environ[k] = v


TAXA_CREDITOS, TAXA_MINIMA = 0.055, 0.80   # taxa do OpenRouter na compra de créditos com cartão


def carregar_config() -> tuple[dict, V.Acesso, list[V.Modelo]]:
    cfg = yaml.safe_load((BASE / "modelos.yaml").read_text(encoding="utf-8"))
    a = cfg["acesso"]
    acesso = V.Acesso(api=a["api"], env=a["env"], data_collection=a.get("data_collection"))
    modelos = [V.Modelo(nome=m["nome"], id=m["id"], provedor=m["provedor"],
                        formato=m.get("formato") or "json_schema", params=m.get("params") or {},
                        canonico=m.get("canonico"), data_collection=m.get("data_collection"),
                        preco_entrada=m.get("preco_entrada"), preco_saida=m.get("preco_saida"))
               for m in cfg["modelos"]]
    return cfg, acesso, modelos


def amostra_piloto(entradas: list[E.Entrada]) -> list[E.Entrada]:
    """L7: a linha de base, a primeira variante do primeiro CS de cada categoria e a
    única variante membros+arquivos (C24-v3), para que os três tipos apareçam."""
    with open(E.RAIZ / "dados" / "cs-experimento.csv", encoding="utf-8") as f:
        catalogo = list(csv.DictReader(f))
    primeiro_por_categoria = {}
    for c in catalogo:
        primeiro_por_categoria.setdefault(c["categoria"], c["id"])
    escolhidas = {"base", "C24-v3"} | {f"{cid}-v1" for cid in primeiro_por_categoria.values()}
    return [e for e in entradas if e.id in escolhidas]


def expandir_cs(tokens: list[str] | None) -> set[str]:
    """--cs C01 C05,C07 C11-C17 -> {"C01", "C05", "C07", "C11", ..., "C17"}."""
    escolhidos = set()
    for parte in re.split(r"[,\s]+", " ".join(tokens or [])):
        parte = parte.strip().upper()
        if not parte:
            continue
        m = re.fullmatch(r"C(\d{1,2})(?:-C?(\d{1,2}))?", parte)
        if not m:
            raise SystemExit(f"--cs: {parte!r} não é um id (C01) nem um intervalo (C01-C10)")
        ini, fim = int(m.group(1)), int(m.group(2) or m.group(1))
        if not 1 <= ini <= fim <= 38:
            raise SystemExit(f"--cs: {parte!r} fora de C01-C38")
        escolhidos |= {f"C{i:02d}" for i in range(ini, fim + 1)}
    return escolhidos


def selecionar(entradas, modelos, args):
    if getattr(args, "amostra", None) == "piloto":
        entradas = amostra_piloto(entradas)
    elif getattr(args, "amostra", None) == "teste":
        entradas = [e for e in entradas if e.id == "base"]
    if getattr(args, "entrada", None):
        entradas = [e for e in entradas if e.id in args.entrada]
    if getattr(args, "cs", None):
        escolhidos = expandir_cs(args.cs)
        entradas = [e for e in entradas if e.cs_id in escolhidos]
    if getattr(args, "modelo", None):
        nomes = [m.nome for m in modelos]
        modelos = [m for m in modelos if m.nome.lower() == args.modelo.lower()]
        if not modelos:
            raise SystemExit(f"modelo desconhecido: {args.modelo} (os de modelos.yaml: {', '.join(nomes)})")
    modos = [args.modo] if getattr(args, "modo", None) else list(P.MODOS)
    return entradas, modelos, modos


def destino(modelo: V.Modelo, modo: str, entrada: E.Entrada) -> Path:
    return RESPOSTAS / modelo.nome / modo / f"{entrada.id}.json"


def diferencas(modelo: V.Modelo, rota: dict, modo: str, entrada: E.Entrada, max_tokens: int, r: dict) -> list[str]:
    """O que mudou entre a resposta gravada e a condição atual; vazio se ela ainda vale."""
    mudou = []
    if r.get("hash_condicao") != P.hash_condicao(modo):
        mudou.append("o prompt, o esquema ou o catálogo")
    if r.get("sha256_entrada") != E.sha256(entrada.texto()):
        mudou.append("o código da entrada")
    if r.get("modelo_pedido") != modelo.id:
        mudou.append(f"o modelo ({r.get('modelo_pedido')} → {modelo.id})")
    if r.get("provider") != rota:
        mudou.append("a rota ou a política de dados")
    if r.get("formato") != modelo.formato:
        mudou.append(f"o formato ({r.get('formato')} → {modelo.formato})")
    if r.get("params") != modelo.params:
        mudou.append(f"os parâmetros ({r.get('params')} → {modelo.params})")
    if r.get("max_tokens") != max_tokens:
        mudou.append(f"o limite de tokens ({r.get('max_tokens')} → {max_tokens})")
    return mudou


def falhou(r: dict) -> bool:
    """Gravada sem resposta do modelo: nem modelo servido, nem tokens, nem texto. Antes de 05/10/2026, o
    harness gravava assim as chamadas a que o OpenRouter respondia 200 sem nenhuma escolha do modelo (5 do
    ChatGPT no modo forçado, em C11–C17); hoje elas viram erro e não são gravadas."""
    return (not r.get("modelo_servido") and not r.get("tokens_saida") and r.get("resposta") is None
            and not r.get("texto_bruto"))


def situacao(modelo: V.Modelo, rota: dict, modo: str, entrada: E.Entrada,
             max_tokens: int) -> tuple[str, dict | None]:
    """"nova" (sem resposta), "valida" (gravada com a mesma condição, modelo, rota,
    formato, parâmetros e limite de tokens; não é refeita), "desatualizada" ou "falha"
    (gravada sem resposta do modelo; o rodar a refaz, como uma nova)."""
    arq = destino(modelo, modo, entrada)
    if not arq.exists():
        return "nova", None
    r = json.loads(arq.read_text(encoding="utf-8"))
    if falhou(r):
        return "falha", r
    return ("desatualizada" if diferencas(modelo, rota, modo, entrada, max_tokens, r) else "valida"), r


# --------------------------------------------------------------------------
# Comandos
# --------------------------------------------------------------------------

def cmd_preparar(args) -> int:
    entradas = E.montar()
    caminho = E.registrar(entradas)
    tipos = {}
    for e in entradas:
        tipos[e.tipo] = tipos.get(e.tipo, 0) + 1
    print(f"{len(entradas)} entradas: " + ", ".join(f"{n} {t}" for t, n in sorted(tipos.items())))
    for e in entradas:
        if e.regras:
            print(f"  {e.id:8s} neutralização: {', '.join(e.regras)}")
    print(f"mantidos sem mudança: {', '.join(E.MANTIDOS)}")
    print(f"metadados em {caminho.relative_to(E.RAIZ)}; texto das entradas em "
          f"{(E.TRABALHO / 'entradas').relative_to(E.RAIZ)}/ (fora do git)")
    return 0


def cmd_testar(args) -> int:
    """Monta todas as chamadas sem enviar nenhuma e confere o que dá para conferir offline."""
    _, acesso, modelos = carregar_config()
    entradas = E.montar()
    problemas = []
    for m in modelos:
        if m.formato not in V.FORMATOS:
            problemas.append(f"{m.nome}: formato desconhecido {m.formato}")
        if "/" not in m.id or m.id.endswith("latest") or ":" in m.id:
            problemas.append(f"{m.nome}: {m.id} não é um slug <autor>/<modelo> fixo")
        if not m.provedor:
            problemas.append(f"{m.nome}: sem provedor fixado")
        for politica in (m.data_collection, acesso.data_collection):
            if politica not in (None, "allow", "deny"):
                problemas.append(f"{m.nome}: data_collection {politica!r} (use allow, deny ou vazio)")
    ordem = P.ordem_do_catalogo()
    if sorted(c["id"] for c in ordem) != [f"C{i:02d}" for i in range(1, 39)]:
        problemas.append("o catálogo do modo forçado não tem os 38 CS uma vez cada")
    with open(E.RAIZ / "dados" / "cs-experimento.csv", encoding="utf-8") as f:
        problemas += S.conferir(S.carregar(), list(csv.DictReader(f)))
    pasta = E.TRABALHO / "prompts"
    n = 0
    for e in entradas:
        codigo = e.texto()
        for modo in P.MODOS:
            prompt = P.montar(modo, codigo, len(e.arquivos))
            json.dumps(P.ESQUEMAS[modo])
            if codigo not in prompt:
                problemas.append(f"{e.id}/{modo}: o código não entrou no prompt")
            (pasta / modo).mkdir(parents=True, exist_ok=True)
            (pasta / modo / f"{e.id}.txt").write_text(P.SISTEMA + "\n\n---\n\n" + prompt + "\n", encoding="utf-8")
            n += len(modelos)
    if args.mostrar:
        e = next(x for x in entradas if x.id == args.mostrar)
        print(P.montar(args.modo or "aberto", e.texto(), len(e.arquivos)))
        return 0
    print(f"{len(entradas)} entradas x {len(P.MODOS)} modos x {len(modelos)} modelos = {n} chamadas montadas, nenhuma enviada")
    print(f"condições: " + ", ".join(f"{modo} {P.hash_condicao(modo)}" for modo in P.MODOS)
          + f"; catálogo do forçado com semente {P.SEMENTE_CATALOGO}")
    print(f"prompts gravados em {pasta.relative_to(E.RAIZ)}/ (fora do git)")
    for m in modelos:
        print(f"  {m.nome:9s} {m.id} @ {m.provedor}, {m.formato}, params {m.params or '{}'}, "
              f"provider {json.dumps(V.roteamento(acesso, m))}")
    print(f"chave {acesso.env}: {'definida' if os.environ.get(acesso.env) else 'não definida'}")
    for p in problemas:
        print(f"  PROBLEMA {p}")
    return 1 if problemas else 0


def aprox(segundos: float | None) -> str:
    """Tempo aproximado para mensagens: "~3h36", "~25 min" ou "menos de 1 min"."""
    texto = em_horas(segundos)
    return texto if texto in ("?", "menos de 1 min") else "~" + texto


def em_horas(segundos: float | None) -> str:
    if segundos is None:
        return "?"
    minutos = round(segundos / 60)
    if minutos < 1:
        return "menos de 1 min"
    return f"{minutos} min" if minutos < 60 else f"{minutos // 60}h{minutos % 60:02d}"


def em_tokens(n: float) -> str:
    return f"{n / 1e6:.2f} M" if n >= 1e5 else f"{n / 1e3:.1f} mil"


def contar_tokens(texto: str) -> int:
    import tiktoken
    return len(tiktoken.get_encoding("o200k_base").encode(texto))


SAIDA_SUPOSTA = {"aberto": 600, "forcado": 2000}   # tokens por resposta, sem raciocínio, até haver medidas


def estimativa(cfg: dict, acesso: V.Acesso, modelos: list[V.Modelo], entradas: list[E.Entrada], modos: list[str],
               usar_gravadas: bool = True) -> dict:
    """Tokens e custo por modelo. Com usar_gravadas, onde já há respostas gravadas (válidas ou desatualizadas),
    a saída (com o raciocínio) é a média delas, por modo, e a entrada é corrigida pela razão entre o que o
    provedor contou e o o200k_base. Só as válidas contam como já feitas."""
    por_modelo = []
    for m in modelos:
        rota = V.roteamento(acesso, m)
        contados, validas, medidas_por_modo = {}, {modo: {} for modo in modos}, {modo: {} for modo in modos}
        for modo in modos:
            for e in entradas:
                contados[modo, e.id] = contar_tokens(P.SISTEMA + P.montar(modo, e.texto(), len(e.arquivos)))
                estado, r = situacao(m, rota, modo, e, cfg["max_tokens"])
                if usar_gravadas and r is not None:
                    medidas_por_modo[modo][e.id] = r
                    if estado == "valida":
                        validas[modo][e.id] = r
        pares = [(r["tokens_entrada"], contados[modo, eid]) for modo in modos
                 for eid, r in medidas_por_modo[modo].items() if r.get("tokens_entrada")]
        fator = sum(a for a, _ in pares) / sum(b for _, b in pares) if pares else 1.0
        ent = sai = ent_falta = sai_falta = medido = 0.0
        tempo, tempo_falta = 0.0, 0.0
        fontes, gravadas = [], 0
        for modo in modos:
            medidas = [r.get("tokens_saida") or 0 for r in medidas_por_modo[modo].values()]
            duracoes = [r["duracao_s"] for r in medidas_por_modo[modo].values() if r.get("duracao_s")]
            por_chamada = sum(medidas) / len(medidas) if medidas else SAIDA_SUPOSTA[modo]
            segundos = sum(duracoes) / len(duracoes) if duracoes else None
            fontes.append(f"{modo} {'pela média de %d gravada(s)' % len(medidas) if medidas else 'suposta'}")
            for e in entradas:
                ent += contados[modo, e.id] * fator
                sai += por_chamada
                tempo = None if tempo is None or segundos is None else tempo + segundos
                if e.id not in validas[modo]:
                    ent_falta += contados[modo, e.id] * fator
                    sai_falta += por_chamada
                    tempo_falta = None if tempo_falta is None or segundos is None else tempo_falta + segundos
            gravadas += len(validas[modo])
            medido += sum(r.get("custo") or 0 for r in validas[modo].values())
        fontes.append(f"entrada x{fator:.2f} pelo que o provedor contou" if pares else "entrada pelo o200k_base")
        tem_preco = m.preco_entrada is not None and m.preco_saida is not None
        preco = (lambda a, b: a / 1e6 * m.preco_entrada + b / 1e6 * m.preco_saida) if tem_preco else (lambda a, b: None)
        por_modelo.append({"modelo": m, "entrada": ent, "saida": sai, "fontes": fontes, "custo": preco(ent, sai),
                           "falta": preco(ent_falta, sai_falta), "gravadas": gravadas, "medido": medido,
                           "tempo": tempo, "tempo_falta": tempo_falta})
    total = sum(x["custo"] or 0 for x in por_modelo)

    def juntar(chave: str, como) -> float | None:
        valores = [x[chave] for x in por_modelo]
        return None if not valores or any(v is None for v in valores) else como(valores)

    return {"chamadas": len(entradas) * len(modos) * len(modelos), "modelos": por_modelo, "total": total,
            "falta": sum(x["falta"] or 0 for x in por_modelo), "gravadas": sum(x["gravadas"] for x in por_modelo),
            "medido": sum(x["medido"] for x in por_modelo), "taxa": max(total * TAXA_CREDITOS, TAXA_MINIMA),
            # tempo: com as filas em paralelo, o do modelo mais lento; em sequência, a soma
            "tempo_paralelo": juntar("tempo", max), "tempo_sequencial": juntar("tempo", sum),
            "tempo_falta_paralelo": juntar("tempo_falta", max), "tempo_falta_sequencial": juntar("tempo_falta", sum)}


def cmd_estimar(args) -> int:
    """Tokens e custo antes de gastar (ver `estimativa`)."""
    cfg, acesso, modelos = carregar_config()
    entradas, modelos, modos = selecionar(E.montar(), modelos, args)
    est = estimativa(cfg, acesso, modelos, entradas, modos)
    print(f"{len(entradas)} entradas x {len(modos)} modos x {len(modelos)} modelos x "
          f"{cfg.get('execucoes', 1)} execução = {est['chamadas']} chamadas")
    for x in est["modelos"]:
        m = x["modelo"]
        custo = f"; ~US$ {x['custo']:.2f}" if x["custo"] is not None else "; sem preço em modelos.yaml"
        print(f"  {m.nome:9s} {m.id:30s} ~{em_tokens(x['entrada'])} tokens de entrada, ~{em_tokens(x['saida'])} de saída "
              f"({'; '.join(x['fontes'])}){custo}")
    print(f"custo dos modelos com preço informado: ~US$ {est['total']:.2f}; comprando os créditos com cartão, "
          f"mais ~US$ {est['taxa']:.2f} de taxa ({TAXA_CREDITOS:.1%}, mínimo US$ {TAXA_MINIMA:.2f}).")
    if est["gravadas"]:
        print(f"já gravadas e válidas: {est['gravadas']} (custaram US$ {est['medido']:.4f} e não são refeitas); "
              f"as que faltam: ~US$ {est['falta']:.2f}.")
    if est["tempo_falta_paralelo"] is not None:
        lento = max(est["modelos"], key=lambda x: x["tempo_falta"])["modelo"].nome
        print(f"tempo das que faltam, pela duração média das gravadas: {aprox(est['tempo_falta_paralelo'])} "
              f"com as filas em paralelo (o mais lento é o {lento}), {aprox(est['tempo_falta_sequencial'])} "
              "em sequência.")
    else:
        print("tempo: sem respostas gravadas de todos os modelos e modos para estimar.")
    print("Tokens contados com o o200k_base (aproximação). A saída suposta não inclui os tokens de raciocínio, "
          "que são cobrados como saída; a medida pelas respostas gravadas inclui. Nenhuma chamada foi feita.")
    return 0


def cmd_conta(args) -> int:
    """Confere a chave no OpenRouter: se vale, o limite de gasto e o uso. Sem custo e sem inferência."""
    import urllib.error

    _, acesso, modelos = carregar_config()
    if not os.environ.get(acesso.env):
        print(f"{acesso.env} não definida: copie experimento/.env.example para experimento/.env e preencha")
        return 1
    try:
        info = V.chave_info(acesso)
    except urllib.error.HTTPError as erro:
        print(f"a chave foi recusada (HTTP {erro.code}): confira {acesso.env} em experimento/.env")
        return 1
    limite, restante = info.get("limit"), info.get("limit_remaining")
    print("chave válida")
    print(f"  limite de gasto da chave: {'nenhum' if limite is None else f'US$ {limite:.2f}'}"
          + ("" if restante is None else f" (restam US$ {restante:.2f})")
          + (f", renovado: {info['limit_reset']}" if info.get("limit_reset") else ""))
    print(f"  uso da chave: US$ {info.get('usage') or 0:.4f} no total, US$ {info.get('usage_daily') or 0:.4f} hoje")
    problemas = 0
    if info.get("is_free_tier"):
        problemas += 1
        print("  PROBLEMA a conta nunca comprou créditos: as chamadas a modelos pagos vão falhar")
    if restante is not None and restante <= 0:
        problemas += 1
        print("  PROBLEMA o limite de gasto da chave acabou")
    if limite is None:
        print("  aviso: a chave não tem limite de gasto; dá para pôr um em openrouter.ai/settings/keys")
    treinam = [m.nome for m in modelos if (m.data_collection or acesso.data_collection) == "allow"]
    if treinam:
        print(f"  lembrete: endpoint que treina com os prompts em {', '.join(treinam)}. A configuração de "
              "privacidade da conta (openrouter.ai/settings/privacy) tem de permitir endpoints pagos que treinam, "
              "e a API não deixa conferir isso; se não permitir, essas chamadas falham, sem custo.")
    print("Nenhuma chamada de inferência foi feita.")
    return 1 if problemas else 0


def _trechos_ruins(trechos, entrada: E.Entrada) -> int:
    """Trechos que apontam um arquivo que não está na entrada ou linhas fora dele."""
    tamanhos = {c: len(t.rstrip("\n").split("\n")) for c, t in entrada.arquivos.items()}
    por_nome = {Path(c).name: n for c, n in tamanhos.items()}
    ruins = 0
    for t in trechos:
        n = tamanhos.get(t.get("arquivo")) or por_nome.get(Path(str(t.get("arquivo"))).name)
        ini, fim = t.get("linha_inicio"), t.get("linha_fim")
        if not n or not isinstance(ini, int) or not isinstance(fim, int) or not 1 <= ini <= fim <= n:
            ruins += 1
    return ruins


def cmd_resumo(args) -> int:
    """O que veio nas respostas gravadas: provedor e snapshot, tokens, custo, os CS citados e o que não bate."""
    cfg, acesso, modelos = carregar_config()
    entradas, modelos, modos = selecionar(E.montar(), modelos, args)
    catalogo = P.ordem_do_catalogo()
    contagem = {"respostas": 0, "sem resposta": 0, "desatualizadas": 0, "JSON inválido": 0, "com desvio": 0,
                "com problema": 0}
    custo, tokens = 0.0, {}
    for m in modelos:
        rota = V.roteamento(acesso, m)
        for modo in modos:
            for e in entradas:
                estado, r = situacao(m, rota, modo, e, cfg["max_tokens"])
                rotulo = f"{m.nome}/{modo}/{e.id}"
                if estado in ("nova", "falha"):
                    contagem["sem resposta"] += 1
                    print(f"\n{rotulo}: " + ("sem resposta gravada" if estado == "nova"
                                              else "gravada sem resposta do modelo (o rodar a refaz)"))
                    continue
                contagem["respostas"] += 1
                if estado == "desatualizada":
                    contagem["desatualizadas"] += 1
                custo += r.get("custo") or 0
                tokens.setdefault((m.nome, modo), []).append(r.get("tokens_saida") or 0)
                print(f"\n{rotulo}{' (DESATUALIZADA)' if estado == 'desatualizada' else ''}: "
                      f"{r.get('provedor_servido')}, {r.get('modelo_servido')}, fim {r.get('stop_reason')}, "
                      f"{r.get('duracao_s')} s")
                print(f"  tokens: {r.get('tokens_entrada')} de entrada, {r.get('tokens_saida')} de saída "
                      f"({r.get('tokens_raciocinio') or 0} de raciocínio); custo US$ {r.get('custo') or 0:.4f}")
                desvios_r = V.desvios(m, r)   # recalculado dos metadados, com a regra atual
                if desvios_r:
                    contagem["com desvio"] += 1
                    print(f"  DESVIO {'; '.join(desvios_r)}")
                if r.get("recusa"):
                    print(f"  RECUSA {r['recusa']}")
                resp = r.get("resposta")
                if not isinstance(resp, dict):
                    contagem["JSON inválido"] += 1
                    print(f"  JSON inválido: {r.get('erro_json')}; início do texto: {(r.get('texto_bruto') or '')[:200]!r}")
                    continue
                problemas = []
                if modo == "aberto":
                    itens = resp.get("smells")
                    if not isinstance(itens, list):
                        problemas.append("sem a lista 'smells'")
                        itens = []
                    print(f"  {len(itens)} CS citado(s):")
                    for s in itens:
                        print(f"    - {s.get('nome')} ({s.get('arquivo')}, linhas {s.get('linha_inicio')}-{s.get('linha_fim')})")
                    trechos = itens
                else:
                    itens = resp.get("avaliacoes") if isinstance(resp.get("avaliacoes"), list) else []
                    numeros = [a.get("item") for a in itens]
                    if sorted(n for n in numeros if isinstance(n, int)) != list(range(1, len(catalogo) + 1)):
                        problemas.append(f"os itens avaliados não são 1 a {len(catalogo)}, uma vez cada")
                    presentes = [a for a in itens if a.get("presente")]
                    print(f"  {len(itens)} itens avaliados, {len(presentes)} presente(s):")
                    for a in presentes:
                        n = a.get("item")
                        nome = catalogo[n - 1]["nome"] if isinstance(n, int) and 1 <= n <= len(catalogo) else "?"
                        faixas = ", ".join(f"{t.get('linha_inicio')}-{t.get('linha_fim')}" for t in a.get("trechos") or [])
                        print(f"    - item {n}: {nome} (linhas {faixas or 'não informadas'})")
                    trechos = [t for a in presentes for t in a.get("trechos") or []]
                ruins = _trechos_ruins(trechos, e)
                if ruins:
                    problemas.append(f"{ruins} trecho(s) com arquivo ou linhas fora da entrada")
                for p in problemas:
                    print(f"  PROBLEMA {p}")
                contagem["com problema"] += bool(problemas)
    print("\n" + ", ".join(f"{k}: {v}" for k, v in contagem.items()) + f"; custo das respostas: US$ {custo:.4f}")
    for (nome, modo), valores in tokens.items():
        print(f"  {nome:9s} {modo:8s} média de {sum(valores) / len(valores):.0f} tokens de saída em {len(valores)} resposta(s)")
    return 1 if any(contagem[k] for k in ("sem resposta", "desatualizadas", "JSON inválido", "com desvio", "com problema")) else 0


def cmd_modelos(args) -> int:
    """Confere cada modelo de modelos.yaml no catálogo público do OpenRouter (sem chave e sem custo)."""
    cfg, _, modelos = carregar_config()
    catalogo = V.catalogo()
    maior_prompt = max(contar_tokens(P.SISTEMA + P.montar(modo, e.texto(), len(e.arquivos)))
                       for e in E.montar() for modo in P.MODOS)
    print(f"maior prompt do experimento: ~{maior_prompt} tokens (o200k_base)")
    problemas = []
    for m in modelos:
        print(f"\n=== {m.nome}: {m.id} @ {m.provedor} ===")
        info = catalogo.get(m.id)
        if not info:
            problemas.append(f"{m.nome}: {m.id} não está no catálogo")
            print("    não está no catálogo")
            continue
        criado = datetime.fromtimestamp(info["created"], timezone.utc).date() if info.get("created") else "?"
        print(f"    snapshot {info.get('canonical_slug')} (no catálogo desde {criado}); "
              f"expira: {info.get('expiration_date') or 'sem data'}")
        if m.canonico and info.get("canonical_slug") != m.canonico:
            problemas.append(f"{m.nome}: o snapshot servido mudou: {info.get('canonical_slug')} (modelos.yaml: {m.canonico})")
        if info.get("expiration_date"):
            problemas.append(f"{m.nome}: o modelo sai do catálogo em {info['expiration_date']}")
        todos = V.endpoints(m.id)
        print("    endpoints: " + ", ".join(e["tag"] for e in todos))
        fixados = [e for e in todos if e["tag"] == m.provedor]
        if not fixados:
            problemas.append(f"{m.nome}: nenhum endpoint {m.provedor}")
            continue
        e = fixados[0]
        suportados = set(e.get("supported_parameters") or [])
        # o teto: o maior preço entre o base e as faixas que os prompts do experimento atingem
        # (as por dia e hora sempre; as por tamanho do prompt, só se algum prompt chegar lá)
        faixas = e["pricing"].get("overrides") or []
        por_hora = any("utc_days" in t or "utc_start" in t for t in faixas)
        tabelas = [e["pricing"], *(t for t in faixas if (t.get("min_prompt_tokens") or 0) <= maior_prompt)]
        preco = {k: max(float(t[k]) for t in tabelas if t.get(k)) * 1e6 for k in ("prompt", "completion")}
        print(f"    {e['tag']}: {e['provider_name']}, quantização {e.get('quantization')}, status {e.get('status')}, "
              f"saída máx. {e.get('max_completion_tokens')}, US$ {preco['prompt']:.2f}/{preco['completion']:.2f} por M")
        print(f"      parâmetros: {', '.join(sorted(suportados))}")
        if por_hora:
            print("      o preço varia com o dia e a hora; acima está o maior, e a cobrança é a da hora da chamada")
        for t in faixas:
            if (t.get("min_prompt_tokens") or 0) > maior_prompt:
                print(f"      acima de {t['min_prompt_tokens']} tokens de prompt o preço é outro (nenhum prompt chega lá)")
        exigidos = {V.FORMATOS.get(m.formato, m.formato), "max_tokens", *m.params}
        for p in sorted(exigidos - suportados):
            problemas.append(f"{m.nome}: {m.provedor} não aceita {p} (a chamada falharia com require_parameters)")
        if m.formato == "json_object" and "structured_outputs" in suportados:
            problemas.append(f"{m.nome}: {m.provedor} aceita saída estruturada; use formato json_schema")
        if e.get("max_completion_tokens") and cfg["max_tokens"] > e["max_completion_tokens"]:
            problemas.append(f"{m.nome}: max_tokens {cfg['max_tokens']} acima do máximo do endpoint")
        if (m.preco_entrada, m.preco_saida) != (round(preco["prompt"], 4), round(preco["completion"], 4)):
            problemas.append(f"{m.nome}: preço em modelos.yaml ({m.preco_entrada}/{m.preco_saida}) "
                             f"difere do catálogo ({preco['prompt']:.4g}/{preco['completion']:.4g})")
    print()
    for p in problemas:
        print(f"  PROBLEMA {p}")
    print("Consulta só ao catálogo público; nenhuma chamada de inferência foi feita.")
    return 1 if problemas else 0


def ler_json(texto: str):
    texto = texto.strip()
    if texto.startswith("```"):
        texto = texto.strip("`").removeprefix("json").strip()
    return json.loads(texto)


AVISO_A_CADA = 120   # segundos sem chamada concluída antes de mostrar as que estão em andamento


def _esperar(futuros, enquanto=None) -> None:
    pendentes = set(futuros)
    while pendentes:
        _, pendentes = concurrent.futures.wait(pendentes, timeout=0.5)
        if enquanto:
            enquanto()


def cmd_rodar(args) -> int:
    cfg, acesso, configurados = carregar_config()
    todas = E.montar()
    E.registrar(todas)
    entradas, modelos, modos = selecionar(todas, configurados, args)
    if not os.environ.get(acesso.env):
        print(f"{acesso.env} não definida (veja experimento/.env.example); nenhuma chamada feita", file=sys.stderr)
        return 1
    execucao = "sequencial" if args.sequencial else "paralela, uma fila por modelo"
    trava, parar = threading.Lock(), threading.Event()
    conta = {"novas": 0, "cache": 0, "desatualizadas": 0, "erros": 0, "desvio": 0, "nao_iniciadas": 0, "custo": 0.0}

    # o que cada fila vai fazer: as respostas que faltam e, com --refazer, as desatualizadas
    pendentes, rotas, media = {}, {}, {}
    for m in modelos:
        rotas[m.nome] = rota = V.roteamento(acesso, m)
        pendentes[m.nome], duracoes = [], []
        for modo in modos:
            for e in entradas:
                estado, antigo = situacao(m, rota, modo, e, cfg["max_tokens"])
                if antigo and antigo.get("duracao_s") and estado != "falha":
                    duracoes.append(antigo["duracao_s"])
                if estado == "falha":
                    print(f"  FALHA GRAVADA {m.nome}/{modo}/{e.id}: sem resposta do modelo; vai ser refeita",
                          file=sys.stderr)
                if estado == "valida":
                    conta["cache"] += 1
                elif estado == "desatualizada" and not args.refazer:
                    conta["desatualizadas"] += 1
                    mudou = diferencas(m, rota, modo, e, cfg["max_tokens"], antigo)
                    print(f"  DESATUALIZADA {m.nome}/{modo}/{e.id}: mudou {', '.join(mudou)} (use --refazer)",
                          file=sys.stderr)
                else:
                    pendentes[m.nome].append((modo, e))
        media[m.nome] = sum(duracoes) / len(duracoes) if duracoes else None   # duração média, para a previsão
    total = sum(len(v) for v in pendentes.values())
    feitas = {m.nome: [] for m in modelos}          # durações das chamadas concluídas nesta rodada
    andamento = {}                                  # modelo -> (modo, entrada, início)
    ultimo_aviso = [time.monotonic()]

    def dizer(texto: str, erro: bool = False) -> None:
        with trava:
            print(texto, file=sys.stderr if erro else sys.stdout, flush=True)

    def somar(chave: str, valor=1) -> None:
        with trava:
            conta[chave] += valor

    def falta() -> str:
        """Quantas faltam e o tempo previsto: em paralelo, o da fila mais demorada; em sequência, a soma."""
        restantes, tempos = 0, []
        for m in modelos:
            n = len(pendentes[m.nome]) - len(feitas[m.nome])
            restantes += n
            base = (sum(feitas[m.nome]) / len(feitas[m.nome])) if feitas[m.nome] else media[m.nome]
            tempos.append(None if base is None and n else n * (base or 0))
        if not restantes:
            return "nenhuma falta"
        previsto = None if None in tempos else (sum(tempos) if args.sequencial else max(tempos))
        if previsto is None:
            return f"faltam {restantes}"
        return f"faltam {restantes}, " + ("menos de 1 min" if previsto < 30 else f"~{em_horas(previsto)}")

    def uma(m: V.Modelo, rota: dict, modo: str, e: E.Entrada) -> None:
        texto_entrada = e.texto()
        arq = destino(m, modo, e)
        prompt = P.montar(modo, texto_entrada, len(e.arquivos))
        inicio = datetime.now(timezone.utc)
        t0 = time.monotonic()
        with trava:
            andamento[m.nome] = (modo, e.id, t0)
        try:
            texto, meta = V.chamar(acesso, m, prompt, P.ESQUEMAS[modo], cfg["max_tokens"],
                                   aviso=lambda t: dizer(f"  {m.nome:9s} {modo:8s} {e.id:8s} {t}", erro=True))
        except Exception as erro:  # noqa: BLE001 - registra e segue; a chamada é refeita na próxima rodada
            with trava:
                andamento.pop(m.nome, None)
                feitas[m.nome].append(time.monotonic() - t0)
                conta["erros"] += 1
                n = sum(len(v) for v in feitas.values())
            dizer(f"  [{n:>{len(str(total))}}/{total}] ERRO {m.nome}/{modo}/{e.id}: {type(erro).__name__}: {erro}",
                  erro=True)
            return
        registro = {
            "modelo": m.nome, "modelo_pedido": m.id, "provider": rota, "formato": m.formato,
            "params": m.params, "max_tokens": cfg["max_tokens"],
            "modo": modo, "entrada": e.id, "cs_id": e.cs_id, "variante": e.variante,
            "hash_condicao": P.hash_condicao(modo), "sha256_entrada": E.sha256(texto_entrada),
            "inicio": inicio.isoformat(timespec="seconds"),
            "duracao_s": round(time.monotonic() - t0 - (meta.get("espera_s") or 0), 1),
            "execucao": execucao, **meta, "resposta": None,
        }
        try:
            registro["resposta"] = ler_json(texto)
        except json.JSONDecodeError as erro:
            registro["texto_bruto"] = texto
            registro["erro_json"] = str(erro)
        registro["desvios"] = V.desvios(m, meta)
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_text(json.dumps(registro, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        itens = registro["resposta"].get("smells" if modo == "aberto" else "avaliacoes") \
            if isinstance(registro["resposta"], dict) else None
        quantos = f"{len(itens)} itens" if isinstance(itens, list) else "JSON inválido"
        with trava:
            andamento.pop(m.nome, None)
            feitas[m.nome].append(registro["duracao_s"])
            conta["novas"] += 1
            conta["custo"] += meta.get("custo") or 0
            n = sum(len(v) for v in feitas.values())
            resto = falta()
            ultimo_aviso[0] = time.monotonic()
        dizer(f"  [{n:>{len(str(total))}}/{total}] {m.nome:9s} {modo:8s} {e.id:8s} {quantos} "
              f"({meta.get('stop_reason')}, {meta.get('provedor_servido')}, {registro['duracao_s']:.0f} s, "
              f"US$ {meta.get('custo') or 0:.4f}); {resto}")
        if registro["desvios"]:
            somar("desvio")
            dizer(f"    DESVIO {m.nome}/{modo}/{e.id}: {'; '.join(registro['desvios'])}", erro=True)

    def fila(m: V.Modelo) -> None:
        for modo, e in pendentes[m.nome]:
            if parar.is_set():
                somar("nao_iniciadas")
                continue
            uma(m, rotas[m.nome], modo, e)

    def avisar_andamento() -> None:
        agora = time.monotonic()
        with trava:
            if agora - ultimo_aviso[0] < AVISO_A_CADA or not andamento:
                return
            ultimo_aviso[0] = agora
            n = sum(len(v) for v in feitas.values())
            texto = "; ".join(f"{nome} {modo} {eid} há {em_horas(agora - t)}" if agora - t >= 60
                              else f"{nome} {modo} {eid} há {agora - t:.0f} s"
                              for nome, (modo, eid, t) in andamento.items())
            resto = falta()
        dizer(f"  … em andamento: {texto}. Feitas {n}/{total}; {resto}")

    t0 = time.monotonic()
    print(f"{len(entradas)} entradas x {len(modos)} modos x {len(modelos)} modelos = "
          f"{len(entradas) * len(modos) * len(modelos)} respostas; {conta['cache']} já gravadas e válidas"
          + (f", {conta['desatualizadas']} desatualizadas (puladas)" if conta["desatualizadas"] else "")
          + f"; {total} chamadas a fazer, execução {execucao}" + (f"; {falta()}" if total else ""), flush=True)
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1 if args.sequencial else max(1, len(modelos)))
    futuros = [executor.submit(fila, m) for m in modelos if pendentes[m.nome]]
    primeiro = None
    while True:
        try:
            _esperar(futuros, avisar_andamento)
            break
        except KeyboardInterrupt:
            agora = time.monotonic()
            if primeiro is None:
                primeiro = agora
                parar.set()
                dizer("\nInterrompido: nenhuma chamada nova começa; esperando as em andamento terminarem e serem "
                      "gravadas. Ctrl+C de novo, depois de 2 s, sai já, e as em andamento (já cobradas) se perdem.",
                      erro=True)
            elif agora - primeiro > 2:
                dizer("Saindo sem esperar as chamadas em andamento.", erro=True)
                os._exit(130)
            # menos de 2 s depois: é o mesmo Ctrl+C, que o terminal manda ao grupo e o uv repassa ao Python
    executor.shutdown()
    for f in futuros:
        f.result()   # um erro inesperado numa fila aparece aqui
    registrar_ambiente(acesso, configurados)
    minutos = (time.monotonic() - t0) / 60
    print(f"\nnovas: {conta['novas']}  em cache: {conta['cache']}  desatualizadas: {conta['desatualizadas']}  "
          f"erros: {conta['erros']}  com desvio de rota: {conta['desvio']}"
          + (f"  não iniciadas (interrupção): {conta['nao_iniciadas']}" if conta["nao_iniciadas"] else "")
          + f"  custo das novas: US$ {conta['custo']:.4f}  tempo: {minutos:.1f} min")
    return 1 if conta["erros"] or conta["desatualizadas"] or conta["desvio"] or conta["nao_iniciadas"] else 0


def registrar_ambiente(acesso: V.Acesso, modelos: list[V.Modelo]) -> None:
    """resultados/ambiente.json: versões, modelos e rotas pedidos, o que serviu, custo, datas e condições (C3)."""
    servidos, provedores, datas = {}, {}, []
    custo, execucoes = {}, set()
    for arq in RESPOSTAS.rglob("*.json"):
        r = json.loads(arq.read_text(encoding="utf-8"))
        execucoes.add(r.get("execucao") or "sequencial")
        servidos.setdefault(r["modelo"], set()).add(r.get("modelo_servido"))
        provedores.setdefault(r["modelo"], set()).add(r.get("provedor_servido"))
        custo[r["modelo"]] = custo.get(r["modelo"], 0) + (r.get("custo") or 0)
        datas.append(r.get("inicio"))
    versoes = {}
    for pacote in ("openai", "pyyaml", "tiktoken"):
        try:
            versoes[pacote] = importlib.metadata.version(pacote)
        except importlib.metadata.PackageNotFoundError:
            versoes[pacote] = None
    AMBIENTE.write_text(json.dumps({
        "python": sys.version.split()[0], "sdks": versoes,
        "acesso": {"api": acesso.api, "data_collection": acesso.data_collection,
                   "plugins_desligados": list(V.PLUGINS), "cabecalhos": V.CABECALHOS,
                   "tempo_limite_s": V.TEMPO_LIMITE, "tentativas_sem_custo": V.TENTATIVAS},
        "execucoes": sorted(execucoes),
        "modelos": [{"nome": m.nome, "pedido": m.id, "canonico": m.canonico, "provider": V.roteamento(acesso, m),
                     "formato": m.formato, "params": m.params,
                     "servidos": sorted(s for s in servidos.get(m.nome, set()) if s),
                     "provedores_servidos": sorted(s for s in provedores.get(m.nome, set()) if s),
                     "custo_usd": round(custo.get(m.nome, 0), 6)} for m in modelos],
        "condicoes": {modo: P.hash_condicao(modo) for modo in P.MODOS},
        "semente_catalogo": P.SEMENTE_CATALOGO,
        "primeira_chamada": min((d for d in datas if d), default=None),
        "ultima_chamada": max((d for d in datas if d), default=None),
        "fontes": {"pdvlaravel_commit": E.PDVLARAVEL_COMMIT, "variantes": f"tools-cs-php {E.VARIANTES_RELEASE}"},
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("comando", choices=["preparar", "testar", "estimar", "modelos", "conta", "rodar", "resumo"])
    p.add_argument("--modelo", help="só este modelo (nome em modelos.yaml)")
    p.add_argument("--modo", choices=P.MODOS, help="só este modo")
    p.add_argument("--entrada", nargs="+", help="só estas entradas (ex.: base C13-v1)")
    p.add_argument("--cs", nargs="+", help="só as variantes destes CS (ex.: C01 C05,C07 C11-C17)")
    p.add_argument("--amostra", choices=["teste", "piloto"],
                   help="teste: só a linha de base; piloto: a amostra da L7")
    p.add_argument("--refazer", action="store_true", help="refaz respostas gravadas com hashes diferentes")
    p.add_argument("--sequencial", action="store_true", help="(rodar) uma chamada por vez, sem filas em paralelo")
    p.add_argument("--mostrar", help="(testar) imprime o prompt desta entrada")
    args = p.parse_args()
    carregar_env()
    return {"preparar": cmd_preparar, "testar": cmd_testar, "estimar": cmd_estimar,
            "modelos": cmd_modelos, "conta": cmd_conta, "rodar": cmd_rodar, "resumo": cmd_resumo}[args.comando](args)


if __name__ == "__main__":
    sys.exit(main())
