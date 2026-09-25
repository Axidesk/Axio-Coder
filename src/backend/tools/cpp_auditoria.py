"""Auditoria de um projeto C/C++: o que cada ficheiro DECLARA contra o que DEFINE.

Le a arvore (tools/cpp.py) e cruza o que o compilador so junta no fim: metodo declarado
na classe e nunca definido (erro de linker), definicao sem declaracao, o mesmo simbolo
definido em dois sitios (ODR), include com aspas para ficheiro que nao existe e cabecalho
sem guarda. Vive separado do leitor porque sao dois assuntos: um le UM ficheiro, o outro
julga o PROJETO inteiro - e o relatorio so existe com o cruzamento dos dois lados.
"""
import os
import re

from src.backend.services.file_service import resolver_caminho
from src.backend.state import emit_event, estado
from src.backend.tools import cpp
from src.backend.tools.projeto_comum import (
    PASTAS_IGNORADAS,
    relativo_a,
    varrer_por_extensao,
)
from src.backend.tools.registry import register

_MAX_FICHEIROS = 2000
_MAX_APONTAMENTOS = 12


def _ficha_definicao(item, relativo):
    return {
        "escopo": item["escopo"],
        "nome": item["nome"],
        "classe": cpp.sem_qualificadores(item["escopo"]) if item["escopo"] else "",
        "ficheiro": relativo,
        "linha": item["linha"],
        "parametros": item["parametros"],
        "constante": re.search(r"\)\s*const\b", item["assinatura"]) is not None,
        "estatico": item["assinatura"].startswith("static"),
        "template": item["template"],
    }


def _sem_definicao(classes, definicoes):
    definidos = {(d["classe"], d["nome"]) for d in definicoes if d["classe"]}
    apontamentos = []
    for nome, classe in sorted(classes.items()):
        if classe["template"] or classe["ambiguo"]:
            continue
        for metodo, linha in sorted(classe["declarados"].items(), key=lambda par: par[1]):
            if (nome, metodo) in definidos:
                continue
            apontamentos.append(
                f"{nome}::{metodo} - declarado em {classe['ficheiro']}:{linha}, sem corpo em nenhum "
                "ficheiro do projeto (linker: unresolved external)"
            )
    return apontamentos


def _sem_declaracao(classes, definicoes):
    apontamentos = []
    for definicao in definicoes:
        classe = classes.get(definicao["classe"]) if definicao["classe"] else None
        if classe is None or classe["template"] or classe["ambiguo"]:
            continue
        if definicao["nome"] in classe["declarados"] or definicao["nome"] in classe["mencoes"]:
            continue
        apontamentos.append(
            f"{definicao['escopo']}::{definicao['nome']} - definido em {definicao['ficheiro']}:"
            f"{definicao['linha']}, mas a classe {definicao['classe']} "
            f"({classe['ficheiro']}:{classe['linha']}) nao declara esse nome"
        )
    return apontamentos


def _duplicadas(definicoes):
    vistos = {}
    for definicao in definicoes:
        if definicao["estatico"] or definicao["nome"] == "main":
            continue
        chave = (definicao["escopo"], definicao["nome"], definicao["parametros"], definicao["constante"])
        vistos.setdefault(chave, []).append(definicao)
    apontamentos = []
    for (escopo, nome, parametros, constante), lista in sorted(vistos.items()):
        if len(lista) < 2:
            continue
        onde = ", ".join(f"{d['ficheiro']}:{d['linha']}" for d in lista)
        rotulo = f"{escopo}::{nome}" if escopo else nome
        assinatura = f"{nome}({parametros} arg{', const' if constante else ''})"
        apontamentos.append(f"{rotulo} - assinatura {assinatura} definida {len(lista)} vezes "
                            f"({onde}) - candidato a violacao ODR")
    return apontamentos


