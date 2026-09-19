"""Etiquetas da arvore do painel de informacoes do projeto.

A etiquetagem NAO mede nada: quem mede a arvore, as linguagens e as dependencias
e o motor deterministico (tools/projeto_info.py e tools/dependencias.py). Aqui a IA
so faz o que o motor
nao sabe fazer - dar um NOME curto ao papel de cada pasta/ficheiro, a partir do
docstring e dos imports que o motor ja sabe ler.

A chamada corre numa thread propria e e silenciosa: nao emite eventos, nao entra
no chat e nao toca no status. O painel acompanha-a por polling a
`estado_etiquetagem()`. So se etiqueta o que falta ou mudou - o que ja esta
etiquetado e cuja assinatura (mtime do ficheiro, nomes dos filhos da pasta) nao
mexeu fica como esta, e nem se chega a abrir o ficheiro para lhe ler o cabecalho.

A primeira etiquetagem de um projeto e automatica: sem nenhuma etiqueta gravada e
sem tentativa anterior, `estado_etiquetagem()` devolve `inicial=True` e o painel
dispara a operacao sozinho. O marco da tentativa vive no proprio ficheiro, por
projeto, logo a automaticidade acontece UMA vez - um erro de rede nao se
transforma num ciclo de tentativas a cada abertura do painel.
"""

import json
import os
import threading
import time

from src.backend.ai.base import gerar_texto
from src.backend.services.persistencia import gravar_json_atomico
from src.backend.state import estado, caminho_estado_projeto

NOME_FICHEIRO = "etiquetas.json"

TAMANHO_LOTE = 40
MAX_LOTES = 12

LINHAS_DE_CONTEXTO = 14
CHARS_DE_CONTEXTO = 500
FILHOS_NO_CONTEXTO = 24
CHARS_DA_ETIQUETA = 48

_lock = threading.Lock()

_INSTRUCAO = (
    "Etiquetas o PAPEL de cada pasta e ficheiro de um projeto de software. "
    "Para cada caminho recebido, responde com uma etiqueta curta (ate 5 palavras) "
    "que diga o que aquele no FAZ no projeto, nunca o que ele e: "
    "'pasta de codigo' nao serve; 'memoria do agente' serve. "
    "Escreve no infinitivo ou em substantivo tecnico, sem ponto final "
    "e sem o caracter #. "
    "Exemplos: \"src/backend/routes\" -> \"endpoints http\"; "
    "\"src/main.js\" -> \"processo electron\"; "
    "\"src/backend/memory/vector.py\" -> \"banco vetorial do palace\". "
    "Responde APENAS com um objeto JSON plano {\"caminho\": \"etiqueta\"}, "
    "com um par por caminho recebido, sem texto antes ou depois."
)


def _caminho_arquivo():
    return caminho_estado_projeto(NOME_FICHEIRO)


def _ler_arquivo():
    """Conteudo do ficheiro de etiquetas do projeto aberto ({} se nao existir)."""
    caminho = _caminho_arquivo()
    if not caminho or not os.path.exists(caminho):
        return {}
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    return dados if isinstance(dados, dict) else {}


def estado_etiquetagem():
    """Retrato para o painel: se esta a etiquetar, onde vai, e o que ja existe.

    `inicial` e o gatilho da primeira etiquetagem automatica: projeto sem
    nenhuma etiqueta e sem tentativa anterior. Vem do ficheiro (e nao de uma flag
    em RAM) para o painel nao repetir a operacao a cada abertura.
    """
    bruto = _ler_arquivo()
    nos = bruto.get("nos") if isinstance(bruto.get("nos"), dict) else {}
    return {
        "estado": "a_etiquetar" if estado.get("etiquetando") else "pronto",
        "progresso": estado.get("etiquetando_progresso", ""),
        "inicial": not nos and not bruto.get("tentado"),
        "nos": nos,
    }


def _gravar(nos, tentado=None):
    """Grava as etiquetas preservando o marco `tentado` (gatilho automatico)."""
    caminho = _caminho_arquivo()
    if not caminho:
        return False
    if tentado is None:
        tentado = _ler_arquivo().get("tentado")
    dados = {"versao": 1, "atualizado": time.time(), "nos": nos}
    if tentado:
        dados["tentado"] = tentado
    return gravar_json_atomico(caminho, dados)


def _limpar_tag(texto):
    """Tag de uma linha so, sem # nem pontuacao final e dentro do limite."""
    tag = " ".join(str(texto or "").split()).strip()
    tag = tag.strip("#").strip().rstrip(".").strip()
    if not tag:
        return ""
    return tag[:CHARS_DA_ETIQUETA].rstrip()


def _cabeca(caminho_abs):
    """Primeiras linhas de um ficheiro, que e onde o papel dele se denuncia."""
    try:
        with open(caminho_abs, "r", encoding="utf-8", errors="ignore") as f:
            linhas = []
            for _ in range(LINHAS_DE_CONTEXTO):
                linha = f.readline()
                if not linha:
                    break
                linhas.append(linha.rstrip())
    except OSError:
        return ""
    return "\n".join(linhas).strip()[:CHARS_DE_CONTEXTO]


def _atualizado(guardado, chave):
    """A etiqueta guardada ainda serve: tem tag e a assinatura do no nao mudou."""
    return bool((guardado or {}).get("tag")) and (guardado or {}).get("chave") == chave


