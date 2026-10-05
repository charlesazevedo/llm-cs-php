#!/usr/bin/env python3
"""Relatório das respostas gravadas, para entender um teste ou o piloto sem abrir os JSON.

Responde, em ordem: as chamadas foram como configuradas? as respostas vieram
inteiras e utilizáveis? o que cada modelo apontou? quanto custou e quanto vão
custar o piloto e a execução completa? O que pede atenção vem no começo, com o
que fazer. Só lê arquivos: não faz chamada nenhuma e não usa a chave.

Uso, da raiz do repositório (ou pelo experimento/compilar-resultados.sh):

    uv run --no-project --with-requirements experimento/requirements.txt \\
        python experimento/relatorio.py --amostra teste

Grava experimento/resultados/relatorio-<amostra>[-<modelo>][-<modo>].md
(relatorio.md sem filtro)
e imprime o resumo. Aceita os filtros do harness: --amostra, --modelo, --modo,
--entrada. Sai com código 1 se alguma resposta pedir atenção.
"""

from __future__ import annotations

import argparse
import re
import sys
import zlib
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import entradas as E  # noqa: E402
import harness as H  # noqa: E402
import prompts as P  # noqa: E402
import provedores as V  # noqa: E402
import sinonimos as S  # noqa: E402

OK, ATENCAO, FALHA = "✅", "⚠️", "❌"
NOME_MODO = {"aberto": "aberto", "forcado": "forçado"}


def num(x, casas=0) -> str:
    """Número no formato brasileiro: 1.234,5."""
    texto = f"{x:,.{casas}f}"
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


def dinheiro(x) -> str:
    return "US$ " + num(x or 0, 4 if (x or 0) < 1 else 2)


# --------------------------------------------------------------------------
# Leitura e diagnóstico de cada resposta
# --------------------------------------------------------------------------

def snapshot_servido(r: dict) -> str | None:
    """O snapshot datado que atendeu, pelos metadados de roteamento (o campo `model` da resposta
    traz o slug pedido, sem data)."""
    rota = r.get("roteamento") or {}
    for e in (rota.get("endpoints") or {}).get("available") or []:
        if e.get("selected"):
            return e.get("model")
    return None


def em_laco(texto: str) -> bool:
    """Se o fim do texto é a repetição de um mesmo trecho: comprimido, ele quase some.
    Um JSON comum cortado no meio comprime a uns 30%; um laço, a menos de 8%."""
    fim = (texto or "")[-4000:]
    return len(fim) >= 2000 and len(zlib.compress(fim.encode("utf-8"))) / len(fim.encode("utf-8")) < 0.08


def citados(modo: str, resp: dict, catalogo: list[dict], sinonimos: list[dict]) -> list[dict]:
    """Os CS que a resposta aponta, cada um com o casamento no catálogo."""
    itens = []
    if modo == "aberto":
        for s in resp.get("smells") or []:
            casou = S.casar(str(s.get("nome") or ""), sinonimos)
            itens.append({"nome": s.get("nome"), "especifico": sorted(casou["especifico"]),
                          "amplo": sorted(casou["amplo"] - casou["especifico"]),
                          "trechos": [s], "justificativa": s.get("justificativa")})
    else:
        for a in resp.get("avaliacoes") or []:
            n = a.get("item")
            if not a.get("presente") or not isinstance(n, int) or not 1 <= n <= len(catalogo):
                continue
            c = catalogo[n - 1]
            itens.append({"nome": f"item {n}: {c['nome']}", "especifico": [c["id"]], "amplo": [],
                          "trechos": a.get("trechos") or [], "justificativa": a.get("justificativa")})
    return itens