def _sem_guarda(cabecalhos, raiz):
    falhas = []
    for caminho in cabecalhos:
        try:
            with open(caminho, "r", encoding="utf-8", errors="ignore") as f:
                texto = f.read()
        except OSError:
            continue
        if "#pragma once" in texto:
            continue
        if re.search(r"^\s*#\s*ifndef\s+\w+\s*$", texto, re.MULTILINE) and \
                re.search(r"^\s*#\s*define\s+\w+\s*$", texto, re.MULTILINE):
            continue
        falhas.append(relativo_a(caminho, raiz))
    return falhas


def _includes_quebrados(ficheiros, raiz):
    conhecidos = set()
    for pasta, dirs, nomes in os.walk(raiz):
        dirs[:] = [d for d in dirs if d not in PASTAS_IGNORADAS and not d.startswith(".")]
        conhecidos |= {n.lower() for n in nomes}
    falhas = set()
    for caminho in ficheiros:
        pasta = os.path.dirname(caminho)
        for delimitador, destino in cpp.includes(caminho):
            if delimitador == "<" or not destino:
                continue
            if os.path.exists(os.path.normpath(os.path.join(pasta, destino))):
                continue
            if os.path.basename(destino).lower() in conhecidos:
                continue
            falhas.add(f"{relativo_a(caminho, raiz)} inclui \"{destino}\", que nao existe no projeto")
    return sorted(falhas)


def _nova_classe(item, relativo):
    return {
        "nome": item["nome"],
        "ficheiro": relativo,
        "linha": item["linha"],
        "declarados": {},
        "mencoes": set(),
        "template": bool(item.get("template")),
        "ambiguo": False,
    }


def _relato(raiz, ficheiros, cabecalhos, classes, problemas):
    codigos = len(ficheiros) - len(cabecalhos)
    total = sum(len(p) for p in problemas.values())
    linhas = [(
        f"AUDITORIA C/C++: {len(ficheiros)} ficheiro(s) em '{raiz}' "
        f"({codigos} de codigo, {len(cabecalhos)} cabecalho(s)), {len(classes)} classe(s), "
        f"{total} apontamento(s)"
    )]
    titulos = (
        ("sem_definicao", "DECLARADO SEM DEFINICAO (erro de linker)"),
        ("sem_declaracao", "DEFINIDO SEM DECLARACAO (a classe nao declara o nome)"),
        ("duplicadas", "DEFINIDO EM DOIS SITIOS (ODR)"),
        ("includes", "INCLUDE COM ASPAS PARA FICHEIRO QUE NAO EXISTE"),
        ("sem_guarda", "CABECALHO SEM GUARDA (#pragma once / #ifndef)"),
    )
    for chave, titulo in titulos:
        lista = problemas[chave]
        if not lista:
            continue
        linhas.append("")
        linhas.append(f"{titulo}: {len(lista)}")
        for apontamento in lista[:_MAX_APONTAMENTOS]:
            linhas.append(f"  - {apontamento}")
        if len(lista) > _MAX_APONTAMENTOS:
            linhas.append(f"  ... (+{len(lista) - _MAX_APONTAMENTOS})")
    linhas.append("")
    if total:
        linhas.append("Leitura pela arvore (tree-sitter): o que vem de biblioteca externa ao projeto "
                      "pode aparecer como 'sem declaracao' - confirme o ficheiro antes de mexer.")
    else:
        linhas.append("Nada a apontar: tudo o que e declarado tem corpo, tudo o que e definido esta "
                      "declarado e nenhum simbolo aparece duas vezes.")
    return "\n".join(linhas)
