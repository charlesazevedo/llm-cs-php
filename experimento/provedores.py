"""Chamadas aos modelos pelo OpenRouter (decisões D10 e L5b).

Todos os modelos são chamados pela API do OpenRouter (https://openrouter.ai/api/v1),
que segue a da OpenAI, com o SDK `openai` e uma chave só (OPENROUTER_API_KEY). A
versão anterior, com um bloco por provedor e quatro chaves, está no histórico do
git (commit 68375ad).

Por padrão, o OpenRouter escolhe o provedor pelo preço, balanceia a carga, faz
fallback para outro provedor e ignora em silêncio os parâmetros que o provedor
não suporta. Para o experimento, cada chamada fixa o provedor de origem do
modelo e desliga isso tudo:

    provider = {"order": [p], "allow_fallbacks": False, "require_parameters": True}

Com `require_parameters`, a chamada só vai a um provedor que aceite todos os
parâmetros enviados (saída estruturada, temperatura); se o provedor fixado não
aceitar, a chamada falha, em vez de seguir sem eles. Nenhuma lista `models` de
fallback é enviada: se um modelo recusar, a recusa fica registrada como resposta
dele.

A conta do OpenRouter pode ligar plugins por padrão (correção de JSON, compressão
do meio do prompt, busca na web) e o cache de respostas; os dois mudariam o que
o modelo recebe ou o que ele devolve. Toda chamada desliga os plugins e o cache
explicitamente e pede os metadados de roteamento, que são gravados com a
resposta: por eles se confere que a chamada foi ao provedor fixado, na primeira
tentativa, sem nenhum plugin no caminho (ver `desvios`). A moderação de entrada
que o OpenRouter exige nos endpoints da OpenAI e da Anthropic (feita pela API de
moderação da OpenAI) não conta como desvio quando não sinaliza nada: ela não
muda a entrada nem a resposta.

Repetição: o SDK reenvia sozinho um pedido que passou do tempo limite, e um
pedido que o servidor terminou depois disso seria cobrado duas vezes. Por isso
o SDK fica sem repetição (`max_retries=0`), o tempo limite é longo
(TEMPO_LIMITE) e só se tenta de novo, aqui, o que foi recusado antes de o
modelo gerar qualquer coisa e não é cobrado: limite de requisições do
fabricante (429), reserva de crédito das chamadas em andamento cheia (402
`in_flight_budget_exhausted`) e erro do servidor (5xx). O erro do servidor vale
também quando o OpenRouter o devolve dentro de uma resposta 200 sem nenhuma
escolha do modelo (`SemResposta`, ex.: 502 `provider_unavailable`, "servers
overloaded"), que não é cobrada. Um tempo limite, uma conexão caída ou uma
resposta sem escolha e sem código repetível viram erro, e a chamada é refeita
na próxima rodada.

O prompt, o esquema e o prompt de sistema são os mesmos para todos. O que pode
mudar é o formato pedido ao provedor: `json_schema` (esquema validado) onde o
provedor fixado aceita saída estruturada, e `json_object` (só JSON válido) onde
não aceita, como o da DeepSeek; o formato também está no texto do prompt.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from dataclasses import dataclass, field

from prompts import SISTEMA

CATALOGO = "https://openrouter.ai/api/v1/models"
FORMATOS = {"json_schema": "structured_outputs", "json_object": "response_format"}  # formato -> parâmetro exigido
PLUGINS = ("web", "file-parser", "response-healing", "context-compression")
CABECALHOS = {"X-OpenRouter-Cache": "false", "X-OpenRouter-Metadata": "enabled"}
TEMPO_LIMITE = 1200   # segundos sem resposta antes de desistir; a chamada mais longa do teste levou 134 s
TENTATIVAS = 6        # para as recusas que não são cobradas (ver `espera`)


@dataclass
class Modelo:
    nome: str
    id: str                              # slug do OpenRouter (<autor>/<modelo>), nunca um apelido "latest"
    provedor: str                        # endpoint fixado (slug do OpenRouter, ex.: "anthropic")
    formato: str = "json_schema"         # chave de FORMATOS
    params: dict = field(default_factory=dict)
    canonico: str | None = None          # slug datado do snapshot, conferido pelo `modelos`
    data_collection: str | None = None   # "allow"/"deny" só para este modelo; None = o de `acesso`
    preco_entrada: float | None = None   # US$ por milhão de tokens, no provedor fixado
    preco_saida: float | None = None


@dataclass
class Acesso:
    api: str
    env: str
    data_collection: str | None = None   # "deny" exclui provedores que podem guardar ou treinar; None = padrão da conta

    def chave(self) -> str:
        valor = os.environ.get(self.env)
        if not valor:
            raise RuntimeError(f"{self.env} não definida (veja experimento/.env.example)")
        return valor


def roteamento(acesso: Acesso, modelo: Modelo) -> dict:
    rota = {"order": [modelo.provedor], "allow_fallbacks": False, "require_parameters": True}
    politica = modelo.data_collection or acesso.data_collection
    if politica:
        rota["data_collection"] = politica
    return rota


def corpo_extra(acesso: Acesso, modelo: Modelo) -> dict:
    """O que vai além dos campos da API da OpenAI: a rota e os plugins desligados."""
    return {"provider": roteamento(acesso, modelo),
            "plugins": [{"id": p, "enabled": False} for p in PLUGINS]}


def formato(modelo: Modelo, esquema: dict) -> dict:
    if modelo.formato == "json_object":
        return {"type": "json_object"}
    return {"type": "json_schema", "json_schema": {"name": "resposta", "schema": esquema, "strict": True}}


def _simples(valor):
    """Campos fora do esquema da OpenAI chegam como dict ou como objeto do SDK."""
    return valor.model_dump() if hasattr(valor, "model_dump") else valor


def espera(erro, tentativa: int) -> float | None:
    """Segundos até a próxima tentativa, ou None se não é seguro repetir (ver o início do módulo)."""
    status = getattr(erro, "status_code", None) or 0
    corpo = getattr(erro, "body", None)
    if isinstance(corpo, dict) and isinstance(corpo.get("error"), dict):
        corpo = corpo["error"]
    motivo = (corpo.get("metadata") or {}).get("reason") if isinstance(corpo, dict) else None
    if not (status == 429 or status >= 500 or (status == 402 and motivo == "in_flight_budget_exhausted")):
        return None
    cabecalhos = getattr(getattr(erro, "response", None), "headers", None) or {}
    try:
        return max(1.0, float(cabecalhos.get("retry-after")))
    except (TypeError, ValueError):
        return float(min(300, 10 * 2 ** (tentativa - 1)))


class SemResposta(RuntimeError):
    """O OpenRouter respondeu 200 sem nenhuma escolha do modelo: sem modelo servido, tokens nem texto.
    O erro que vier no corpo dá o `status_code` e o `body`, como num APIStatusError, para `espera`."""

    def __init__(self, mensagem: str, erro=None):
        super().__init__(mensagem)
        self.body = erro if isinstance(erro, dict) else None
        codigo = erro.get("code") if isinstance(erro, dict) else None
        self.status_code = codigo if isinstance(codigo, int) else 0


def chamar(acesso: Acesso, modelo: Modelo, prompt: str, esquema: dict, max_tokens: int, aviso=None):
    """Uma chamada; devolve (texto, metadados). `aviso(texto)`, se dado, recebe as novas tentativas."""
    from openai import APIStatusError, OpenAI

    cliente = OpenAI(api_key=acesso.chave(), base_url=acesso.api, timeout=TEMPO_LIMITE, max_retries=0)
    recusas = []
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            r = cliente.chat.completions.create(
                model=modelo.id,
                messages=[{"role": "system", "content": SISTEMA}, {"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                response_format=formato(modelo, esquema),
                extra_body=corpo_extra(acesso, modelo),
                extra_headers=CABECALHOS,
                **modelo.params,
            )
            if not r.choices:
                # 200 sem nenhuma escolha do modelo (um erro do provedor no corpo): não é resposta do
                # modelo e não é gravada; com código repetível (5xx, 429), tenta de novo como os outros.
                erro = _simples(getattr(r, "error", None))
                raise SemResposta(f"o OpenRouter respondeu sem resposta do modelo (id {r.id}): "
                                  f"{erro or 'sem detalhe'}", erro)
            break
        except (APIStatusError, SemResposta) as erro:
            pausa = espera(erro, tentativa)
            if pausa is None or tentativa == TENTATIVAS:
                raise
            recusas.append({"status": erro.status_code, "espera_s": pausa,
                            **({"sem_resposta": True} if isinstance(erro, SemResposta) else {})})
            if aviso:
                tipo = "sem resposta do modelo" if isinstance(erro, SemResposta) else "recusada"
                aviso(f"{tipo} ({erro.status_code}, sem custo); nova tentativa em {pausa:.0f} s")
            time.sleep(pausa)
    uso = r.usage
    detalhes = getattr(uso, "completion_tokens_details", None) if uso else None
    escolha = r.choices[0] if r.choices else None
    mensagem = escolha.message if escolha else None
    return (mensagem.content if mensagem else "") or "", {
        "modelo_servido": r.model,
        "provedor_servido": getattr(r, "provider", None),
        "stop_reason": escolha.finish_reason if escolha else None,
        "stop_reason_nativo": getattr(escolha, "native_finish_reason", None),
        "recusa": getattr(mensagem, "refusal", None),
        "tokens_entrada": uso.prompt_tokens if uso else None,
        "tokens_saida": uso.completion_tokens if uso else None,
        "tokens_raciocinio": getattr(detalhes, "reasoning_tokens", None),
        "custo": getattr(uso, "cost", None),
        "id_requisicao": r.id,
        "roteamento": _simples(getattr(r, "openrouter_metadata", None)),
        "recusas_antes": recusas,
        "espera_s": sum(x["espera_s"] for x in recusas),
    }


def desvios(modelo: Modelo, meta: dict) -> list[str]:
    """O que nos metadados indica que a chamada não foi como pedida."""
    rota = meta.get("roteamento")
    if not rota:
        return ["sem metadados de roteamento"]
    achados = []
    if (rota.get("attempt") or 1) > 1:
        achados.append(f"tentativa {rota['attempt']}")
    if rota.get("is_byok"):
        achados.append("chave própria (BYOK)")
    for etapa in rota.get("pipeline") or []:
        # A moderação que o OpenRouter exige nos endpoints da OpenAI e da Anthropic só
        # examina a entrada; se não a sinaliza, a chamada segue sem mudança. Sinalizada,
        # a chamada é recusada antes do modelo e vira erro, sem resposta gravada.
        if etapa.get("type") == "guardrail" and (etapa.get("data") or {}).get("flagged") is False:
            continue
        achados.append(f"plugin {etapa.get('name') or etapa.get('type')}")
    escolhidos = [e for e in (rota.get("endpoints") or {}).get("available") or [] if e.get("selected")]
    nome = (meta.get("provedor_servido") or (escolhidos[0].get("provider") if escolhidos else "") or "")
    if nome.lower().replace(" ", "-") != modelo.provedor.split("/")[0]:
        achados.append(f"servido por {nome or '?'}")
    return achados


def _ler(url: str, chave: str | None = None):
    pedido = urllib.request.Request(url, headers={"Authorization": f"Bearer {chave}"} if chave else {})
    with urllib.request.urlopen(pedido, timeout=60) as r:
        return json.load(r)["data"]


def chave_info(acesso: Acesso) -> dict:
    """GET /api/v1/key: limite de gasto e uso da chave. Não é chamada de inferência e não custa nada."""
    return _ler(acesso.api.rstrip("/") + "/key", acesso.chave())


def catalogo() -> dict[str, dict]:
    """O catálogo público do OpenRouter (não precisa de chave), por id do modelo."""
    return {m["id"]: m for m in _ler(CATALOGO)}


def endpoints(modelo_id: str) -> list[dict]:
    """Os endpoints (provedor, variante) que servem o modelo, com parâmetros e preços."""
    return _ler(f"{CATALOGO}/{modelo_id}/endpoints")["endpoints"]
