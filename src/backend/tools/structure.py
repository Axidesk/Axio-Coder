"""Auditoria estrutural do codigo Python, modulo a modulo.

Varrimento que o linter e o jscpd nao fazem: funcao publica sem consumidor,
funcao orfa, simbolo privado importado de outro modulo, corpos de funcao
identicos por AST (abaixo do limiar de linhas do jscpd), nomes de topo repetidos
entre modulos e modulos de tools/ sem ferramenta registada.

Separa DEFEITO de AVISO, porque os dois casos exigem accoes diferentes:
  * DEFEITO - contradiz o desenho: orfa, privado importado, corpo identico,
    nome publico repetido em dois modulos;
  * AVISO   - decidivel: funcao publica usada so dentro do proprio modulo
    (candidata a privada), wrapper de <=3 linhas, corpo semelhante com literais
    diferentes (juncao de wrappers, aceitavel por desenho) e dependencia
    invertida entre camadas (um modulo que importa de uma camada acima da sua,
    que e o sinal tipico de peca no modulo errado).

Os usos vem do AST (nunca de regex sobre o texto), os nomes repetidos so contam
se forem publicos (homonimos privados sao normais) e as referencias incluem o
app.py da raiz, que fica fora da pasta varrida.
"""

import ast
import collections
import hashlib
import os
import re

from src.backend.services.file_service import arquivos_recursivos, resolver_caminho
from src.backend.state import emit_event
from src.backend.tools.registry import register

_IGNORAR = {"__init__.py"}
_GRANDE = 300
_MIN_CORPO = 120
_ARRANQUE = "app.py (raiz)"
_FORA = "fora do ambito varrido"
_CAMADAS = {"services": 1, "memory": 1, "tools": 2, "ai": 3, "routes": 4}
_NIVEL_RAIZ = 0
_NIVEL_ENTRADA = 4


def _chave_relativa(caminho):
    """Chave de um modulo no relatorio: relativa ao projeto quando possivel."""
    rel = os.path.relpath(caminho, os.getcwd()).replace("\\", "/")
    return caminho.replace("\\", "/") if rel.startswith("..") else rel


def _modulos_da_pasta(pasta_abs):
    fontes, arvores, invalidos = {}, {}, []
    for caminho in arquivos_recursivos(pasta_abs, ".py"):
        if os.path.basename(caminho) in _IGNORAR or not os.path.isfile(caminho):
            continue
        rel = _chave_relativa(caminho)
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                texto = f.read()
            arvores[rel] = ast.parse(texto)
            fontes[rel] = texto
        except SyntaxError as e:
            invalidos.append(f"{rel}: {e}")
    return fontes, arvores, invalidos


def _nomes_referenciados(arvore):
    nomes = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Name):
            nomes.add(no.id)
        elif isinstance(no, ast.Attribute):
            nomes.add(no.attr)
        elif isinstance(no, ast.ImportFrom):
            nomes.update(a.name for a in no.names)
        elif isinstance(no, ast.Import):
            nomes.update(a.name.split(".")[-1] for a in no.names)
    return nomes


def _referencias_do_arranque(pasta_abs):
    alvo = os.path.abspath(pasta_abs)
    for _ in range(6):
        alvo = os.path.dirname(alvo)
        candidato = os.path.join(alvo, "app.py")
        if os.path.isfile(candidato):
            try:
                with open(candidato, "r", encoding="utf-8") as f:
                    return _nomes_referenciados(ast.parse(f.read()))
            except Exception:
                return set()
    return set()


def _raiz_do_backend(pasta_abs):
    """Ancestral que tem as pastas do backend (tools, routes, ai, services)."""
    alvo = os.path.abspath(pasta_abs)
    for _ in range(6):
        pastas = sum(os.path.isdir(os.path.join(alvo, p))
                     for p in ("tools", "routes", "ai", "services"))
        if pastas >= 3:
            return alvo
        pai = os.path.dirname(alvo)
        if pai == alvo:
            return ""
        alvo = pai
    return ""


def _referencias_fora_do_ambito(pasta_abs, arvores):
    """Nomes referenciados pelos consumidores de fora, e quantos modulos os deram."""
    nomes, lidos = set(), 0
    for caminho in _fontes_fora_do_ambito(pasta_abs, arvores):
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                nomes |= _nomes_referenciados(ast.parse(f.read()))
            lidos += 1
        except (OSError, SyntaxError):
            continue
    return nomes, lidos