@register(
    "tool_auditar_cpp",
    'Varre um projeto C/C++ e cruza o que cada ficheiro DECLARA com o que DEFINE: metodos declarados na classe e nunca definidos (erro de linker garantido), definicoes sem declaracao correspondente, o mesmo simbolo definido em dois sitios (violacao ODR), includes com aspas que apontam para ficheiros que nao existem no projeto e cabecalhos sem guarda. Le a arvore (tree-sitter), nao o texto: nao confunde uma chamada com uma definicao nem um nome escrito num comentario com codigo. Sem caminho, varre a pasta do projeto aberto. Use antes de compilar e sempre que mexer em cabecalhos.',
    {
        'caminho_relativo': {"tipo": "STRING", "padrao": ""},
    },
)
def tool_auditar_cpp(caminho_relativo=""):
    emit_event("executing", function="Auditando projeto C/C++")
    raiz, erro = _raiz_da_varredura(caminho_relativo)
    if erro:
        return erro
    ficheiros = varrer_por_extensao(raiz, cpp.EXTENSOES, _MAX_FICHEIROS)
    if not ficheiros:
        return f"SEM C/C++: nao ha ficheiros C/C++ em '{raiz}'."
    cabecalhos = [f for f in ficheiros if os.path.splitext(f)[1].lower() in cpp.EXTENSOES_CABECALHO]
    por_ficheiro = []
    for ficheiro in ficheiros:
        src, arvore = cpp.partir(ficheiro)
        if arvore is None:
            continue
        por_ficheiro.append((relativo_a(ficheiro, raiz), cpp.colher(src, arvore),
                             cpp.mencoes_por_classe(src, arvore)))
    classes = _classes_do_projeto(por_ficheiro)
    definicoes = [_ficha_definicao(item, relativo)
                  for relativo, itens, _ in por_ficheiro
                  for item in itens
                  if item["tipo"] in ("metodo", "funcao") and item["corpo"]]
    problemas = {
        "sem_definicao": _sem_definicao(classes, definicoes),
        "sem_declaracao": _sem_declaracao(classes, definicoes),
        "duplicadas": _duplicadas(definicoes),
        "includes": _includes_quebrados(ficheiros, raiz),
        "sem_guarda": _sem_guarda(cabecalhos, raiz),
    }
    return _relato(raiz, ficheiros, cabecalhos, classes, problemas)


def _classes_do_projeto(por_ficheiro):
    """{nome: ficha} de todas as classes do projeto, com o que cada uma declara.

    Duas passagens de proposito: a classe tem de estar conhecida antes de lhe pendurar as
    declaracoes, senao um metodo lido num .cpp criava uma classe-fantasma com o ficheiro
    errado. Nome repetido em dois sitios diferentes marca a ficha como ambigua e cala as
    verificacoes dela - entre duas classes homonimas, a duvida e a resposta honesta.
    """
    classes = {}
    for relativo, itens, _ in por_ficheiro:
        for item in itens:
            if item["tipo"] not in ("classe", "struct"):
                continue
            ficha = classes.get(item["nome"])
            if ficha is None:
                classes[item["nome"]] = _nova_classe(item, relativo)
            elif ficha["ficheiro"] != relativo:
                ficha["ambiguo"] = True
    for relativo, itens, mencoes in por_ficheiro:
        for item in itens:
            if item["tipo"] != "metodo" or item["sinal"] or item["abstrato"]:
                continue
            ficha = classes.get(cpp.sem_qualificadores(item["escopo"]))
            if ficha is None:
                continue
            ficha["declarados"][item["nome"]] = item["linha"]
            ficha["template"] = ficha["template"] or item["template"]
        for nome, nomes in mencoes.items():
            if nome in classes:
                classes[nome]["mencoes"] |= nomes
    return classes
def _raiz_da_varredura(caminho_relativo):
    if not caminho_relativo:
        raiz = estado.get("pasta_raiz", "")
        if not raiz or not os.path.isdir(raiz):
            return None, "ERRO: nao ha pasta de projeto aberta. Indique 'caminho_relativo'."
        return raiz, None
    absoluto, erro = resolver_caminho(caminho_relativo, permitir_extra=True)
    if erro:
        return None, erro
    if not os.path.exists(absoluto):
        return None, f"ERRO: '{caminho_relativo}' nao existe."
    return (absoluto if os.path.isdir(absoluto) else os.path.dirname(absoluto)), None
