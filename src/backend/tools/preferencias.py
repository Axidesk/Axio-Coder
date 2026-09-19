"""Ferramenta das preferencias de layout e estilo do utilizador.

O gosto do utilizador nao se adivinha: ele diz uma vez e eu tenho de o aplicar
sempre. Guardado no DATA_DIR do Axio (e nao na pasta do projeto), o bloco entra
em TODA a rodada seja qual for o projeto aberto - e por isso esta ferramenta
tambem serve para CONFERIR o que ja esta registado antes de decidir um layout.
"""

from src.backend.services import preferencias
from src.backend.tools.registry import register


@register(
    "tool_gerenciar_preferencias",
    "Le e escreve as preferencias PERMANENTES de layout e estilo do utilizador (bordas, cores, transicoes, "
    "scrollbar, gestos). O bloco e injetado em todas as rodadas e vale em qualquer projeto, porque vive no "
    "DATA_DIR do Axio e nao na pasta aberta. 'listar' mostra o que ja esta registado; 'escrever' grava uma "
    "preferencia (a 'area' e a chave - escrever na mesma area SUBSTITUI o texto, nao acumula); 'remover' apaga. "
    "Use 'escrever' SEMPRE que o utilizador corrigir um detalhe ou revelar um gosto: e o mecanismo que faz o "
    "estilo dele sobreviver a esta conversa.",
    {
        "acao": {
            "tipo": "STRING",
            "desc": "listar | escrever | remover",
            "enum": ["listar", "escrever", "remover"],
            "obrig": True,
        },
        "area": {
            "tipo": "STRING",
            "desc": "Assunto curto que identifica a preferencia (ex: 'bordas', 'transicoes', 'scrollbar'). E a chave: escrever na mesma area substitui.",
            "padrao": "",
        },
        "texto": {
            "tipo": "STRING",
            "desc": "A preferencia em si, acionavel e conferivel (ex: 'Sem bordas em botoes, icones, inputs e cards: separar por cor e por fundo suave no hover.').",
            "padrao": "",
        },
    },
)
def tool_gerenciar_preferencias(acao, area="", texto=""):
    acao = (acao or "").strip().lower()
    if acao == "listar":
        return _listar_preferencias()
    if acao == "escrever":
        try:
            item = preferencias.escrever(area, texto)
        except ValueError as e:
            return f"ERRO: {e}"
        return f"Preferencia registada: [{item['area']}] {item['texto']}"
    if acao == "remover":
        if not preferencias.remover(area):
            return f"ERRO: nao ha preferencia na area '{area}'."
        return f"Preferencia '{area}' removida."
    return f"ERRO: acao desconhecida '{acao}'. Use listar, escrever ou remover."


def _listar_preferencias():
    itens = preferencias.carregar()["itens"]
    if not itens:
        return "Nenhuma preferencia registada."
    linhas = [f"- [{item.get('area')}] {item.get('texto')}" for item in itens]
    return "PREFERENCIAS REGISTADAS:\n" + "\n".join(linhas)
