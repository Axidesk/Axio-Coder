"""Auditoria das ligacoes entre o HTML, o JS e o CSS de um frontend.

Cruza as marcas que o leitor (tools/html_lexico.py) tira dos tres lados e denuncia os orfaos
dos dois sentidos: o alvo que o codigo procura e nao existe no HTML (quebra silenciosa: nada
rebenta, o elemento so deixa de ser atualizado) e o id/classe que o HTML declara e ninguem usa.
Vive separado do validador de sintaxe porque sao dois assuntos - um julga UM ficheiro, o outro
julga o PROJETO - e o achado so existe no cruzamento.
"""
from src.backend.state import emit_event
from src.backend.tools.html_lexico import (
    EXT_CSS,
    EXT_HTML,
    EXT_JS,
    alvos_do_css,
    declaracoes_em_texto,
    html_do_ficheiro,
    javascript_do_texto,
    juntar,
    leitor_css,
    leitor_js,
    ler_texto,
    novo_cofre,
)
from src.backend.tools.projeto_comum import (
    PASTAS_IGNORADAS,
    raiz_da_varredura,
    relativo_a,
    varrer_por_extensao,
)
from src.backend.tools.registry import register

_MAX_FICHEIROS = 1500
_MAX_POR_SECAO = 8
_IGNORAR_SEMPRE = frozenset(PASTAS_IGNORADAS - {"vendor", "gen"})


def _acrescentar(destino, registos):
    for registo in registos:
        destino.setdefault(registo["valor"], registo)


def _unicos(registos):
    vistos = {}
    for registo in registos:
        atual = vistos.get(registo["valor"])
        if atual is None:
            vistos[registo["valor"]] = {**registo, "vezes": 1}
        else:
            atual["vezes"] += 1
    return sorted(vistos.values(), key=lambda r: (r["ficheiro"], r["linha"]))


def _montado(valor, prefixos):
    return any(valor.startswith(prefixo) for prefixo in prefixos)


def _orfaos(declarados, usados, prefixos):
    return sorted((r for valor, r in declarados.items()
                   if valor not in usados and not _montado(valor, prefixos)),
                  key=lambda r: (r["ficheiro"], r["linha"]))


def _do_lado_de_fora(raiz, ficheiros, ja_lidos, leitor_do_css, declaradas_ids, declaradas_classes,
                     ids_do_css, classes_do_css):
    """Marcas dos ficheiros fora da varredura normal (vendor, gerados).

    Servem para nao chamar 'inexistente' ao que vive la dentro - o proprio visualizador do Axio
    mora em vendor/ - mas nao geram orfaos nem regras mortas: nao sao o alvo da varredura.
    """
    fora = 0
    for caminho in ficheiros:
        if caminho in ja_lidos:
            continue
        fora += 1
        relativo = relativo_a(caminho, raiz)
        if caminho.lower().endswith(EXT_HTML):
            ids, classes, _, _ = html_do_ficheiro(caminho, relativo)
            _acrescentar(declaradas_ids, ids)
            _acrescentar(declaradas_classes, classes)
            continue
        texto = ler_texto(caminho)
        if texto is None or leitor_do_css is None:
            continue
        achados = alvos_do_css(relativo, texto, leitor_do_css)
        ids_do_css.extend(achados[0])
        classes_do_css.extend(achados[1])
    return fora


def _linhas_de_alvo(alvos):
    linhas = []
    for alvo in alvos[:_MAX_POR_SECAO]:
        vezes = f" ({alvo['vezes']}x)" if alvo.get("vezes", 1) > 1 else ""
        linhas.append(f"  - {alvo['ficheiro']}:{alvo['linha']}: {alvo['via']} -> \"{alvo['valor']}\"{vezes}")
    if len(alvos) > _MAX_POR_SECAO:
        linhas.append(f"  ... (+{len(alvos) - _MAX_POR_SECAO})")
    return linhas


def _linhas_de_declarado(registos):
    linhas = [f"  - {r['ficheiro']}:{r['linha']}: {r['via']} \"{r['valor']}\"" for r in registos[:_MAX_POR_SECAO]]
    if len(registos) > _MAX_POR_SECAO:
        linhas.append(f"  ... (+{len(registos) - _MAX_POR_SECAO})")
    return linhas


