import hashlib
import os
import re
import sys
import threading
import time

from src.backend.memory.glossary import (
    load_glossary,
    save_glossary,
    achar_linha_identificador,
    caminho_do_arquivo,
    localizar_alvos,
)
from src.backend.memory.store import coletar_notas_knowledge
from src.backend.services.session import (
    carregar_marcas_de_restauro,
    carregar_verificacoes_de_restauro,
    gravar_verificacoes_de_restauro,
)
from src.backend.state import estado, registar_aviso_de_mudanca

INTERVALO_MANUTENCAO = 300.0
INTERVALO_PENDENCIAS = 20.0
MAX_PENDENCIAS = 12

_agenda_lock = threading.Lock()
_ultima_manutencao = [0.0]
_pendencias_cache = {"t": 0.0, "valor": []}

_RE_FICHEIRO = re.compile(r"(?<![\w])[~\w./\\-]+\.(?:py|js|ts|json|html|css|md|ya?ml)\b")

_NEGACOES = ("nao ", "não ", "em vez de", "antigo", "substituid", "renomeado")
_NEGACOES_A_FRENTE = (
    "nao existe",
    "não existe",
    "nao esta",
    "não esta",
    "planeado",
    "planejado",
    "por criar",
    "a criar",
    "falta criar",
    "a construir",
)
_COMANDOS = ("node ", "python ", "py ", "npm ", "npx ", "deno ", "bun ")

_PASTAS_FORA_DO_INDICE = {".git", "__pycache__", ".mypy_cache", ".ruff_cache",
                          ".venv", "venv", "dist", "build"}

_BASENAMES_CACHE_SEGUNDOS = 600.0

_basenames_cache = {"raiz": "", "t": 0.0, "valor": set()}
_codigo_cache = {"raiz": "", "t": 0.0, "valor": set()}
_caminhos_cache = {"raiz": "", "t": 0.0, "valor": {}}
_indice_lock = threading.Lock()
_indice_em_andamento = threading.Event()

_EXTENSOES_CODIGO = (".py", ".js", ".ts")


def _assinatura(caminho):
    """(mtime, tamanho) do ficheiro; None quando ele nao existe."""
    try:
        st = os.stat(caminho)
    except OSError:
        return None
    return [round(st.st_mtime, 3), st.st_size]


def _remover_duplicatas_exatas(termos):
    """Remove entradas duplicadas EXATAS (mesmo termo, identificador e aliases).

    Duplicata exata e lixo puro: nao acrescenta sinonimo nenhum e entra DUAS
    vezes no contexto (o glossario e injetado a cada rodada). Sinonimos
    legitimos - mesmo identificador com termos diferentes - nao sao tocados.
    """
    vistos = set()
    saida = []
    removidas = []
    for t in termos:
        chave = (
            (t.get("termo") or "").strip().lower(),
            (t.get("identificador") or "").strip().lower(),
            tuple(sorted((a or "").strip().lower() for a in (t.get("aliases") or []))),
        )
        if chave in vistos:
            removidas.append(t.get("termo") or t.get("identificador") or "?")
            continue
        vistos.add(chave)
        saida.append(t)
    return saida, removidas


def _agrupar_notas_por_corpo(notas):
    """Agrupa notas pelo corpo normalizado: mesmo texto == mesma assinatura.

    Ponto unico da comparacao de corpos, partilhado por `_notas_a_remover` (que
    apaga as redundantes exatas no ciclo) e por `_notas_duplicadas` (que as
    reporta no diagnostico) - antes cada uma repetia a normalizacao + sha1.
    """
    grupos = {}
    for n in notas or []:
        chave = re.sub(r"\s+", " ", (n.get("conteudo") or "")).strip().lower()
        if not chave:
            continue
        digest = hashlib.sha1(chave.encode("utf-8")).hexdigest()
        grupos.setdefault(digest, []).append(n)
    return grupos


def _notas_a_remover(notas):
    """Nomes das notas a apagar por terem corpo IDENTICO a uma mais recente.

    Duplicata de corpo e lixo puro - nao acrescenta informacao nenhuma e entra
    duas vezes na busca semantica. Mantem a mais RECENTE (mtime) e devolve as
    restantes. Funcao pura: nao toca no disco, por isso e testavel sozinha.
    """
    remover = []
    for grupo in _agrupar_notas_por_corpo(notas).values():
        if len(grupo) < 2:
            continue
        grupo.sort(key=lambda n: n.get("mtime") or 0, reverse=True)
        remover.extend(n.get("nome") for n in grupo[1:])
    return remover


def _apagar_notas(nomes):
    """Apaga o .md de cada nota e o drawer correspondente do vetor."""
    # import-local: os modulos de vetor/pasta carregam chromadb e nao devem pesar o import de instructions
    from src.backend.memory.store import garantir_pasta_knowledge
    from src.backend.memory.vector import excluir_memoria_do_vetor
    pasta = garantir_pasta_knowledge()
    if not pasta:
        return []
    apagadas = []
    for nome in nomes:
        try:
            os.remove(os.path.join(pasta, f"{nome}.md"))
        except OSError:
            continue
        try:
            excluir_memoria_do_vetor(nome)
        except Exception:
            pass
        apagadas.append(nome)
    return apagadas