def _fontes_fora_do_ambito(pasta_abs, arvores):
    """Caminhos dos modulos que consomem o codigo varrido sem estarem na varredura.

    Sao tres grupos: os modulos do backend que ficam fora da pasta pedida (apontar a
    auditoria a uma subpasta nao pode tornar orfa a funcao que so o routes/ chama),
    os scripts soltos na RAIZ do projeto e os modulos das pastas de modelo (as que
    tem `modelo.py`), que usam as primitivas de geometria. Sem os dois ultimos
    grupos, toda a biblioteca de malhas sai ORFA e o relatorio pede a remocao de
    codigo vivo.
    """
    raiz = _raiz_do_backend(pasta_abs)
    if not raiz:
        return []
    caminhos = [
        caminho
        for caminho in arquivos_recursivos(raiz, ".py")
        if os.path.basename(caminho) not in _IGNORAR
        and os.path.isfile(caminho)
        and _chave_relativa(caminho) not in arvores
    ]
    projeto = os.path.dirname(os.path.dirname(raiz))
    for nome in sorted(os.listdir(projeto)):
        caminho = os.path.join(projeto, nome)
        if nome.endswith(".py") and os.path.isfile(caminho):
            caminhos.append(caminho)
    caminhos.extend(_fontes_de_modelos(projeto))
    return caminhos


def _fontes_de_modelos(projeto):
    """Modulos das pastas de modelo (as que tem modelo.py), que consomem o nucleo.

    Sem este grupo, tirar o codigo de um modelo do backend para a pasta dele
    torna ORFA toda a primitiva que ele usa - o relatorio passa a pedir a
    remocao de codigo vivo.
    """
    caminhos = []
    for nome in sorted(os.listdir(projeto)):
        pasta = os.path.join(projeto, nome)
        if not os.path.isdir(pasta):
            continue
        for sub in sorted(os.listdir(pasta)):
            alvo = os.path.join(pasta, sub)
            if os.path.isfile(os.path.join(alvo, "modelo.py")):
                caminhos.extend(arquivos_recursivos(alvo, ".py"))
    return caminhos


def _itens_de_topo(arvore):
    itens = []
    for no in arvore.body:
        if not isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        itens.append({
            "nome": no.name,
            "tipo": "classe" if isinstance(no, ast.ClassDef) else "funcao",
            "li": no.lineno,
            "n": no.end_lineno - no.lineno + 1,
            "privado": no.name.startswith("_"),
            "decs": [ast.unparse(d) for d in no.decorator_list],
            "args": [a.arg for a in no.args.args] if hasattr(no, "args") else [],
            "no": no,
        })
    return itens


def _hash_do_corpo(item, normalizar):
    no = item["no"]
    partes = [no.args] if hasattr(no, "args") else []
    partes = partes + list(no.body)
    corpo = ast.dump(ast.Module(body=partes, type_ignores=[]), annotate_fields=False,
                     include_attributes=False)
    if normalizar:
        corpo = re.sub(r"'[^']*'", "''", corpo)
        corpo = re.sub(r"\b\d+\b", "0", corpo)
    return hashlib.sha256(corpo.encode()).hexdigest()[:12], len(corpo)


def _imports_privados(arvores):
    cruzados = []
    for m, arvore in arvores.items():
        for no in ast.walk(arvore):
            if not isinstance(no, ast.ImportFrom) or not no.module:
                continue
            if not no.module.startswith("src.backend"):
                continue
            origem = no.module.replace(".", "/") + ".py"
            for a in no.names:
                if a.name.startswith("_"):
                    cruzados.append((origem, m, a.name, no.lineno))
    return cruzados


def _nivel_do_caminho(rel):
    partes = rel.replace("\\", "/").split("/")
    if len(partes) >= 3 and partes[0] == "src" and partes[1] == "backend":
        pasta = partes[2]
        return (_CAMADAS[pasta], pasta) if pasta in _CAMADAS else (_NIVEL_RAIZ, "raiz")
    return _NIVEL_ENTRADA, "arranque"


def _nivel_do_modulo(modulo):
    partes = modulo.split(".")
    if len(partes) >= 3 and partes[0] == "src" and partes[1] == "backend":
        pasta = partes[2]
        return (_CAMADAS[pasta], pasta) if pasta in _CAMADAS else (_NIVEL_RAIZ, "raiz")
    return _NIVEL_ENTRADA, "externo"