def diagnosticar(m: V.Modelo, modo: str, e: E.Entrada, estado: str, r: dict | None, cfg: dict,
                 acesso: V.Acesso, catalogo: list[dict], sinonimos: list[dict]) -> dict:
    d = {"modelo": m, "modo": modo, "entrada": e, "estado": estado, "r": r, "alertas": []}
    if r is None:          # as que faltam viram um alerta só, em `montar`
        return d
    if estado == "falha":  # gravada sem resposta do modelo: um alerta só, sem os de rota e de JSON
        d["alertas"].append((FALHA, "o OpenRouter respondeu sem resposta do modelo (sem modelo servido, tokens "
                             "nem texto); não é resposta do modelo",
                             "rodar de novo: o `rodar` refaz essa chamada sozinho, sem `--refazer`"))
        d["r"] = None      # nas tabelas, conta como uma resposta que falta
        return d
    if estado == "desatualizada":   # as desatualizadas viram um alerta por motivo, em `montar`
        d["mudou"] = H.diferencas(m, V.roteamento(acesso, m), modo, e, cfg["max_tokens"], r)
    # 1. rota
    desvios = V.desvios(m, r)   # recalculado dos metadados gravados, com a regra atual
    snap = snapshot_servido(r)
    d["rota_ok"] = not desvios
    d["snapshot"] = snap
    d["snapshot_ok"] = bool(snap) and (not m.canonico or snap == m.canonico)
    if desvios:
        d["alertas"].append((FALHA, f"desvio de rota: {'; '.join(desvios)}",
                             "não usar a resposta; ver os metadados de roteamento no JSON"))
    if snap and m.canonico and snap != m.canonico:
        d["alertas"].append((ATENCAO, f"o snapshot servido ({snap}) não é o de modelos.yaml ({m.canonico})",
                             "rodar `harness.py modelos` e decidir se o snapshot novo vale"))
    # 2. resposta
    resp = r.get("resposta")
    d["json_ok"] = isinstance(resp, dict)
    d["cortada"] = r.get("stop_reason") == "length"
    d["completa"] = d["json_ok"] and not d["cortada"]
    d["laco"] = d["cortada"] and not d["json_ok"] and em_laco(r.get("texto_bruto"))
    if d["laco"]:
        avaliados = len(re.findall(r'"item"\s*:\s*\d+', r.get("texto_bruto") or ""))
        d["alertas"].append((ATENCAO,
            "a resposta entrou em laço: " + (f"depois de {avaliados} itens avaliados, " if avaliados else "")
            + f"repetiu o mesmo trecho até o limite de {num(r.get('max_tokens') or cfg['max_tokens'])} tokens "
            f"({num((r.get('tokens_saida') or 0) - (r.get('tokens_raciocinio') or 0))} de texto), e o JSON ficou incompleto",
            "nada: pelo protocolo, conta como resposta do modelo, inválida, e o CS como não detectado "
            "(decisão do autor, 03/10/2026); aumentar o limite não resolve um laço"))
    elif d["cortada"]:
        rac = r.get("tokens_raciocinio") or 0
        d["alertas"].append((FALHA,
            f"resposta cortada no limite de {num(r.get('max_tokens') or cfg['max_tokens'])} tokens de saída "
            f"({num(rac)} deles de raciocínio, {num((r.get('tokens_saida') or 0) - rac)} de texto)"
            + ("; o JSON ficou incompleto e a resposta não serve" if not d["json_ok"] else ""),
            "decidir entre aumentar `max_tokens` em modelos.yaml (o `harness.py modelos` mostra o máximo de cada "
            "endpoint) ou limitar o raciocínio deste modelo; depois, `rodar ... --refazer`"))
    elif not d["json_ok"]:
        d["alertas"].append((FALHA, f"JSON inválido: {r.get('erro_json')}",
                             "ver `texto_bruto` no JSON; pelo protocolo, conta como resposta do modelo"))
    if r.get("recusa"):
        d["alertas"].append((ATENCAO, f"o modelo recusou: {r['recusa']}", "registrar; conta como resposta"))
    d["itens"] = citados(modo, resp, catalogo, sinonimos) if d["json_ok"] else []
    if d["json_ok"] and modo == "forcado":
        numeros = sorted(a.get("item") for a in resp.get("avaliacoes") or [] if isinstance(a.get("item"), int))
        d["avaliados"] = len(resp.get("avaliacoes") or [])
        if numeros != list(range(1, len(catalogo) + 1)):
            d["alertas"].append((ATENCAO, f"avaliou {d['avaliados']} itens, e não os {len(catalogo)} do catálogo "
                                 "uma vez cada", "ver a resposta; pode ser preciso reforçar o prompt"))
    trechos = [t for i in d["itens"] for t in i["trechos"]]
    d["trechos"] = len(trechos)
    d["trechos_ruins"] = H._trechos_ruins(trechos, e) if trechos else 0
    if d["trechos_ruins"]:
        d["alertas"].append((ATENCAO, f"{d['trechos_ruins']} de {len(trechos)} trecho(s) apontam um arquivo que não "
                             "está na entrada ou linhas fora dele", "ver os trechos no detalhe da resposta"))
    return d