def curar_notas_redundantes(notas=None):
    """Remove AUTOMATICAMENTE as notas de corpo identico (acao, nao aviso).

    Antes so existia o aviso em `pendencias_de_memoria`; este e o passo que age,
    chamado pelo ciclo de manutencao a cada rodada. Mantem sempre a nota mais
    recente de cada grupo. Devolve os nomes efetivamente apagados.
    """
    if notas is None:
        notas = coletar_notas_knowledge()
    nomes = _notas_a_remover(notas)
    if not nomes:
        return []
    apagadas = _apagar_notas(nomes)
    if apagadas:
        _pendencias_cache["t"] = 0.0
        print(f"[memoria] notas redundantes removidas automaticamente: {', '.join(apagadas)}")
    return apagadas


def verificar_glossario(forcar=False):
    """Remede no ficheiro as linhas do glossario cujo arquivo MUDOU.

    E o que torna o glossario auto-curavel: cada entrada guarda em
    `localizacao["conferido"]` a assinatura (mtime + tamanho) do arquivo no
    momento em que foi medida. Enquanto o arquivo nao mexer, a entrada nao e
    remedida (custo ~0); quando mexer - ou quando a entrada nunca foi medida -
    a linha e remedida e a assinatura atualizada. Entradas cujo alvo desapareceu
    ficam marcadas com `localizacao["ausente"] = True` - NUNCA sao apagadas,
    porque decidir remover um mapeamento e do agente (a auto-curacao so MEDE, nao
    julga). O que ela faz e SEGUIR o simbolo: quando o identificador esta
    definido num unico sitio do projeto, o alvo da entrada e reapontado para la
    sozinho; quando ha mais do que um candidato, a proposta sai no relatorio.

    Devolve o relatorio: {"corrigidos": [...], "ausentes": [...], "sem_arquivo": N}.
    """
    dados = load_glossary()
    termos = dados.get("termos", []) if isinstance(dados, dict) else []
    relatorio = {"corrigidos": [], "ausentes": [], "realocados": [], "candidatos": {},
                 "sem_arquivo": 0, "duplicatas_removidas": []}
    if not termos:
        return relatorio

    termos, duplicatas = _remover_duplicatas_exatas(termos)
    if duplicatas:
        relatorio["duplicatas_removidas"] = duplicatas
    alterou = bool(duplicatas)

    if not estado.get("pasta_raiz"):
        relatorio["sem_pasta"] = True
        if alterou:
            dados["termos"] = termos
            save_glossary(dados)
        return relatorio

    por_arquivo = {}
    for t in termos:
        loc = t.get("localizacao") or {}
        arquivo = loc.get("arquivo", "")
        if arquivo:
            por_arquivo.setdefault(arquivo, []).append(t)
        else:
            relatorio["sem_arquivo"] += 1

    pendentes = []

    for arquivo, entradas in por_arquivo.items():
        caminho = caminho_do_arquivo(arquivo)
        assin = _assinatura(caminho) if caminho else None
        if assin is None:
            for t in entradas:
                loc = t.setdefault("localizacao", {})
                pendentes.append((arquivo, t, loc, "arquivo nao existe"))
                if not loc.get("ausente"):
                    loc["ausente"] = True
                    loc.pop("conferido", None)
                    alterou = True
            continue

        for t in entradas:
            loc = t.setdefault("localizacao", {})
            if not forcar and loc.get("conferido") == assin:
                continue
            medida = achar_linha_identificador(arquivo, t.get("identificador", ""))
            loc["conferido"] = assin
            alterou = True
            if medida is None:
                pendentes.append((arquivo, t, loc, "alvo nao encontrado"))
                loc["ausente"] = True
                continue
            loc.pop("ausente", None)
            if str(loc.get("linha", "")).strip() != str(medida):
                relatorio["corrigidos"].append(
                    f"{t.get('identificador', '')} ({arquivo}): {loc.get('linha')} -> {medida}"
                )
                loc["linha"] = medida

    if pendentes and _reapontar_alvos(pendentes, relatorio):
        alterou = True

    if alterou:
        dados["termos"] = termos
        save_glossary(dados)
    return relatorio


def _reapontar_alvos(pendentes, relatorio):
    """Segue o simbolo quando o alvo do glossario mudou de sitio.

    Antes isto parava na queixa: a entrada ficava marcada como ausente e cabia ao
    agente descobrir para onde o simbolo foi, com um `mapear_codigo` por entrada.
    Aqui o identificador e procurado onde ele esta DEFINIDO e, havendo um unico
    sitio, o glossario e corrigido sozinho - isso e medicao, nao julgamento. Com
    mais do que um candidato nada e escrito: a proposta vai no relatorio, porque
    escolher entre dois sitios e decisao de quem conhece o codigo.
    """
    localizacoes = localizar_alvos([t.get("identificador", "") for _, t, _, _ in pendentes])
    realocou = False
    for arquivo, t, loc, motivo in pendentes:
        ident = t.get("identificador", "")
        locais = localizacoes.get((ident or "").strip()) or []
        if len(locais) == 1 and locais[0][0] != arquivo:
            novo_arquivo, nova_linha = locais[0]
            relatorio["realocados"].append(f"{ident}: {arquivo} -> {novo_arquivo}:{nova_linha}")
            loc["arquivo"] = novo_arquivo
            loc["linha"] = nova_linha
            loc.pop("ausente", None)
            caminho_novo = caminho_do_arquivo(novo_arquivo)
            loc["conferido"] = _assinatura(caminho_novo) if caminho_novo else None
            realocou = True
            continue
        relatorio["ausentes"].append(f"{ident} -> {arquivo} ({motivo})")
        if locais:
            relatorio["candidatos"][f"{ident} -> {arquivo}"] = locais
    return realocou