def _arestas_de_camada(arvores):
    """Grafo pasta->pasta dos imports internos, e os que SOBEM de camada.

    Camadas declaradas (da mais interna para a mais externa):
    raiz < services/memory < tools < ai < routes. Importar de uma camada ACIMA
    da propria (services -> tools, tools -> ai) e o sinal tipico de peca posta
    no modulo errado; importar do mesmo nivel (tools -> tools, memory ->
    memory) e desenho normal e nao gera achado nenhum.
    """
    grafo = collections.Counter()
    invertidas = []
    for m, arvore in arvores.items():
        nivel_m, pasta_m = _nivel_do_caminho(m)
        for no in ast.walk(arvore):
            if not isinstance(no, ast.ImportFrom) or not no.module:
                continue
            if not no.module.startswith("src.backend"):
                continue
            nivel_d, pasta_d = _nivel_do_modulo(no.module)
            grafo[(pasta_m, pasta_d)] += 1
            if nivel_d > nivel_m:
                invertidas.append((m, no.lineno, no.module, pasta_d, nivel_d, pasta_m, nivel_m))
    return grafo, invertidas


def _analisar(arvores, externos, fora=()):
    topo = {m: _itens_de_topo(a) for m, a in arvores.items()}
    referencias = {m: _nomes_referenciados(a) for m, a in arvores.items()}
    quem_usa = collections.defaultdict(set)
    for m, refs in referencias.items():
        for nome in refs:
            quem_usa[nome].add(m)
    for nome in externos:
        quem_usa[nome].add(_ARRANQUE)
    for nome in fora:
        quem_usa[nome].add(_FORA)

    defeitos = collections.defaultdict(list)
    avisos = collections.defaultdict(list)

    for m, itens in topo.items():
        for i in itens:
            if i["tipo"] != "funcao" or i["privado"] or i["decs"] or len(i["nome"]) < 4:
                continue
            if quem_usa[i["nome"]] - {m}:
                continue
            if i["nome"] in referencias[m]:
                avisos[m].append(f"USO INTERNO l.{i['li']}: {i['nome']}({i['n']}l) so e usada dentro "
                                 f"do modulo (candidata a privada)")
            else:
                defeitos[m].append(f"ORFA l.{i['li']}: {i['nome']}({i['n']}l) nunca usada em parte nenhuma")

    for origem, consumidor, nome, li in _imports_privados(arvores):
        if origem in arvores:
            defeitos[origem].append(f"PRIVADO IMPORTADO: {nome} e importado por {consumidor} "
                                    f"(l.{li}) — tornar publico na origem")
        defeitos[consumidor].append(f"PRIVADO IMPORTADO l.{li}: {nome} vem de {origem} — "
                                    f"a origem deve expor API publica")

    grafo, invertidas = _arestas_de_camada(arvores)
    for m, li, modulo, pasta_d, nivel_d, pasta_m, nivel_m in invertidas:
        avisos[m].append(f"DEPENDENCIA INVERTIDA l.{li}: importa {modulo} (camada {nivel_d}, "
                         f"{pasta_d}) estando em {pasta_m} (camada {nivel_m})")

    grupos_estritos = collections.defaultdict(list)
    grupos_tolerantes = collections.defaultdict(list)
    for m, itens in topo.items():
        for i in itens:
            chave, tamanho = _hash_do_corpo(i, False)
            if tamanho >= _MIN_CORPO:
                grupos_estritos[chave].append((m, i))
            chave_t, tamanho_t = _hash_do_corpo(i, True)
            if tamanho_t >= _MIN_CORPO:
                grupos_tolerantes[chave_t].append((m, i))

    ja_estrito = set()
    for chave, lst in sorted(grupos_estritos.items()):
        if len(lst) < 2:
            continue
        resumo = " | ".join(f"{m}:{i['li']} {i['nome']}({i['n']}l)" for m, i in lst)
        for m, i in lst:
            defeitos[m].append(f"CORPO IDENTICO hash={chave}: {resumo}")
            ja_estrito.add((m, i["li"]))
    for chave, lst in sorted(grupos_tolerantes.items()):
        if len(lst) < 2 or all((m, i["li"]) in ja_estrito for m, i in lst):
            continue
        resumo = " | ".join(f"{m}:{i['li']} {i['nome']}({i['n']}l)" for m, i in lst)
        for m, _ in lst:
            avisos[m].append(f"CORPO SEMELHANTE hash={chave} (literais diferentes): {resumo}")

    por_nome = collections.defaultdict(list)
    for m, itens in topo.items():
        for i in itens:
            por_nome[i["nome"]].append((m, i))
    for nome, lst in sorted(por_nome.items()):
        if nome.startswith("_"):
            continue
        modulos = sorted({m for m, _ in lst})
        if len(modulos) < 2:
            continue
        resumo = " | ".join(f"{m}:{i['li']}" for m, i in lst)
        for m, _ in lst:
            defeitos[m].append(f"NOME REPETIDO {nome}: {resumo}")

    for m, itens in topo.items():
        for i in itens:
            if i["tipo"] == "funcao" and not i["decs"] and not i["privado"] and i["n"] <= 3:
                avisos[m].append(f"WRAPPER l.{i['li']}: {i['nome']}({i['n']}l) args={i['args']}")

    return topo, defeitos, avisos, grafo