# --------------------------------------------------------------------------
# Relatório
# --------------------------------------------------------------------------

def injetado_apontado(d: dict) -> str | None:
    """"especifico" se a resposta nomeia o CS injetado (no aberto, por um sinônimo específico; no forçado,
    pelo item); "amplo" se só um nome amplo o cobre (vai para o julgamento manual, L10); None se não.
    É só uma prévia: o critério da D4 também confere as linhas e a linha de base (L9)."""
    cid = d["entrada"].cs_id
    if not cid:
        return None
    if any(cid in i["especifico"] for i in d.get("itens", [])):
        return "especifico"
    if any(cid in i["amplo"] for i in d.get("itens", [])):
        return "amplo"
    return None


def tabela(cabecalho: list[str], linhas: list[list]) -> list[str]:
    saida = ["| " + " | ".join(cabecalho) + " |", "|" + "|".join("---" for _ in cabecalho) + "|"]
    saida += ["| " + " | ".join(str(c) for c in l) + " |" for l in linhas]
    return saida + [""]


def tempo_txt(est: dict) -> str:
    if not est["falta"] and est["gravadas"] == est["chamadas"]:
        return "nada (já está completo)"
    return H.aprox(est["tempo_falta_paralelo"])


def marca(cond) -> str:
    return OK if cond else FALHA