def relatar_verificacao(relatorio):
    """Formata o relatorio da verificacao para a tool do agente."""
    linhas = []
    dups = relatorio.get("duplicatas_removidas") or []
    if dups:
        linhas.append(f"Duplicatas exatas removidas: {len(dups)} ({', '.join(dups)})")
    linhas.append(f"Linhas corrigidas por medicao no ficheiro: {len(relatorio.get('corrigidos') or [])}")
    linhas += [f"  {c}" for c in (relatorio.get("corrigidos") or [])]
    realocados = relatorio.get("realocados") or []
    if realocados:
        linhas.append(f"Simbolo mudou de sitio e o glossario seguiu sozinho ({len(realocados)}):")
        linhas += [f"  {r}" for r in realocados]
    ausentes = relatorio.get("ausentes") or []
    if ausentes:
        linhas.append(f"ALVO NAO ENCONTRADO ({len(ausentes)}) - nao achei o identificador no arquivo "
                      "nem em nenhum ficheiro do projeto, ou achei-o em mais do que um sitio. "
                      "Nada foi reescrito; a decisao e sua:")
        linhas += [f"  {a}" for a in ausentes]
        for chave, locais in (relatorio.get("candidatos") or {}).items():
            onde = ", ".join(f"{arquivo}:{linha}" for arquivo, linha in locais)
            linhas.append(f"      ? {chave} - definido em: {onde}")
    if relatorio.get("sem_arquivo"):
        linhas.append(f"Sem arquivo registado: {relatorio['sem_arquivo']}")
    if relatorio.get("sem_pasta"):
        linhas.append("ERRO: nenhuma pasta de projeto esta selecionada. Sem ela nao consigo abrir os "
                      "arquivos para medir as linhas. Selecione a pasta e repita.")
    return "\n".join(linhas)


def agendar_manutencao(intervalo=INTERVALO_MANUTENCAO):
    """Dispara a auto-curacao do glossario em background, no maximo 1x por intervalo.

    Chamada a cada rodada sem bloquear nada (fire-and-forget): a resposta e
    gerada com o glossario atual e a thread daemon cura-o para a proxima. E o
    que substitui a dependencia de o agente "lembrar" de verificar - o sistema
    verifica sozinho sempre que um ficheiro indexado muda.
    """
    agora = time.time()
    with _agenda_lock:
        if agora - _ultima_manutencao[0] < intervalo:
            return False
        _ultima_manutencao[0] = agora
    threading.Thread(target=_ciclo_manutencao, daemon=True).start()
    return True


def _ciclo_manutencao():
    try:
        _basenames_projeto()
        relatorio = verificar_glossario()
        corrigidos = len(relatorio.get("corrigidos") or [])
        ausentes = len(relatorio.get("ausentes") or [])
        realocados = len(relatorio.get("realocados") or [])
        if corrigidos or ausentes or realocados:
            print(f"[memoria] glossario auto-curado: {corrigidos} linha(s) remedidas, "
                  f"{realocados} alvo(s) reapontado(s), {ausentes} alvo(s) ausente(s)")
    except Exception as e:
        print(f"[memoria] auto-curacao do glossario falhou: {e}")
    try:
        curar_notas_redundantes()
    except Exception as e:
        print(f"[memoria] auto-curacao das notas falhou: {e}")


def _coletar_basenames():
    """(nomes, raiz) de tudo o que conta como 'visivel': projeto + deps.

    O detector de referencia morta olhava so o caminho LITERAL citado na nota:
    uma nota que escreve `renderer.js` era dada como obsoleta mesmo com o
    ficheiro vivo em `src/frontend/js/chat/renderer.js`. Isso enchia o bloco de
    pendencias de centenas de falsos positivos (458 refs "mortas" em 71 notas) -
    ruido injetado em TODAS as rodadas.

    O indice cobre o projeto E as dependencias instaladas (o node_modules do
    projeto e o site-packages do interpretador em uso): as notas citam tambem
    ficheiros de libs (monaco, xterm, werkzeug) e esses estao vivos.
    """
    raiz = estado.get("pasta_raiz") or ""
    bases = []
    if raiz and os.path.isdir(raiz):
        bases.append(raiz)
    venv = os.path.dirname(os.path.dirname(sys.executable or ""))
    site_packages = os.path.join(venv, "Lib", "site-packages")
    if os.path.isdir(site_packages):
        bases.append(site_packages)
    nomes = set()
    for base in bases:
        for _pasta, dirs, arquivos in os.walk(base):
            dirs[:] = [d for d in dirs if d not in _PASTAS_FORA_DO_INDICE]
            for a in arquivos:
                nomes.add(a.lower())
    return nomes, raiz


def _coletar_nomes_no_codigo():
    """Nomes de ficheiro citados pelo proprio codigo do projeto.

    Uma nota que cita `.axio/bootstrap.json` ou `checkpoint.json` esta CORRETA:
    sao ficheiros que o codigo cria em runtime (bootstrap.py, session.py), logo
    nao existem no disco enquanto nao forem usados. Acusar a nota de obsoleta
    era falso positivo. Aqui os nomes mencionados nos .py/.js do projeto sao
    indexados e a referencia que aparece neles deixa de ser dada como morta.
    node_modules fica de fora (codigo de terceiros, nao descreve a memoria).
    """
    raiz = estado.get("pasta_raiz") or ""
    nomes = set()
    if not raiz or not os.path.isdir(raiz):
        return nomes
    excluir = _PASTAS_FORA_DO_INDICE | {"node_modules"}
    for pasta, dirs, arquivos in os.walk(raiz):
        dirs[:] = [d for d in dirs if d not in excluir]
        for a in arquivos:
            if not a.endswith(_EXTENSOES_CODIGO):
                continue
            try:
                with open(os.path.join(pasta, a), "r", encoding="utf-8", errors="ignore") as f:
                    texto = f.read()
            except OSError:
                continue
            for m in _RE_FICHEIRO.findall(texto):
                nomes.add(os.path.basename(m.replace("\\", "/")).lower())
    return nomes