def _tools_sem_ferramenta(topo):
    """Modulos de tools/ sem @register: sao APOIO, nao ferramenta.

    Nao e achado. O registry.py e a infraestrutura do registo e o
    comments_lexer.py e a camada de leitura - nenhum dos dois declara
    ferramenta. Se um modulo de ferramentas ESQUECER o @register, o sinal
    aparece noutro sitio: a funcao `tool_*` fica orfa (ninguem a invoca) e sai
    como DEFEITO na propria linha do modulo. Por isso o veredito nao precisa
    desta lista - ela serve so para dizer quantos modulos de tools/ sao apoio.
    """
    return [(m, len(itens)) for m, itens in sorted(topo.items())
            if "/tools/" in m
            and not any(d.startswith("register") for i in itens for d in i["decs"])]


def _contagem_de_itens(topo, modulos):
    """Funcoes e classes de topo de um conjunto de modulos (contagem unica)."""
    funcoes = classes = 0
    for m in modulos:
        for i in topo[m]:
            if i["tipo"] == "classe":
                classes += 1
            else:
                funcoes += 1
    return funcoes, classes


def _relatorio(alvo, fontes, arvores, invalidos, externos, detalhado, fora=(), n_fora=0):
    topo, defeitos, avisos, grafo = _analisar(arvores, externos, fora)
    n_linhas = {m: texto.count("\n") + 1 for m, texto in fontes.items()}
    n_caracteres = sum(len(texto) for texto in fontes.values())
    funcoes, classes = _contagem_de_itens(topo, list(arvores))
    por_pasta = collections.defaultdict(list)
    for m in arvores:
        por_pasta["/".join(m.split("/")[:-1]) or "."].append(m)
    ref_extra = ""
    if externos or n_fora:
        origens = ([_ARRANQUE] if externos else []) + (
            [f"{n_fora} modulo(s) do backend fora do ambito"] if n_fora else []
        )
        ref_extra = " | referencias incluidas: " + " + ".join(origens)
    linhas = [f"AUDITORIA ESTRUTURAL — {alvo}",
              f"varridos: {len(arvores)} modulos .py em {len(por_pasta)} pastas | "
              f"{sum(n_linhas.values())} linhas | {n_caracteres} caracteres | "
              f"{funcoes} funcoes | {classes} classes | "
              f"sintaxe invalida: {len(invalidos)}{ref_extra}"]
    for inv in invalidos:
        linhas.append(f"  !! SINTAXE: {inv}")

    limpos = com_defeito = com_aviso = 0
    for pasta in sorted(por_pasta):
        modulos = sorted(por_pasta[pasta])
        n_func, n_cls = _contagem_de_itens(topo, modulos)
        linhas.append("")
        linhas.append(f"--- {pasta}/  ({len(modulos)} modulos, "
                      f"{sum(n_linhas[m] for m in modulos)} linhas, "
                      f"{n_func} funcoes, {n_cls} classes)")
        for m in modulos:
            d = sorted(set(defeitos.get(m, [])))
            a = sorted(set(avisos.get(m, [])))
            if d:
                com_defeito += 1
            elif a:
                com_aviso += 1
            else:
                limpos += 1
            partes = []
            if d:
                partes.append(f"{len(d)} DEFEITO(S)")
            if a:
                partes.append(f"{len(a)} aviso(s)")
            marca = " + ".join(partes) if partes else "OK"
            linhas.append(f"  {m.split('/')[-1]:24s} {n_linhas[m]:5d}l {len(topo[m]):2d} itens  {marca}")
            for texto in d:
                linhas.append(f"      - {texto}")
            for texto in a:
                linhas.append(f"      ~ {texto}")
            if detalhado:
                for i in topo[m]:
                    linhas.append(f"        . {i['tipo']} {i['nome']} l.{i['li']} ({i['n']}l) args={i['args']}")

    grandes = sorted(((n, m) for m, n in n_linhas.items() if n > _GRANDE), reverse=True)
    linhas.append("")
    linhas.append(f"MODULOS ACIMA DE {_GRANDE} LINHAS: {len(grandes)}")
    for tam, m in grandes:
        linhas.append(f"  {tam:5d}l  {m}")

    apoio = _tools_sem_ferramenta(topo)
    linhas.append("")
    linhas.append(f"MODULOS DE tools/ DE APOIO (sem @register, por desenho): {len(apoio)}")
    for m, n_itens in apoio:
        linhas.append(f"  {m.split('/')[-1]:24s} {n_itens:2d} itens")

    linhas.append("")
    linhas.append("DEPENDENCIAS INTERNAS (camada de origem -> camada de destino)")
    linhas.append("  ordem declarada: raiz < services/memory < tools < ai < routes")
    if grafo:
        for (origem, destino), n in sorted(grafo.items(), key=lambda kv: (-kv[1], kv[0])):
            invertida = _CAMADAS.get(destino, _NIVEL_RAIZ) > _CAMADAS.get(origem, _NIVEL_RAIZ)
            linhas.append(f"  {origem:10s} -> {destino:10s} {n:3d}"
                          f"{'   <-- INVERTIDA' if invertida else ''}")
    else:
        linhas.append("  nenhuma aresta entre pastas do backend")

    linhas.append("")
    linhas.append(f"VEREDITO: {com_defeito} modulo(s) com defeito, {com_aviso} so com avisos, "
                  f"{limpos} limpos.")
    return "\n".join(linhas)