def montar(args) -> tuple[list[str], list[str], str, bool]:
    cfg, acesso, configurados = H.carregar_config()
    todas = E.montar()
    entradas, modelos, modos = H.selecionar(todas, configurados, args)
    catalogo = P.ordem_do_catalogo()
    por_id = {c["id"]: c for c in catalogo}
    sinonimos = S.carregar()
    diags = []
    for e in entradas:
        for m in modelos:
            for modo in modos:
                estado, r = H.situacao(m, V.roteamento(acesso, m), modo, e, cfg["max_tokens"])
                diags.append(diagnosticar(m, modo, e, estado, r, cfg, acesso, catalogo, sinonimos))
    gravadas = [d for d in diags if d["r"]]
    alertas = [(d, a) for d in diags for a in d["alertas"]]
    motivos = {}
    for d in diags:
        if d.get("mudou"):
            motivos.setdefault(", ".join(d["mudou"]), []).append(d)
    for motivo, grupo in reversed(list(motivos.items())):
        quais = ", ".join(f"{d['modelo'].nome} {NOME_MODO[d['modo']]} {d['entrada'].id}" for d in grupo)
        alertas.insert(0, ({"modelo": None}, (
            ATENCAO, f"{len(grupo)} resposta(s) desatualizada(s), porque mudou {motivo} depois delas ({quais}); "
            "o que está abaixo é delas, até serem refeitas",
            "refazer com o `teste-linha-de-base.sh` (ou `rodar ... --refazer`), que mostra o custo antes")))
    faltam = [d for d in diags if not d["r"]]
    if faltam:
        por_grupo = {}
        for d in faltam:
            por_grupo[d["modelo"].nome, NOME_MODO[d["modo"]]] = por_grupo.get((d["modelo"].nome, NOME_MODO[d["modo"]]), 0) + 1
        alertas.insert(0, ({"modelo": None, "titulo": "Respostas que faltam"}, (
            ATENCAO if len(faltam) < len(diags) else FALHA,
            f"{len(faltam)} de {len(diags)} respostas ainda não estão gravadas ("
            + ", ".join(f"{nm} {md}: {q}" for (nm, md), q in por_grupo.items()) + ")",
            "se a amostra ainda não rodou, é esperado; se rodou, as que faltam deram erro na chamada (o `rodar` "
            "mostra o erro) e são refeitas na próxima rodada, sem custo para as já gravadas")))
    custo = sum(d["r"].get("custo") or 0 for d in gravadas)
    antes = H.estimativa(cfg, acesso, modelos, entradas, modos, usar_gravadas=False)
    piloto = H.estimativa(cfg, acesso, configurados, H.amostra_piloto(todas), list(P.MODOS))
    completa = H.estimativa(cfg, acesso, configurados, todas, list(P.MODOS))
    saida_total = sum(d["r"].get("tokens_saida") or 0 for d in gravadas)
    raciocinio = sum(d["r"].get("tokens_raciocinio") or 0 for d in gravadas)

    cs = "cs-" + "_".join(",".join(args.cs).replace(",", "_").split()) if args.cs else None
    nome = "-".join(x.lower() for x in (args.amostra or "selecao", cs, args.modelo, args.modo) if x)
    titulo = {"teste": "Resultado do teste (linha de base)", "piloto": "Resultado do piloto"}.get(args.amostra,
                                                                                                "Resultado")
    linhas = [f"# {titulo}", "",
              f"Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')} por `experimento/relatorio.py`, a partir de "
              f"`experimento/resultados/respostas/`: {len(gravadas)} de {len(diags)} respostas esperadas "
              f"({len(entradas)} entrada(s) x {len(modelos)} modelos x {len(modos)} modo(s)). "
              "O relatório só lê os arquivos; não faz chamada nenhuma.", ""]

    # --- Em resumo
    variantes = [e for e in entradas if e.cs_id]
    if not variantes:
        apontaram = "🔎 **O que apontaram:** " + "; ".join(
            f"modo {NOME_MODO[modo]}: " + ", ".join(
                f"{d['modelo'].nome} {len(d['itens'])}"
                + (f" ({sum(1 for i in d['itens'] if i['especifico'])} do catálogo)" if modo == "aberto" else "")
                for d in gravadas if d["modo"] == modo and d["json_ok"])
            for modo in modos if any(d["modo"] == modo and d["json_ok"] for d in gravadas)) + " (detalhe na seção 3)."
    else:
        partes = []
        for modo in modos:
            contagem = []
            for m in modelos:
                ds = [d for d in diags if d["modelo"] is m and d["modo"] == modo and d["entrada"].cs_id and d["r"]]
                acertos = sum(1 for d in ds if injetado_apontado(d) == "especifico")
                amplos = sum(1 for d in ds if injetado_apontado(d) == "amplo")
                contagem.append(f"{m.nome} {acertos}" + (f" (+{amplos} por nome amplo)" if amplos else ""))
            partes.append(f"modo {NOME_MODO[modo]}: " + ", ".join(contagem))
        apontaram = (f"🎯 **CS injetado apontado** (prévia, das {len(variantes)} variantes, sem conferir as linhas): "
                     + "; ".join(partes) + " (tabela na seção 3).")
    n = len(diags)
    desatualizadas = sum(1 for d in diags if d["estado"] == "desatualizada")
    rota_ok = sum(1 for d in gravadas if d.get("rota_ok") and d.get("snapshot_ok"))
    completas = sum(1 for d in gravadas if d.get("completa"))
    resumo = [
        f"{marca(len(gravadas) == n and not desatualizadas)} **Respostas gravadas:** {len(gravadas)} de {n}"
        + (f", {desatualizadas} delas desatualizadas (ver abaixo)" if desatualizadas else "") + ".",
        f"{marca(rota_ok == len(gravadas))} **Rota:** {rota_ok} de {len(gravadas)} foram atendidas pelo provedor "
        "fixado, na primeira tentativa, sem plugin e pelo snapshot de `modelos.yaml`.",
        f"{marca(completas == len(gravadas))} **Respostas inteiras:** {completas} de {len(gravadas)} vieram completas "
        "e em JSON válido.",
        apontaram,
        f"💲 **Custo:** {dinheiro(custo)}, contra {dinheiro(antes['total'])} estimados antes (a estimativa supunha a "
        f"saída sem raciocínio). Os tokens de raciocínio foram {num(100 * raciocinio / saida_total if saida_total else 0)}% "
        "da saída, e são cobrados como saída.",
        f"🔮 **Projeção com os tokens medidos:** piloto ~{dinheiro(piloto['total'])} "
        f"(faltam ~{dinheiro(piloto['falta'])}); execução completa ~{dinheiro(completa['total'])} "
        f"(faltam ~{dinheiro(completa['falta'])}), mais a taxa da compra dos créditos. Tempo do que falta, com "
        f"uma fila por modelo em paralelo: piloto {tempo_txt(piloto)}, execução completa {tempo_txt(completa)}.",
    ]
    linhas += ["## Em resumo", ""] + [f"- {x}" for x in resumo] + [""]

    # --- Atenção
    linhas += ["## O que pede atenção", ""]
    if alertas:
        for i, (d, (simbolo, o_que, fazer)) in enumerate(alertas, 1):
            onde = (f"**{d['modelo'].nome}, modo {NOME_MODO[d['modo']]}, {d['entrada'].id}:** " if d["modelo"]
                    else f"**{d.get('titulo', 'Respostas desatualizadas')}:** ")
            linhas.append(f"{i}. {simbolo} {onde}{o_que}. *O que fazer:* {fazer}.")
        linhas.append("")
    else:
        linhas += [f"{OK} Nada: todas as respostas vieram como esperado.", ""]

    # --- 1. Rota
    linhas += ["## 1. As chamadas foram como configuradas?", "",
               "Cada modelo tem o provedor fixado em `modelos.yaml`, sem troca por outro e com os plugins e o cache "
               "do OpenRouter desligados. Os metadados de roteamento de cada resposta dizem quem atendeu.", ""]
    linhas += tabela(["Modelo", "Modo", "Entrada", "Provedor fixado", "Quem atendeu", "Snapshot servido", "Ok?"],
                     [[d["modelo"].nome, NOME_MODO[d["modo"]], d["entrada"].id, d["modelo"].provedor,
                       d["r"].get("provedor_servido"), f"`{d['snapshot']}`" if d["snapshot"] else "?",
                       marca(d["rota_ok"] and d["snapshot_ok"])] for d in gravadas])

    # --- 2. Respostas
    linhas += ["## 2. As respostas vieram inteiras e utilizáveis?", "",
               "*Fim* é o motivo de parada: `stop` é o normal; `length` quer dizer que a resposta bateu no limite de "
               f"tokens de saída (`max_tokens`, hoje {num(cfg['max_tokens'])}) e foi cortada. No modo forçado, a "
               f"resposta tem de avaliar os {len(catalogo)} itens do catálogo. *Trechos* são os intervalos de linhas "
               "apontados; fora do arquivo é sinal de que o modelo errou a numeração.", ""]
    linhas += tabela(["Modelo", "Modo", "Entrada", "Fim", "JSON", "Conteúdo", "Trechos fora do arquivo"],
                     [[d["modelo"].nome, NOME_MODO[d["modo"]], d["entrada"].id,
                       f"{marca(not d['cortada'])} {d['r'].get('stop_reason')}", marca(d["json_ok"]),
                       (f"{len(d['itens'])} CS citados" if d["modo"] == "aberto"
                        else f"{d.get('avaliados', 0)} itens avaliados, {len(d['itens'])} presentes")
                       if d["json_ok"] else "—",
                       f"{d['trechos_ruins']} de {d['trechos']}" if d["json_ok"] else "—"] for d in gravadas])

    # --- 3. O que os modelos apontaram
    linhas += ["## 3. O que cada modelo apontou", ""]
    variantes = [e for e in entradas if e.cs_id]
    if variantes:
        linhas += ["### O CS injetado foi apontado? (prévia)", "",
                   "✓ = a resposta nomeia o CS injetado: no modo aberto, por um sinônimo específico da lista; no "
                   "forçado, marcando o item dele. ≈ = só um nome amplo o cobre (por exemplo, *Large Class* para "
                   "*Excessive Class Length*, *Dead Code* para *Unused Private Field*), que pela D4 vai para o "
                   "julgamento manual (L10). – = não nomeou; ? = sem resposta válida. \\* = a linha de base, no "
                   "mesmo modelo e modo, também aponta esse CS: ele já existe no código original, e só as linhas "
                   "dizem se a resposta aponta o trecho injetado. É uma prévia: ainda não confere as linhas nem "
                   "desconta a linha de base, que é o critério completo da D4 (L9).", ""]
        cab = ["Entrada", "CS injetado"] + [f"{m.nome} {NOME_MODO[modo][:2]}." for m in modelos for modo in modos]
        corpo = []
        for e in variantes:
            linha = [e.id, f"{e.cs_id} {por_id[e.cs_id]['nome']}"]
            for m in modelos:
                for modo in modos:
                    d = next(x for x in diags if x["entrada"] is e and x["modelo"] is m and x["modo"] == modo)
                    marca_ = ("?" if not d["r"] or not d.get("json_ok")
                              else {"especifico": "✓", "amplo": "≈"}.get(injetado_apontado(d), "–"))
                    base = next((x for x in diags if x["entrada"].id == "base" and x["modelo"] is m
                                 and x["modo"] == modo), None)
                    if marca_ in ("✓", "≈") and base and any(e.cs_id in i["especifico"] + i["amplo"]
                                                            for i in base.get("itens", [])):
                        marca_ += "*"
                    linha.append(marca_)
            corpo.append(linha)
        totais = ["**Total**", ""]
        for m in modelos:
            for modo in modos:
                ds = [d for d in diags if d["entrada"].cs_id and d["modelo"] is m and d["modo"] == modo]
                certos = sum(1 for d in ds if d["r"] and injetado_apontado(d) == "especifico")
                amplos = sum(1 for d in ds if d["r"] and injetado_apontado(d) == "amplo")
                totais.append(f"{certos}/{len(ds)}" + (f" (+{amplos} ≈)" if amplos else ""))
        linhas += tabela(cab, corpo + [totais])
        linhas += ["Legenda: *ab.* = modo aberto; *fo.* = modo forçado. Abaixo, por entrada, todos os CS do catálogo "
                   "que cada modelo apontou.", ""]
    if any(e.id == "base" for e in entradas):
        linhas += ["A **linha de base** é a `CaixaController` sem nenhum CS injetado. O que os modelos apontam nela "
                   "são CS que já existem no código original do PDVLaravel, ou falsos positivos. Isso é esperado, e "
                   "é por isso que ela existe: pelo critério da D4, um CS só conta como detectado numa variante se a "
                   "linha de base não o apontar no mesmo lugar.", ""]
    linhas += ["No modo **aberto**, o nome dado pelo modelo é casado com o catálogo pela lista de sinônimos "
               "(`dados/sinonimos.csv`). No modo **forçado**, o modelo marca os itens do próprio catálogo. "
               "✓ = apontou; a coluna *Cód.* é o id no catálogo.", ""]
    nomes_modelos = [m.nome for m in modelos]
    for e in entradas:
        injetado = e.cs_id
        for modo in modos:
            ds = [d for d in diags if d["entrada"] is e and d["modo"] == modo]
            apontados = {}
            for d in ds:
                for i in d.get("itens", []):
                    for cid in i["especifico"]:
                        apontados.setdefault(cid, set()).add(d["modelo"].nome)
            linhas += [f"### {e.id}, modo {NOME_MODO[modo]}"
                       + (f" (CS injetado: {injetado} {por_id[injetado]['nome']})" if injetado else ""), ""]
            if not apontados:
                linhas += ["Nenhum CS do catálogo apontado.", ""]
            else:
                ordem = sorted(apontados, key=lambda c: (-len(apontados[c]), c))
                linhas += tabela(["Cód.", "CS", *nomes_modelos],
                                 [[c + (" ← injetado" if c == injetado else ""), por_id[c]["nome"],
                                   *("✓" if nm in apontados[c] else "" for nm in nomes_modelos)] for c in ordem])
            soltos = {}
            for d in ds:
                for i in d.get("itens", []):
                    if not i["especifico"]:
                        chave = (d["modelo"].nome, str(i["nome"]), tuple(i["amplo"]))
                        soltos[chave] = soltos.get(chave, 0) + 1
            if modo == "aberto" and soltos:
                linhas += ["Nomes que a lista de sinônimos não liga a um CS específico do catálogo. Os *amplos* "
                           "podem ser mais de um CS e vão para o julgamento manual (L10). Os *sem casamento* são CS "
                           "de fora do catálogo, problemas que não são CS (*bugs*, segurança, desempenho) ou "
                           "sinônimos que faltam na lista (L6):", ""]
                for nome_m in nomes_modelos:
                    grupo = [(nome_i, amplo, vezes) for (nm, nome_i, amplo), vezes in soltos.items() if nm == nome_m]
                    if grupo:
                        linhas.append(f"- **{nome_m}:** " + "; ".join(
                            f"*{nome_i}*" + (f" ({vezes}x)" if vezes > 1 else "")
                            + (f" (amplo: {', '.join(amplo)})" if amplo else "") for nome_i, amplo, vezes in grupo))
                linhas.append("")

    # --- 4. Custo
    linhas += ["## 4. Custo, tokens e tempo", "",
               "Tokens de saída incluem os de raciocínio, que o modelo gera antes da resposta e que são cobrados "
               "como saída. O custo é o que o OpenRouter cobrou em cada chamada.", ""]
    linhas += tabela(["Modelo", "Modo", "Entrada", "Tokens de entrada", "Tokens de saída", "dos quais raciocínio",
                      "Custo", "Tempo"],
                     [[d["modelo"].nome, NOME_MODO[d["modo"]], d["entrada"].id, num(d["r"].get("tokens_entrada") or 0),
                       num(d["r"].get("tokens_saida") or 0), num(d["r"].get("tokens_raciocinio") or 0),
                       dinheiro(d["r"].get("custo")), f"{num(d['r'].get('duracao_s') or 0, 1)} s"] for d in gravadas]
                     + [["**Total**", "", "", "", num(saida_total), num(raciocinio), f"**{dinheiro(custo)}**", ""]])
    linhas += ["Projeção, com a saída média medida por modelo e modo (e a entrada corrigida pela contagem real de "
               "cada provedor):", ""]
    linhas += tabela(["", "Chamadas", "Custo estimado", "Já gasto (não é refeito)", "Falta gastar",
                      "Tempo do que falta, em paralelo", "em sequência"],
                     [[nome_, num(x["chamadas"]), dinheiro(x["total"]), dinheiro(x["medido"]), dinheiro(x["falta"]),
                       H.em_horas(x["tempo_falta_paralelo"]), H.em_horas(x["tempo_falta_sequencial"])]
                      for nome_, x in (("Piloto (L7)", piloto), ("Execução completa (L8)", completa))])
    linhas += [f"A estimativa usa o maior preço de cada endpoint (o da DeepSeek muda com o horário) e não inclui a "
               f"taxa da compra de créditos com cartão ({num(100 * H.TAXA_CREDITOS, 1)}%, mínimo "
               f"US$ {num(H.TAXA_MINIMA, 2)}). Com uma resposta por modelo e modo, a média é só um indício: o piloto "
               "mede melhor. O tempo usa a duração média das respostas gravadas; cresce com o tamanho da entrada.", ""]

    # --- 5. Detalhes
    linhas += ["## 5. Detalhe de cada resposta", "",
               "O texto completo está em `experimento/resultados/respostas/<modelo>/<modo>/<entrada>.json`.", ""]
    for d in gravadas:
        r = d["r"]
        linhas += [f"<details><summary>{d['modelo'].nome}, modo {NOME_MODO[d['modo']]}, {d['entrada'].id}: "
                   + (f"{len(d['itens'])} CS" if d["json_ok"] else "JSON inválido") + "</summary>", ""]
        if not d["json_ok"]:
            bruto = r.get("texto_bruto") or ""
            linhas += [f"Erro: `{r.get('erro_json')}`. O texto tem {num(len(bruto))} caracteres; o fim dele:", "",
                       "```", bruto[-400:], "```", ""]
        for i in d["itens"]:
            faixas = ", ".join(f"{t.get('arquivo')}:{t.get('linha_inicio')}-{t.get('linha_fim')}" for t in i["trechos"])
            casamento = (", ".join(f"{c} {por_id[c]['nome']}" for c in i["especifico"]) if i["especifico"]
                         else (f"amplo: {', '.join(i['amplo'])}" if i["amplo"] else "sem casamento"))
            linhas.append(f"- **{i['nome']}** → {casamento}. {faixas or 'sem trecho'}"
                          + (f". *{i['justificativa']}*" if i.get("justificativa") else ""))
        linhas += ["", "</details>", ""]

    terminal = [titulo, ""] + [x.replace("**", "") for x in resumo] + [""]
    if alertas:
        terminal.append("O que pede atenção:")
        terminal += [f"  {simbolo} " + (f"{d['modelo'].nome}, {NOME_MODO[d['modo']]}, {d['entrada'].id}: "
                                         if d["modelo"] else "") + o_que for d, (simbolo, o_que, _) in alertas]
    else:
        terminal.append(f"{OK} Nada pede atenção.")
    return linhas, terminal, nome, bool(alertas)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--amostra", choices=["teste", "piloto"], help="teste: só a linha de base; piloto: a amostra da L7")
    p.add_argument("--modelo", help="só este modelo")
    p.add_argument("--modo", choices=P.MODOS, help="só este modo")
    p.add_argument("--entrada", nargs="+", help="só estas entradas")
    p.add_argument("--cs", nargs="+", help="só as variantes destes CS (ex.: C01 C05,C07 C11-C17)")
    p.add_argument("--saida", help="arquivo do relatório (padrão: experimento/resultados/relatorio-<amostra>.md)")
    args = p.parse_args()
    linhas, terminal, nome, ha_alertas = montar(args)
    filtrado = args.amostra or args.modelo or args.modo or args.cs
    destino = Path(args.saida) if args.saida else E.RESULTADOS / (f"relatorio-{nome}.md" if filtrado
                                                                   else "relatorio.md")
    destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    print("\n".join(terminal))
    try:
        mostrar = destino.resolve().relative_to(E.RAIZ)
    except ValueError:
        mostrar = destino
    print(f"\nRelatório completo em {mostrar}")
    return 1 if ha_alertas else 0


if __name__ == "__main__":
    sys.exit(main())