def _construir_indice():
    try:
        nomes, raiz = _coletar_basenames()
        citados = _coletar_nomes_no_codigo()
        with _indice_lock:
            _basenames_cache.update({"raiz": raiz, "t": time.time(), "valor": nomes})
            _codigo_cache.update({"raiz": raiz, "t": time.time(), "valor": citados})
    except Exception:
        pass
    finally:
        _indice_em_andamento.clear()


def _indice(cache):
    """Devolve um indice em cache, construindo-o em BACKGROUND se for preciso.

    Varrer o site-packages (opencv, onnxruntime, 143 pacotes) leva ~17s - caro
    demais para o caminho sincrono da injecao. A thread daemon constroi os dois
    indices (basenames e nomes citados no codigo) e guarda-os em cache; enquanto
    nao estiverem prontos devolve o que houver. Com o indice vazio
    `_referencias_mortas` NAO acusa nada (conservador): um aviso a mais e ruido,
    por isso o sistema prefere nao avisar a avisar errado.
    """
    raiz = estado.get("pasta_raiz") or ""
    if cache["raiz"] == raiz and cache["valor"] and time.time() - cache["t"] < _BASENAMES_CACHE_SEGUNDOS:
        return cache["valor"]
    if not _indice_em_andamento.is_set():
        _indice_em_andamento.set()
        threading.Thread(target=_construir_indice, daemon=True).start()
    return cache["valor"] if cache["raiz"] == raiz else set()


def _basenames_projeto():
    return _indice(_basenames_cache)


def _nomes_no_codigo():
    return _indice(_codigo_cache)


def invalidar_indice():
    """Marca os indices de basenames/nomes citados como velhos (TTL expirado).

    Chamado sempre que o projeto ganha ou perde ficheiros. Sem isto, um ficheiro
    criado ha segundos ainda nao esta no indice em cache (que leva ~17s a varrer
    o site-packages) e uma nota que o cite aparece como 'REF MORTA' - um aviso
    falso injetado na rodada seguinte.
    """
    for cache in (_basenames_cache, _codigo_cache, _caminhos_cache):
        cache["t"] = 0.0


registar_aviso_de_mudanca(invalidar_indice)


def _parece_url(alvo):
    """Dominio escrito sem esquema (ex: 'sqlite.org/lang_vacuum.html').

    Pasta oculta do projeto ('.axio/...') tambem tem ponto no primeiro segmento,
    por isso comecar por ponto exclui a hipotese de dominio.
    """
    if "/" not in alvo:
        return False
    primeiro = alvo.split("/", 1)[0]
    if primeiro.startswith("."):
        return False
    return "." in primeiro


def _parece_lista_de_extensoes(alvo):
    """Lista de extensoes em prosa (ex: 'js/.jsx/.ts'), nao um ficheiro.

    O sinal e um segmento INTERNO comecar por ponto. A primeira parte pode
    comecar por ponto por outro motivo legitimo ('.axio/'), por isso nao conta.
    """
    return any(s.startswith(".") for s in alvo.split("/")[1:])


def _referencias_mortas(conteudo):
    """Ficheiros citados numa nota que nao existem em NENHUM lugar visivel.

    Filtra antes de acusar: URLs sem esquema, listas de extensoes em prosa,
    tokens de tema com dois pontos (`colors.x.css`), ficheiros de libs
    instaladas e caminhos com `~` (o palace do mempalace vive em
    ~/.mempalace/palace) nao sao notas obsoletas - sao apenas texto ou vivem
    fora do projeto, onde nao ha como validar. O `~` e expandido antes do
    os.path.exists: sem isso o token perdia o til e existia sempre "morto".
    So o til SEGUIDO de separador e caminho de casa; o til colado a um nome
    (`~filesystem.py:207`) e prosa ("aprox. no ficheiro") e nesse caso o que
    se valida e o nome sem o til.
    """
    raiz = estado.get("pasta_raiz") or ""
    basenames = _basenames_projeto()
    if not basenames:
        return []
    citados = _nomes_no_codigo()
    mortas = []
    texto = conteudo or ""
    for m in _RE_FICHEIRO.finditer(texto):
        bruto = m.group(0)
        if bruto.startswith(("http://", "https://")):
            continue
        antes = texto[max(0, m.start() - 16):m.start()].lower()
        if any(t in antes for t in _NEGACOES) or any(t in antes for t in _COMANDOS):
            continue
        fim = texto.find("\n", m.end())
        depois = texto[m.end():fim if fim != -1 else m.end() + 60].lower()
        if any(t in depois for t in _NEGACOES_A_FRENTE):
            continue
        alvo = bruto.replace("\\", "/")
        if alvo.startswith("./"):
            alvo = alvo[2:]
        if alvo.startswith("~") and not alvo.startswith("~/"):
            alvo = alvo[1:]
        if _parece_url(alvo) or _parece_lista_de_extensoes(alvo):
            continue
        if "/" not in alvo and alvo.count(".") > 1:
            continue
        if os.path.exists(os.path.expanduser(alvo)) or (raiz and os.path.exists(os.path.join(raiz, alvo))):
            continue
        if os.path.basename(alvo).lower() in basenames:
            continue
        if os.path.basename(alvo).lower() in citados:
            continue
        mortas.append(bruto)
    return sorted(set(mortas))