def _relato(raiz, contagens, secoes, dinamicos, prefixos, falhas):
    linhas = [
        f"AUDITORIA DE LIGACOES HTML <-> JS/CSS: {contagens['html']} html, {contagens['js']} js, "
        f"{contagens['css']} css em '{raiz}'",
        f"o HTML declara {contagens['ids']} id(s) e {contagens['classes']} classe(s); o JS procura "
        f"{contagens['ids_js']} id(s) e {contagens['classes_js']} classe(s); o CSS usa "
        f"{contagens['ids_css']} id(s) e {contagens['classes_css']} classe(s)",
    ]
    if contagens.get("fora"):
        linhas.append(f"para decidir se um alvo existe entraram mais {contagens['fora']} ficheiro(s) "
                      "fora da varredura normal (vendor, gerados) - esses nao geram orfaos")
    total = 0
    for titulo, registos, formato in secoes:
        if not registos:
            continue
        total += len(registos)
        linhas.append("")
        linhas.append(f"{titulo}: {len(registos)}")
        linhas.extend(formato(registos))
    linhas.append("")
    if dinamicos:
        linhas.append(f"SELETOR MONTADO EM TEMPO DE EXECUCAO (nao pode ser seguido daqui): {len(dinamicos)}")
        linhas.extend(_linhas_de_alvo(_unicos(dinamicos)))
        linhas.append("")
    if prefixos:
        linhas.append("Nao julgados, porque o nome e montado em tempo de execucao - prefixos vistos: "
                      + ", ".join(f"{prefixo}*" for prefixo in sorted(prefixos)[:10]))
        linhas.append("")
    if falhas:
        linhas.append(f"FICHEIROS QUE NAO FORAM LIDOS: {len(falhas)}")
        linhas.extend(f"  - {falha}" for falha in falhas[:5])
        linhas.append("")
    if total:
        linhas.append("Leitura estatica pela arvore (tree-sitter): um seletor montado por concatenacao nao "
                      "entra, uma funcao propria que embrulhe o querySelector nao e seguida e o id de outra "
                      "pagina HTML cala o aviso do JS (o cruzamento e do projeto inteiro, nao de cada pagina).")
        linhas.append("Uma classe do HTML que ninguem usa pode ser gancho de biblioteca externa ou classe "
                      "utilitaria gerada por ferramenta (Tailwind, icon fonts): confirme antes de apagar. "
                      "Nada foi editado.")
    else:
        linhas.append("Nada a apontar: todo o alvo que o JS e o CSS procuram existe no HTML, e todo o id e "
                      "classe que o HTML declara e usado por alguem.")
    return "\n".join(linhas)


