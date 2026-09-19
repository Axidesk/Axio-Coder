"""Preferencias de layout e estilo do utilizador, sempre injetadas no prompt.

Isto nao e conhecimento de um projeto: e o GOSTO do utilizador, que vale em todos
os projetos e por isso vive no DATA_DIR do Axio (ao lado do glossario), nunca na
pasta aberta. E injetado em TODAS as rodadas porque e curto e porque so assim
sobrevive a mudanca de assunto dentro da mesma sessao - a alternativa (uma nota
de knowledge) so aparece quando uma busca semantica a chama, e uma preferencia de
layout raramente e procurada: e aplicada.

REGRA DE ENTRADA: cada linha tem de ser ACIONAVEL e CONFERIVEL no codigo - uma
cor, uma borda, um tempo, um gesto. 'Bonito' e 'moderno' nao entram: daqui sai o
que eu consigo aplicar e o utilizador consegue confirmar a olhar.
"""

import json
import time

from src.backend.config import caminho_data
from src.backend.services.persistencia import gravar_json_atomico

NOME_ARQUIVO = "preferencias.json"


def _caminho():
    return caminho_data(NOME_ARQUIVO)


def carregar():
    try:
        with open(_caminho(), "r", encoding="utf-8") as f:
            dados = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        dados = {}
    itens = dados.get("itens") if isinstance(dados, dict) else None
    return {"itens": itens if isinstance(itens, list) else []}


def _gravar(itens):
    gravar_json_atomico(_caminho(), {"itens": itens})
    return {"itens": itens}


def _chave(area):
    return (area or "").strip().lower()


def escrever(area, texto):
    """Cria ou atualiza UMA preferencia, identificada pela 'area'.

    A area e a chave: escrever na mesma area SUBSTITUI o texto em vez de o
    acumular. Duas linhas a dizer o mesmo com palavras diferentes sao ruido
    injetado em todas as rodadas seguintes.
    """
    chave = _chave(area)
    texto = (texto or "").strip()
    if not chave:
        raise ValueError("a preferencia precisa de uma 'area' curta (ex: 'bordas')")
    if not texto:
        raise ValueError("a preferencia precisa de 'texto'")
    itens = carregar()["itens"]
    agora = time.strftime("%Y-%m-%d %H:%M:%S")
    item = next((i for i in itens if _chave(i.get("area")) == chave), None)
    if item is None:
        item = {"area": chave}
        itens.append(item)
    item.update({"texto": texto, "atualizado": agora})
    _gravar(itens)
    return item


def remover(area):
    chave = _chave(area)
    itens = carregar()["itens"]
    restantes = [i for i in itens if _chave(i.get("area")) != chave]
    if len(restantes) == len(itens):
        return False
    _gravar(restantes)
    return True


def bloco():
    """Bloco pronto a injetar no prompt. Vazio quando nao ha nada registado.

    O titulo vem DENTRO do bloco de proposito: assim um cofre sem preferencias
    nao deixa um cabecalho orfao no prompt.
    """
    itens = carregar()["itens"]
    if not itens:
        return ""
    linhas = [f"- {item.get('area')}: {item.get('texto')}" for item in itens]
    return (
        "=== PREFERENCIAS DE LAYOUT DO USUARIO (permanentes, valem em qualquer projeto) ===\n"
        + "\n".join(linhas)
        + "\n(Aplique-as SEM esperar que ele as repita. Ao perceber uma nova - ou quando ele corrigir "
        "o que fiz - registe-a na mesma rodada com tool_gerenciar_preferencias(acao='escrever').)\n"
    )