_RE_SIMBOLO_COM_ARQUIVO = re.compile(
    r"(?<![\w./\\-])([\w./\\-]+\.(?:py|js|ts|css|html))(?:::|:)([A-Za-z_$][\w$]*)"
)
_RE_ARQUIVO_COM_SIMBOLO_ANTES = re.compile(
    r"([A-Za-z_$][\w$]*)\s*\(\s*([\w./\\-]+\.(?:py|js|ts|css|html))\s*:"
)
_LIMITE_VERIFICACOES_SIMBOLO = 120
_RE_TOKEN_BRUTO = re.compile(r"[A-Za-z_$][\w$-]*")
_MAX_CAMINHOS_CITADOS = 14
_LIMITE_BYTES_CONFERENCIA = 512 * 1024


def _parece_simbolo(nome):
    """Token com forma de codigo (snake_case/CamelCase), nao palavra de prosa.

    Exigir underscore, ou maiuscula INTERNA com minuscula no meio, corta o grosso
    dos falsos positivos: 'linha' e 'arquivo' sao prosa, 'dedup_nota' e
    'ROOMS_PROTEGIDAS' sao simbolos, e 'DEFINITIVAS' (titulo de seccao em
    maiusculas) NAO passa - palavra toda em maiusculas sem underscore e prosa,
    nao constante.
    """
    if len(nome) < 4:
        return False
    if "_" in nome:
        return True
    return any(c.isupper() for c in nome[1:]) and any(c.islower() for c in nome)


def _simbolos_ausentes(conteudo, orcamento):
    """Simbolos que a nota aponta e que ja nao existem no ficheiro citado.

    Fecha a classe que `_referencias_mortas` nao alcanca: aqui o FICHEIRO existe,
    mas a funcao/classe/constante que a nota cita desapareceu ou foi renomeada -
    a forma mais comum de nota obsoleta mas sintaticamente valida. A medicao
    reusa `achar_linha_identificador` (o mesmo medidor do glossario, com
    fallback por substring), o que a torna conservadora: so acusa o que nao
    aparece MESMO no ficheiro. `orcamento` e uma lista [int] partilhada entre
    notas para limitar as leituras de ficheiro por passagem.
    """
    texto = conteudo or ""
    pares = set(_RE_SIMBOLO_COM_ARQUIVO.findall(texto))
    pares.update((arquivo, nome) for nome, arquivo in _RE_ARQUIVO_COM_SIMBOLO_ANTES.findall(texto))
    ausentes = []
    for arquivo, nome in sorted(pares):
        nome = nome.split(".")[0]
        if orcamento[0] <= 0 or not _parece_simbolo(nome):
            continue
        if not os.path.isfile(caminho_do_arquivo(arquivo)):
            continue
        orcamento[0] -= 1
        if achar_linha_identificador(arquivo, nome) is None:
            ausentes.append(f"{arquivo}:{nome}")
    return sorted(set(ausentes))


def _chave_da_nota(nota):
    """Identidade do corpo da nota: muda quando a nota e reescrita."""
    texto = f"{nota.get('nome', '')}\n{nota.get('conteudo', '')}"
    return hashlib.sha1(texto.encode("utf-8", "replace")).hexdigest()[:16]


def _caminhos_por_nome():
    """{nome em minusculas: [caminhos]} do projeto, para resolver o que a nota cita.

    A conferencia precisa do FICHEIRO e a nota escreve `workspace.js`, que vive
    em src/frontend/js/editor/workspace.js. Resolver pelo NOME e a diferenca
    entre conferir 265 notas e nao conferir nenhuma: medido a 2026-09-26, o
    caminho literal resolvia 17 de 131.
    """
    raiz = estado.get("pasta_raiz") or ""
    if (_caminhos_cache["raiz"] == raiz and _caminhos_cache["valor"]
            and time.time() - _caminhos_cache["t"] < _BASENAMES_CACHE_SEGUNDOS):
        return _caminhos_cache["valor"]
    valor = {}
    if raiz and os.path.isdir(raiz):
        for pasta, dirs, arquivos in os.walk(raiz):
            dirs[:] = [d for d in dirs if d not in _PASTAS_FORA_DO_INDICE and not d.startswith(".")]
            for arquivo in arquivos:
                valor.setdefault(arquivo.lower(), []).append(os.path.join(pasta, arquivo))
    _caminhos_cache.update({"raiz": raiz, "t": time.time(), "valor": valor})
    return valor


def _tokens_do_ficheiro(caminho):
    try:
        if os.path.getsize(caminho) > _LIMITE_BYTES_CONFERENCIA:
            return set()
        with open(caminho, "r", encoding="utf-8", errors="ignore") as f:
            return _tokens_de_codigo(f.read())
    except OSError:
        return set()