@register(
    "tool_auditar_estrutura",
    "Varredura estrutural do codigo Python, modulo a modulo, com veredito por ficheiro. DEFEITOS: funcao orfa (nunca usada), simbolo privado importado de outro modulo, corpos identicos por AST, nome publico repetido em dois modulos. AVISOS: funcao publica usada so dentro do modulo (candidata a privada), wrapper de <=3 linhas, corpo semelhante com literais diferentes. Inclui o app.py nas referencias, da os totais (modulos, pastas, linhas, caracteres, funcoes, classes) no cabecalho e em cada pasta, e nomeia os modulos de tools/ que sao apoio. Traça ainda o grafo de dependencias entre pastas e marca a DEPENDENCIA INVERTIDA (importar de uma camada acima da propria) — o sinal de peca no modulo errado. Uma subpasta pode ser varrida sozinha sem que isso torne orfa a funcao que so e chamada de outra pasta. Sem 'caminho_relativo' varre src/backend inteiro.",
    {
        'caminho_relativo': {"tipo": "STRING", "desc": "Pasta ou ficheiro a varrer (omitido = src/backend)", "padrao": ""},
        'detalhado': {"tipo": "BOOLEAN", "desc": "Incluir o inventario de itens de topo de cada modulo", "padrao": False},
    },
    disponivel="sempre",
)
def tool_auditar_estrutura(caminho_relativo="", detalhado=False):
    alvo = caminho_relativo or "src/backend"
    emit_event("executing", function=f"Auditoria estrutural: {alvo}")
    pasta_abs, erro = resolver_caminho(alvo)
    if erro:
        return erro
    if not os.path.exists(pasta_abs):
        return f"ERRO: '{alvo}' nao existe no projeto."
    fontes, arvores, invalidos = _modulos_da_pasta(pasta_abs)
    if not fontes:
        return f"ERRO: nenhum modulo .py encontrado em '{alvo}'."
    externos = _referencias_do_arranque(pasta_abs)
    fora, n_fora = _referencias_fora_do_ambito(pasta_abs, arvores)
    return _relatorio(alvo, fontes, arvores, invalidos, externos, bool(detalhado), fora, n_fora)