@register(
    "tool_auditar_ligacoes",
    'Cruza o HTML de um frontend com o que o JavaScript e o CSS procuram e denuncia os orfaos dos dois sentidos: (a) o codigo que aponta para um #id que ja nao existe no HTML - quebra silenciosa, nada rebenta, o elemento so deixa de ser atualizado - e (b) o id/classe que o HTML declara e ninguem usa. Ve tambem o id que um for=/href= aponta e nao existe, a regra de CSS que morreu e a classe que o JS procura e nao existe em sitio nenhum. Le a arvore (tree-sitter) do JS e do CSS: nao confunde um seletor escrito num comentario com codigo, nem um id que o proprio JS cria com um id que ele procura. Reporta ainda o seletor montado por concatenacao, que nao pode ser seguido daqui. Use depois de tirar ou renomear um id no HTML, e antes de apagar estilo. Sem caminho, varre a pasta do projeto aberto.',
    {
        'caminho_relativo': {"tipo": "STRING", "padrao": ""},
    },
)
def tool_auditar_ligacoes(caminho_relativo=""):
    emit_event("executing", function="Auditando ligacoes HTML <-> JS/CSS")
    raiz, erro = raiz_da_varredura(caminho_relativo)
    if erro:
        return erro
    ficheiros_html = varrer_por_extensao(raiz, EXT_HTML, _MAX_FICHEIROS)
    if not ficheiros_html:
        return (f"SEM HTML: nao ha ficheiros HTML em '{raiz}' - sem HTML nao ha ligacoes para cruzar "
                "(esta ferramenta e de frontend).")
    ficheiros_js = varrer_por_extensao(raiz, EXT_JS, _MAX_FICHEIROS)
    ficheiros_css = varrer_por_extensao(raiz, EXT_CSS, _MAX_FICHEIROS)

    simples_ids, simples_classes = {}, {}
    declaradas_ids, declaradas_classes = {}, {}
    referencias = []
    cofre = novo_cofre()
    falhas = []
    leitor_do_js, erro_js = leitor_js("")
    if leitor_do_js is None:
        falhas.append(f"nenhum JS foi lido: {erro_js}")

    for caminho in ficheiros_html:
        relativo = relativo_a(caminho, raiz)
        ids, classes, refs, scripts = html_do_ficheiro(caminho, relativo)
        _acrescentar(simples_ids, ids)
        _acrescentar(simples_classes, classes)
        _acrescentar(declaradas_ids, ids)
        _acrescentar(declaradas_classes, classes)
        referencias.extend(refs)
        if leitor_do_js is None:
            continue
        for base, codigo in scripts:
            juntar(cofre, javascript_do_texto(relativo, codigo, leitor_do_js, base - 1))

    for caminho in ficheiros_js:
        relativo = relativo_a(caminho, raiz)
        texto = ler_texto(caminho)
        if texto is None:
            continue
        ids, classes, prefixos = declaracoes_em_texto(texto, relativo)
        _acrescentar(declaradas_ids, ids)
        _acrescentar(declaradas_classes, classes)
        cofre["prefixos"] |= prefixos
        leitor, erro_leitor = leitor_js(caminho)
        if leitor is None:
            falhas.append(f"{relativo}: {erro_leitor}")
            continue
        juntar(cofre, javascript_do_texto(relativo, texto, leitor))

    ids_css, classes_css = [], []
    leitor_do_css, erro_css = leitor_css()
    if leitor_do_css is None:
        falhas.append(f"nenhum CSS foi lido: {erro_css}")
    else:
        for caminho in ficheiros_css:
            relativo = relativo_a(caminho, raiz)
            texto = ler_texto(caminho)
            if texto is None:
                continue
            achados = alvos_do_css(relativo, texto, leitor_do_css)
            ids_css.extend(achados[0])
            classes_css.extend(achados[1])

    ids_css_amplo, classes_css_amplo = list(ids_css), list(classes_css)
    fora = _do_lado_de_fora(
        raiz,
        varrer_por_extensao(raiz, EXT_HTML, _MAX_FICHEIROS, _IGNORAR_SEMPRE)
        + varrer_por_extensao(raiz, EXT_CSS, _MAX_FICHEIROS, _IGNORAR_SEMPRE),
        set(ficheiros_html) | set(ficheiros_css),
        leitor_do_css,
        declaradas_ids,
        declaradas_classes,
        ids_css_amplo,
        classes_css_amplo,
    )

    _acrescentar(declaradas_ids, cofre["ids_novos"])
    _acrescentar(declaradas_classes, cofre["classes_novas"])
    prefixos = cofre["prefixos"]

    ids_existem = set(declaradas_ids)
    classes_existem = set(declaradas_classes)
    ids_procurados = {r["valor"] for r in cofre["ids"]}
    classes_procuradas = {r["valor"] for r in cofre["classes"]}
    ids_do_css = {r["valor"] for r in ids_css}
    classes_do_css = {r["valor"] for r in classes_css}
    ids_com_regra = {r["valor"] for r in ids_css_amplo}
    classes_com_regra = {r["valor"] for r in classes_css_amplo}
    ids_referidos = {r["valor"] for r in referencias}

    secoes = (
        ("JS PROCURA ID QUE NAO EXISTE NO HTML - quebra silenciosa, o elemento nunca e atualizado",
         _unicos([r for r in cofre["ids"]
                  if r["valor"] not in ids_existem and not _montado(r["valor"], prefixos)]),
         _linhas_de_alvo),
        ("JS PROCURA CLASSE QUE NAO EXISTE EM HTML NEM NO CSS - a chamada nao faz nada",
         _unicos([r for r in cofre["classes"]
                  if r["valor"] not in classes_existem and r["valor"] not in classes_com_regra
                  and not _montado(r["valor"], prefixos)]),
         _linhas_de_alvo),
        ("HTML APONTA PARA ID QUE NAO EXISTE (for=, href=, aria-*)",
         _unicos([r for r in referencias if r["valor"] not in ids_existem]), _linhas_de_alvo),
        ("CSS USA ID QUE NAO EXISTE NO HTML - regra morta",
         _unicos([r for r in ids_css
                  if r["valor"] not in ids_existem and not _montado(r["valor"], prefixos)]),
         _linhas_de_alvo),
        ("CSS USA CLASSE QUE NAO EXISTE EM HTML NEM E CRIADA PELO JS - regra morta",
         _unicos([r for r in classes_css
                  if r["valor"] not in classes_existem and r["valor"] not in classes_procuradas
                  and not _montado(r["valor"], prefixos)]),
         _linhas_de_alvo),
        ("HTML DECLARA ID QUE NINGUEM USA - candidato a remover",
         _orfaos(simples_ids, ids_procurados | ids_com_regra | ids_referidos, prefixos),
         _linhas_de_declarado),
        ("HTML DECLARA CLASSE QUE NINGUEM USA - pode ser gancho de biblioteca externa",
         _orfaos(simples_classes, classes_procuradas | classes_com_regra, prefixos),
         _linhas_de_declarado),
    )
    contagens = {
        "html": len(ficheiros_html), "js": len(ficheiros_js), "css": len(ficheiros_css), "fora": fora,
        "ids": len(declaradas_ids), "classes": len(declaradas_classes),
        "ids_js": len(ids_procurados), "classes_js": len(classes_procuradas),
        "ids_css": len(ids_do_css), "classes_css": len(classes_do_css),
    }
    return _relato(raiz, contagens, secoes, cofre["dinamicos"], prefixos, falhas)