def _tokens_de_codigo(texto):
    """Identificadores, classes CSS e flags - as formas de nome que apontam codigo.

    O `-` entra no token bruto (`--dur-7`, `chat-content-up`,
    `enable-gpu-rasterization`) e a escolha entre identificador e nome composto
    por hifen e feita em Python, nunca com um segundo regex: medido a
    2026-09-26, um regex so de hifens em CSS minificado gastava 7,7s por causa
    do backtracking, e a conferencia inteira passou de 1,2s para 8,4s.
    """
    return {t for t in _RE_TOKEN_BRUTO.findall(texto)
            if _parece_simbolo(t) or t.count("-") >= 2}


def _conferir_nota_no_disco(nota, memoria):
    """Prova positiva de que a nota ainda descreve o codigo que esta no disco.

    A pergunta e estreita de proposito: algum identificador que a nota nomeia
    continua vivo num dos ficheiros que ela cita? Um so basta - a nota cita
    sempre coisas de fora (comandos, libs, outros modulos) e exigir todos
    acusaria quase todas. Ao contrario dos detetores que ACUSAM, este exige
    prova para RETIRAR o aviso: sem prova, o aviso fica de pe.
    """
    corpo = nota.get("conteudo") or ""
    indice = _caminhos_por_nome()
    citados = {os.path.basename(m.replace("\\", "/")).lower() for m in _RE_FICHEIRO.findall(corpo)}
    caminhos = []
    for nome in sorted(citados):
        caminhos.extend(indice.get(nome, ())[:2])
        if len(caminhos) >= _MAX_CAMINHOS_CITADOS:
            break
    if not caminhos:
        return False
    tokens = _tokens_de_codigo(corpo)
    if not tokens:
        return False
    for caminho in caminhos[:_MAX_CAMINHOS_CITADOS]:
        if caminho not in memoria:
            memoria[caminho] = _tokens_do_ficheiro(caminho)
        if tokens & memoria[caminho]:
            return True
    return False


def _notas_anteriores_a_restauro(notas, acusadas=None):
    """Notas escritas ANTES de um restauro que tocou nos ficheiros que elas citam.

    Depois de o projeto ser reposto para tras o ficheiro continua a existir e o
    simbolo pode ate existir: a nota e que descreve uma versao que ja nao esta la
    e nada no texto dela o denuncia. O criterio e temporal - conta so a nota
    escrita antes do restauro, porque a reescrita depois ja descreve o codigo de
    agora.

    O aviso NAO e um pedido de conferencia a mao: cada nota suspeita e conferida
    aqui contra o disco e a conferencia fica gravada, para nao se repetir na
    rodada seguinte. Quem sobra no aviso e so o que o codigo nao conseguiu
    conferir - sem prova, o aviso fica de pe, em vez de se dar por conferido o
    que ninguem leu.
    """
    marcas = carregar_marcas_de_restauro()
    if not marcas:
        return []
    acusadas = acusadas or set()
    conferidas = carregar_verificacoes_de_restauro()
    itens = []
    for nota in notas:
        corpo = nota.get("conteudo") or ""
        citados = {os.path.basename(m.replace("\\", "/")).lower() for m in _RE_FICHEIRO.findall(corpo)}
        itens.append({"nota": nota, "chave": _chave_da_nota(nota), "citados": citados})
    vivas = {i["chave"] for i in itens}
    guardadas = {c: v for c, v in conferidas.items() if c in vivas}
    memoria = {}
    novas = 0
    por_marca = []
    for marca in marcas:
        ts = float(marca.get("ts") or 0)
        repostos = {str(n).lower() for n in (marca.get("nomes") or []) if str(n).strip()}
        if not ts or not repostos:
            continue
        afetadas = []
        for item in itens:
            nota = item["nota"]
            if (nota.get("mtime") or 0) >= ts or not (item["citados"] & repostos):
                continue
            if nota.get("nome", "") in acusadas or ts <= (guardadas.get(item["chave"]) or 0):
                continue
            if _conferir_nota_no_disco(nota, memoria):
                guardadas[item["chave"]] = ts
                novas += 1
                continue
            afetadas.append(nota.get("nome", ""))
        if afetadas:
            por_marca.append((ts, afetadas))
    if guardadas != conferidas:
        gravar_verificacoes_de_restauro(guardadas)
    if novas:
        print(f"[memoria] {novas} nota(s) suspeita(s) de restauro conferida(s) contra o disco")
    avisos = []
    for ts, afetadas in por_marca[-2:]:
        quando = time.strftime("%d/%m/%Y %H:%M", time.localtime(ts))
        amostra = ", ".join(f'"{a}"' for a in afetadas[:4])
        resto = f" (+{len(afetadas) - 4})" if len(afetadas) > 4 else ""
        avisos.append(f"{len(afetadas)} nota(s) anterior(es) ao restauro de {quando} citam ficheiro(s) repostos "
                      f"por ele e o codigo nao conseguiu conferir: {amostra}{resto} - leia estas antes de as citar")
    return avisos