def _contexto_do_projeto(dados):
    """Uma linha sobre o projeto, para o modelo nomear com o contexto certo."""
    nome = os.path.basename((dados.get("raiz") or "").rstrip("/\\"))
    partes = ["projeto " + nome] if nome else []
    if dados.get("stack"):
        partes.append("stack " + str(dados["stack"]))
    if not partes:
        return ""
    return "Contexto do projeto: " + ", ".join(partes) + "."


def _nos_do_projeto(guardadas):
    """Percorre a arvore e devolve (o que descreve cada no, contexto do projeto).

    A chave de um ficheiro e o mtime; a de uma pasta e a lista dos seus filhos.
    Sao esses valores que decidem se a etiqueta ainda serve ou se o no mudou - e
    so para os que mudaram se le o cabecalho do ficheiro, portanto uma atualizacao
    sem alteracoes nao abre ficheiro nenhum.
    """
    from src.backend.tools.projeto_info import dados_projeto

    dados = dados_projeto()
    raiz = dados.get("raiz") or ""
    arvore = dados.get("arvore")
    if not raiz or not arvore:
        return [], ""
    guardadas = guardadas or {}
    nos = []

    def _percorrer(no, caminho):
        nome = no.get("nome") or ""
        filhos = no.get("filhos") or []
        guardado = guardadas.get(caminho) or {}
        if no.get("tipo") == "pasta":
            nomes = [f.get("nome", "") for f in filhos]
            chave = "|".join(sorted(nomes))
            contexto = ""
            if nomes and not _atualizado(guardado, chave):
                contexto = "conteudo: " + ", ".join(nomes[:FILHOS_NO_CONTEXTO])
            nos.append({"caminho": caminho, "rotulo": caminho or nome,
                        "tipo": "pasta", "chave": chave, "contexto": contexto})
            for filho in filhos:
                filho_nome = filho.get("nome") or ""
                _percorrer(filho, f"{caminho}/{filho_nome}" if caminho else filho_nome)
        else:
            completo = os.path.join(raiz, caminho.replace("/", os.sep))
            try:
                chave = str(os.path.getmtime(completo))
            except OSError:
                chave = ""
            contexto = "" if _atualizado(guardado, chave) else _cabeca(completo)
            nos.append({"caminho": caminho, "rotulo": caminho, "tipo": "ficheiro",
                        "chave": chave, "contexto": contexto})

    _percorrer(arvore, "")
    return nos, _contexto_do_projeto(dados)


def _pendentes(nos, guardadas):
    """Nos sem etiqueta ou cuja assinatura mudou desde a ultima etiquetagem."""
    return [no for no in nos if not _atualizado(guardadas.get(no["caminho"]), no["chave"])]


def _prompt_do_lote(lote, contexto=""):
    linhas = []
    if contexto:
        linhas.append(contexto)
        linhas.append("")
    for no in lote:
        linhas.append(f'- "{no["rotulo"]}" [{no["tipo"]}]')
        if no["contexto"]:
            for linha in no["contexto"].splitlines():
                linhas.append("    " + linha)
    return "\n".join(linhas)


def _parse_resposta(texto, caminhos_pedidos):
    """Extrai {caminho: tag} do que o modelo devolveu, ignorando o que nao foi pedido."""
    from src.backend.ai.base import json_da_resposta

    dados = json_da_resposta(texto)
    if not isinstance(dados, dict):
        return {}
    limpas = {}
    for chave, valor in dados.items():
        if chave not in caminhos_pedidos or not isinstance(valor, str):
            continue
        tag = _limpar_tag(valor)
        if tag:
            limpas[chave] = tag
    return limpas


def etiquetar_projeto(use_deepseek=False):
    """Etiqueta so o que falta, em lotes, gravando a cada lote concluido.

    Corre numa thread propria (a rota devolve antes de isto acabar). Gravar lote a
    lote e o que torna a operacao retomavel: se a geracao falhar a meio, o que ja
    ficou etiquetado nao se perde nem se repete na proxima vez.
    """
    if not estado.get("pasta_raiz"):
        return
    with _lock:
        if estado.get("etiquetando"):
            return
        estado["etiquetando"] = True
        estado["etiquetando_progresso"] = ""
    try:
        bruto = _ler_arquivo()
        guardadas = bruto.get("nos") if isinstance(bruto.get("nos"), dict) else {}
        tentado = bruto.get("tentado") or time.time()
        if not bruto.get("tentado"):
            _gravar(guardadas, tentado)
        nos, contexto = _nos_do_projeto(guardadas)
        pendentes = _pendentes(nos, guardadas)
        total = len(pendentes)
        for indice in range(0, total, TAMANHO_LOTE):
            if indice // TAMANHO_LOTE >= MAX_LOTES:
                break
            lote = pendentes[indice:indice + TAMANHO_LOTE]
            estado["etiquetando_progresso"] = f"{indice + len(lote)}/{total}"
            try:
                texto = gerar_texto(_prompt_do_lote(lote, contexto), _INSTRUCAO,
                                    temperatura=0.1, use_deepseek=use_deepseek)
            except Exception:
                break
            novas = _parse_resposta(texto, {no["caminho"] for no in lote})
            if not novas:
                continue
            for no in lote:
                tag = novas.get(no["caminho"])
                if tag:
                    guardadas[no["caminho"]] = {"tag": tag, "chave": no["chave"]}
            _gravar(guardadas, tentado)
    finally:
        estado["etiquetando"] = False
        estado["etiquetando_progresso"] = ""