def pendencias_de_memoria(intervalo=INTERVALO_PENDENCIAS):
    """O que exige JUIZO: o sistema AVISA, o agente cura (regra 24).

    So devolve o que e MEDIVEL por codigo: entradas do glossario cujo alvo
    desapareceu e notas de knowledge que citam ficheiros (ou simbolos dentro
    deles) que ja nao existem.
    Notas de corpo IDENTICO ja nao entram aqui: `curar_notas_redundantes` apaga-as
    sozinho no ciclo de manutencao (acao, nao aviso). Uma nota desatualizada mas
    sintaticamente valida NAO e detetavel aqui - essa continua a depender da
    leitura do agente. Lista vazia = memoria saudavel (o bloco nem aparece na
    injecao, por isso nao polui quando esta tudo limpo).
    """
    agora = time.time()
    if agora - _pendencias_cache["t"] < intervalo:
        return list(_pendencias_cache["valor"])

    linhas = []
    try:
        dados = load_glossary()
        for t in dados.get("termos", []):
            loc = t.get("localizacao") or {}
            if loc.get("ausente"):
                linhas.append(f'glossario: "{t.get("termo", "")}" -> {t.get("identificador", "")} '
                              f'({loc.get("arquivo", "")}) - alvo nao encontrado no ficheiro')
    except Exception:
        pass

    try:
        notas = coletar_notas_knowledge()
        orcamento = [_LIMITE_VERIFICACOES_SIMBOLO]
        acusadas = set()
        outras = []
        for nota in notas:
            nome = nota.get("nome", "")
            corpo = nota.get("conteudo", "")
            mortas = _referencias_mortas(corpo)
            if mortas:
                acusadas.add(nome)
                amostra = ", ".join(mortas[:5])
                resto = f" (+{len(mortas) - 5})" if len(mortas) > 5 else ""
                outras.append(f'nota "{nome}" cita ficheiro(s) inexistente(s): {amostra}{resto}')
            ausentes = _simbolos_ausentes(corpo, orcamento)
            if ausentes:
                acusadas.add(nome)
                amostra = ", ".join(ausentes[:5])
                resto = f" (+{len(ausentes) - 5})" if len(ausentes) > 5 else ""
                outras.append(f'nota "{nome}" cita simbolo(s) que ja nao existe(m): {amostra}{resto}')
        linhas.extend(_notas_anteriores_a_restauro(notas, acusadas))
        linhas.extend(outras)
    except Exception:
        pass

    if len(linhas) > MAX_PENDENCIAS:
        linhas = linhas[:MAX_PENDENCIAS] + [f"... e mais {len(linhas) - MAX_PENDENCIAS} (ver acao='listar')"]
    _pendencias_cache["t"] = agora
    _pendencias_cache["valor"] = linhas
    return list(linhas)


def deduplicar_textos(textos):
    """Remove repeticoes na injecao de memorias.

    A busca semantica pode devolver a MESMA drawer varias vezes (ou notas
    espelhadas com corpo identico) e a injecao literal chegava a repetir a
    mesma frase 4x no contexto, gastando tokens sem acrescentar nada. Compara
    pelo texto normalizado (espacos colapsados, minusculas).
    """
    vistos = set()
    saida = []
    for texto in textos:
        chave = re.sub(r"\s+", " ", (texto or "")).strip().lower()
        if not chave or chave in vistos:
            continue
        vistos.add(chave)
        saida.append(texto)
    return saida


def _duplicados_glossario(termos):
    """Entradas que apontam para o MESMO identificador ou repetem o mesmo termo."""
    por_ident = {}
    por_termo = {}
    for t in termos:
        ident = (t.get("identificador") or "").strip().lower()
        termo = (t.get("termo") or "").strip().lower()
        if ident:
            por_ident.setdefault(ident, []).append(t.get("termo") or ident)
        if termo:
            por_termo.setdefault(termo, []).append(t.get("identificador") or termo)
    avisos = []
    for ident, nomes in por_ident.items():
        if len(nomes) > 1:
            avisos.append(f"identificador '{ident}' em {len(nomes)} entradas: {', '.join(nomes)}")
    for termo, idents in por_termo.items():
        if len(idents) > 1:
            avisos.append(f"termo '{termo}' repetido em {len(idents)} entradas")
    return avisos


def _notas_duplicadas(notas):
    """Notas de knowledge com o corpo IDENTICO (comparado apos normalizar espacos)."""
    return [f"{len(v)} notas com corpo identico: {', '.join(n.get('nome') or '' for n in v)}"
            for v in _agrupar_notas_por_corpo(notas).values() if len(v) > 1]


def raio_x_da_injecao(query=None, incluir_vetor=False):
    """Mede TUDO o que entra no contexto e aponta o que e lixo, por camada.

    Responde a 'a minha memoria esta limpa?' com numeros medidos em vez de
    impressao: glossario (total, alvos ausentes, nunca medidos, duplicados),
    notas de knowledge (total, KB, referencias mortas, corpos identicos) e,
    opcionalmente, o vetor (drawers/tamanho) e a busca semantica de uma query
    (hits, quantos a deduplicacao removeu, faixa de similaridade). Cada camada
    e isolada com try/except: uma peca que falhe nao derruba o diagnostico.
    """
    relatorio = {}

    termos = []
    try:
        dados = load_glossary()
        termos = dados.get("termos", []) if isinstance(dados, dict) else []
    except Exception:
        termos = []
    locs = [(t.get("localizacao") or {}) for t in termos]
    relatorio["glossario"] = {
        "total": len(termos),
        "sem_arquivo": sum(1 for loc in locs if not loc.get("arquivo")),
        "nunca_medidas": sum(1 for loc in locs if loc.get("arquivo") and not loc.get("conferido")),
        "ausentes": [t.get("identificador", "") for t in termos if (t.get("localizacao") or {}).get("ausente")],
        "duplicados": _duplicados_glossario(termos),
    }

    notas = []
    try:
        notas = coletar_notas_knowledge()
    except Exception:
        pass
    kb = sum(len((n.get("conteudo") or "").encode("utf-8")) for n in notas) / 1024
    refs = {}
    simbolos = {}
    orcamento = [_LIMITE_VERIFICACOES_SIMBOLO]
    for n in notas:
        corpo = n.get("conteudo", "")
        mortas = _referencias_mortas(corpo)
        if mortas:
            refs[n.get("nome", "")] = mortas
        ausentes = _simbolos_ausentes(corpo, orcamento)
        if ausentes:
            simbolos[n.get("nome", "")] = ausentes
    relatorio["notas"] = {
        "total": len(notas),
        "kb": round(kb, 1),
        "com_ref_morta": refs,
        "simbolos_ausentes": simbolos,
        "duplicadas": _notas_duplicadas(notas),
    }

    try:
        relatorio["restauros"] = {
            "marcas": len(carregar_marcas_de_restauro()),
            "conferidas": len(carregar_verificacoes_de_restauro()),
            "por_conferir": _notas_anteriores_a_restauro(notas, set()),
        }
    except Exception:
        pass

    if incluir_vetor:
        try:
            # import-local: puxar o modulo do vetor (chromadb) no topo pesaria o import de instructions
            from src.backend.memory.vector import vetor_status
            relatorio["vetor"] = {"status": vetor_status()}
        except Exception as e:
            relatorio["vetor"] = {"erro": str(e)}

    if query:
        try:
            # import-local: so a busca sob demanda justifica carregar o modulo do vetor
            from src.backend.memory.vector import buscar_memorias_com_timeout, wing_da_pasta
            wing = wing_da_pasta(estado.get("pasta_raiz") or "")
            dados_busca = buscar_memorias_com_timeout(
                query=query,
                palace_path=os.path.expanduser("~/.mempalace/palace"),
                wing=wing,
                n_results=8,
            )
            hits = dados_busca.get("results", []) if isinstance(dados_busca, dict) else []
            textos = [h.get("text", "") for h in hits]
            unicos = deduplicar_textos(textos)
            sims = [h.get("similarity") for h in hits if h.get("similarity") is not None]
            relatorio["busca"] = {
                "query": query,
                "hits": len(hits),
                "apos_dedup": len(unicos),
                "removidos_por_dedup": len(hits) - len(unicos),
                "similaridade_min": round(min(sims), 3) if sims else None,
                "similaridade_max": round(max(sims), 3) if sims else None,
                "erro": dados_busca.get("error") if isinstance(dados_busca, dict) else None,
            }
        except Exception as e:
            relatorio["busca"] = {"erro": str(e)}

    total_problemas = (
        len(relatorio["glossario"]["ausentes"])
        + len(relatorio["glossario"]["duplicados"])
        + len(relatorio["notas"]["com_ref_morta"])
        + len(relatorio["notas"]["simbolos_ausentes"])
        + len(relatorio["notas"]["duplicadas"])
        + len((relatorio.get("restauros") or {}).get("por_conferir") or [])
    )
    relatorio["problemas"] = total_problemas
    relatorio["veredito"] = ("LIMPA" if total_problemas == 0
                             else f"{total_problemas} ponto(s) a curar - ver abaixo")
    return relatorio


def formatar_raio_x(relatorio):
    """Formata o raio-X da injecao para leitura do agente."""
    g = relatorio.get("glossario") or {}
    n = relatorio.get("notas") or {}
    linhas = [f"RAIO-X DA MEMORIA INJETADA: {relatorio.get('veredito', '?')}", ""]
    linhas.append(f"GLOSSARIO: {g.get('total', 0)} termos "
                  f"({g.get('sem_arquivo', 0)} sem arquivo, {g.get('nunca_medidas', 0)} nunca medidos)")
    for a in g.get("ausentes") or []:
        linhas.append(f"  ALVO AUSENTE: {a}")
    for d in g.get("duplicados") or []:
        linhas.append(f"  DUPLICADO: {d}")
    linhas.append(f"NOTAS: {n.get('total', 0)} notas, {n.get('kb', 0)} KB")
    for nome, mortas in (n.get("com_ref_morta") or {}).items():
        linhas.append(f"  REF MORTA em '{nome}': {', '.join(mortas[:6])}")
    for nome, ausentes in (n.get("simbolos_ausentes") or {}).items():
        linhas.append(f"  SIMBOLO AUSENTE em '{nome}': {', '.join(ausentes[:6])}")
    for d in n.get("duplicadas") or []:
        linhas.append(f"  REDUNDANTE: {d}")
    r = relatorio.get("restauros") or {}
    if r:
        linhas.append(f"RESTAUROS DE CODIGO: {r.get('marcas', 0)} marca(s), "
                      f"{r.get('conferidas', 0)} nota(s) conferida(s) contra o disco sozinhas")
        for a in r.get("por_conferir") or []:
            linhas.append(f"  POR CONFERIR: {a}")
    if "vetor" in relatorio:
        v = relatorio["vetor"]
        linhas.append(f"VETOR: {v.get('status') or v.get('erro')}")
    if "busca" in relatorio:
        b = relatorio["busca"]
        if b.get("erro"):
            linhas.append(f"BUSCA: erro - {b['erro']}")
        else:
            linhas.append(f"BUSCA '{b.get('query')}': {b.get('hits')} hits, {b.get('apos_dedup')} "
                          f"apos dedup ({b.get('removidos_por_dedup')} repetidos), "
                          f"similaridade {b.get('similaridade_min')}-{b.get('similaridade_max')}")
    return "\n".join(linhas)
