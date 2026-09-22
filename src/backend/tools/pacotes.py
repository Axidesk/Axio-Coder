"""Pacotes instalados atras da ultima versao publicada no registo (PyPI + npm).

Mede em fio de fundo (a rede nunca bloqueia o painel), guarda em cache com TTL de
24h e revalida contra o ambiente instalado, marcando os pacotes que OUTRO
instalado trava (ex: sympy exige mpmath<1.4). A ferramenta
tool_verificar_dependencias traduz esta medicao para o modelo antes de instalar,
atualizar ou pinar qualquer coisa.
"""
import os
import sys
import json
import ast
import time
import shutil
import subprocess
import threading
import importlib.util

import requests

from packaging.requirements import InvalidRequirement, Requirement
from packaging.version import InvalidVersion, Version

from src.backend.state import MSG_SEM_PASTA, emit_event, estado
from src.backend.tools.dependencias import normalizar_pacote
from src.backend.tools.projeto_comum import (
    gravar_cache_projeto,
    ler_cache_projeto,
)
from src.backend.tools.registry import register

TTL_DESATUALIZADOS = 86400
TIMEOUT_DESATUALIZADOS = 90
INTERVALO_RETENTATIVA = 300
INTERVALO_REVALIDACAO = 60
ESPERA_MEDICAO_DEPENDENCIAS = 30.0
LIMITE_LISTA_DEPENDENCIAS = 40
TIMEOUT_REGISTO = 10
REGISTOS = (
    ("pip", "https://pypi.org/pypi/{0}/json"),
    ("npm", "https://registry.npmjs.org/{0}/latest"),
)
_SCRIPT_RESTRICOES = (
    "import importlib.metadata as m, json; "
    "print(json.dumps({d.metadata['Name']: list(d.requires or []) "
    "for d in m.distributions() if d.metadata['Name']}))"
)
_estado_desatualizados = {"raiz": "", "correndo": False, "ts": 0.0,
                          "pacotes": {}, "versoes": {}, "erro": "", "falha_ts": 0.0,
                          "revalidado_ts": 0.0, "instalado_assinatura": ""}
_trava_desatualizados = threading.Lock()


def python_do_projeto(raiz):
    """Interpretador que mede o pip: o venv do projeto, senao o que corre o Axio.

    Sem isto, medir outro projeto usava o venv do Axio e listava as dependencias
    erradas - o projeto ficava marcado com pacotes que nao sao dele.
    """
    for sub in (".venv", "venv", "env"):
        for partes in (("Scripts", "python.exe"), ("bin", "python")):
            caminho = os.path.join(raiz, sub, *partes)
            if os.path.exists(caminho):
                return caminho
    return sys.executable

def _correr_manifesto(comando, cwd):
    """Corre um comando de manifesto e devolve `(json, erro)`.

    O `npm outdated` sai com codigo 1 quando encontra pacotes desatualizados
    (docs.npmjs.com), logo o codigo de saida NAO e sinal de erro aqui: so a
    ausencia de JSON legivel conta.
    """
    try:
        proc = subprocess.run(
            comando, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=TIMEOUT_DESATUALIZADOS,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        return None, "tempo excedido"
    except (OSError, subprocess.SubprocessError) as e:
        return None, str(e)
    texto = (proc.stdout or "").strip()
    if not texto:
        return {}, ""
    try:
        return json.loads(texto), ""
    except ValueError:
        return None, "resposta ilegivel"

def _pip_desatualizados(raiz):
    """Pacotes Python instalados atras da ultima versao publicada no PyPI."""
    dados, erro = _correr_manifesto(
        [python_do_projeto(raiz), "-m", "pip", "list", "--outdated", "--format=json"], raiz)
    if erro:
        return {}, "pip: " + erro
    saida = {}
    for item in dados or []:
        nome = item.get("name") if isinstance(item, dict) else None
        if nome:
            saida[normalizar_pacote(nome)] = {"atual": item.get("version") or "",
                                               "ultima": item.get("latest_version") or "",
                                               "nome": nome,
                                               "gestor": "pip"}
    return saida, ""

def _npm_desatualizados(raiz):
    """Dependencias de node instaladas atras da ultima versao do registo npm."""
    if not os.path.exists(os.path.join(raiz, "package.json")):
        return {}, ""
    npm = shutil.which("npm")
    if not npm:
        return {}, "npm: nao encontrado"
    comando = [npm, "outdated", "--json"]
    if sys.platform == "win32" and npm.lower().endswith((".cmd", ".bat")):
        comando = ["cmd", "/c"] + comando
    dados, erro = _correr_manifesto(comando, raiz)
    if erro:
        return {}, "npm: " + erro
    saida = {}
    for nome, item in (dados or {}).items():
        if isinstance(item, dict):
            saida[normalizar_pacote(nome)] = {"atual": item.get("current") or "",
                                               "ultima": item.get("latest") or "",
                                               "gestor": "npm"}
    return saida, ""

def _restricoes_instaladas(raiz):
    """O que cada pacote instalado exige, no ambiente que mede o pip.

    Le os metadados (Requires-Dist) no interpretador do projeto, sem tocar a
    rede: e o que permite dizer que um pacote esta travado por outro em vez de o
    apresentar como uma atualizacao ao alcance do utilizador.
    """
    dados, erro = _correr_manifesto(
        [python_do_projeto(raiz), "-c", _SCRIPT_RESTRICOES], raiz)
    if erro or not isinstance(dados, dict):
        return {}
    return dados

def _exigencia(texto):
    """Uma exigencia do metadado (`nome>=1.0; marcador`) ou nada, se ilegivel."""
    try:
        return Requirement(texto)
    except (InvalidRequirement, TypeError):
        return None

def _marcador_ativo(marcador):
    """Se o marcador da exigencia se aplica a este ambiente.

    Marcador ilegivel conta como inativo: um aviso falso de incompatibilidade
    vale menos do que o silencio.
    """
    if marcador is None:
        return True
    try:
        return bool(marcador.evaluate())
    except Exception:
        return False

def _permitido(specifier, versao):
    """Se a versao satisfaz a exigencia (comparacao ilegivel conta como sim)."""
    if not specifier:
        return True
    try:
        return specifier.contains(versao, prereleases=True)
    except (InvalidVersion, ValueError):
        return True

def _margem_que_trava(specifier, versao):
    """So as clausulas da exigencia que a versao nao satisfaz.

    Uma exigencia como `!=4.21.0,<7.0.0,>=3.20.2` (dos google-cloud-*) nao cabe
    no tooltip: aqui fica so o `<7.0.0`, que e o que trava a subida. Sem clausula
    culpada (exigencia ilegivel), mostra-se a exigencia inteira.
    """
    travam = [str(parte) for parte in specifier if not _permitido(parte, versao)]
    return ",".join(travam) or str(specifier)

def _pedidos_por_pacote(restricoes):
    """Indexa as exigencias instaladas por pacote exigido (1 leitura, N consultas)."""
    pedidos = {}
    for dono, exigencias in (restricoes or {}).items():
        for texto in exigencias or []:
            exigencia = _exigencia(texto)
            if exigencia is None or not exigencia.specifier:
                continue
            pedidos.setdefault(normalizar_pacote(exigencia.name), []).append((dono, exigencia))
    for lista in pedidos.values():
        lista.sort(key=lambda par: par[0].lower())
    return pedidos

def _preso_por(chave, ultima, pedidos):
    """O instalado que trava este pacote de subir para `ultima`, ou nada."""
    if not ultima:
        return None
    for dono, exigencia in pedidos.get(chave, []):
        if not _marcador_ativo(exigencia.marker):
            continue
        if not _permitido(exigencia.specifier, ultima):
            return {"dono": dono, "margem": _margem_que_trava(exigencia.specifier, ultima)}
    return None

def _marcar_presos(pacotes, restricoes):
    """Anota cada pacote desatualizado que outro instalado esta a segurar.

    Saida do PyPI que o dono instalado nao aceita: o painel pinta estes de
    amarelo e mostra a restricao, para o sinal nao se confundir com um pacote
    que o utilizador pode simplesmente atualizar. So o pip entra: as versoes npm
    vem de outro registo e nao se restringem neste formato.
    """
    if not restricoes:
        return
    pedidos = _pedidos_por_pacote(restricoes)
    for chave, info in pacotes.items():
        if info.get("gestor") == "npm":
            continue
        if (info.get("preso") or {}).get("origem") == "nova":
            continue
        preso = _preso_por(chave, info.get("ultima"), pedidos)
        if preso:
            info["preso"] = preso
        else:
            info.pop("preso", None)

_OPERADORES_DE_TETO = ("<", "<=", "==", "===", "~=")

def _trava_por_versao_nova(pacotes, instalado):
    """Marca o pacote cuja versao nova obriga a DESCER outro instalado.

    O `_preso_por` so olha num sentido: quem depende do pacote a subir. Falta o
    contrario - a propria versao publicada pode exigir, de outra dependencia,
    uma versao INFERIOR a que esta instalada (ex: trame-vtk 2.11 exige
    trame-client<4 enquanto o trame instalado ja exige >=4). O pip aceita a
    subida, desce o vizinho e deixa-o partido. Exige-se clausula de teto (`<`,
    `==`, `~=`): sem ela a exigencia em falta resolve-se subindo, nao descendo.
    """
    for chave, info in pacotes.items():
        if info.get("gestor") == "npm" or info.get("preso"):
            continue
        nome = info.get("nome") or chave
        ultima = info.get("ultima")
        if not ultima:
            continue
        for texto in _exigencias_publicadas(nome, ultima):
            exigencia = _exigencia(texto)
            if exigencia is None or not exigencia.specifier:
                continue
            if not _marcador_ativo(exigencia.marker):
                continue
            if not any(parte.operator in _OPERADORES_DE_TETO for parte in exigencia.specifier):
                continue
            versao = instalado.get(normalizar_pacote(exigencia.name))
            if not versao or _permitido(exigencia.specifier, versao):
                continue
            info["preso"] = {"dono": f"{nome} {ultima}",
                             "margem": f"exige {exigencia.name}{exigencia.specifier} e tem {versao} instalado",
                             "origem": "nova"}
            break

def _medir_desatualizados(raiz):
    """Mede no PyPI e no registo npm o que esta atras da ultima versao publicada.

    Unico ponto desta funcao que toca a rede; quem a chama trata do cache e do
    fundo (a resposta da API nunca espera por ela).
    """
    pacotes = {}
    erros = []
    for medir in (_pip_desatualizados, _npm_desatualizados):
        try:
            achados, erro = medir(raiz)
        except Exception as e:
            achados, erro = {}, str(e)
        pacotes.update(achados)
        if erro:
            erros.append(erro)
    if pacotes:
        _marcar_presos(pacotes, _restricoes_instaladas(raiz))
        instalado, _ = _versao_instalada(raiz)
        _trava_por_versao_nova(pacotes, instalado)
    return pacotes, "; ".join(erros)

def _medir_desatualizados_em_fundo(raiz):
    try:
        pacotes, erro = _medir_desatualizados(raiz)
        if erro and not pacotes:
            _estado_desatualizados["erro"] = erro
            _estado_desatualizados["falha_ts"] = time.time()
            return
        _estado_desatualizados.update({"pacotes": pacotes, "erro": erro,
                                       "ts": time.time(), "falha_ts": 0.0})
        gravar_cache_projeto("projeto_outdated.json",
                              {"pacotes": pacotes, "erro": erro})
    finally:
        _estado_desatualizados["correndo"] = False

def _versao_instalada(raiz):
    """Versoes instaladas agora no ambiente do projeto (consulta LOCAL ao pip).

    Sem rede: e o que permite comparar o que o cache marca com o que esta
    instalado de facto, sem pagar dezenas de segundos ao PyPI so para descobrir
    que ja nao ha nada a assinalar.
    """
    dados, erro = _correr_manifesto(
        [python_do_projeto(raiz), "-m", "pip", "list", "--format=json"], raiz)
    if erro:
        return {}, erro
    return {normalizar_pacote(item["name"]): item.get("version") or ""
            for item in (dados or [])
            if isinstance(item, dict) and item.get("name")}, ""

def _nome_pacote_npm(chave):
    """Nome do pacote a partir de uma chave do lockfile, so no nivel de topo.

    `node_modules/@xterm/xterm` -> `@xterm/xterm`. As chaves aninhadas
    (`node_modules/a/node_modules/b`) ficam de fora: nao sao o que foi declarado
    no package.json.
    """
    prefixo = "node_modules/"
    if not chave.startswith(prefixo):
        return ""
    nome = chave[len(prefixo):]
    return "" if "/node_modules/" in nome else nome

def _versoes_npm(raiz):
    """Versoes resolvidas no package-lock.json, por pacote de topo.

    O lockfile e o registo local do que o npm instalou: le-se o ficheiro em vez
    de correr o npm. Sem lockfile nao ha versoes npm a mostrar, e isso nao e erro.
    """
    try:
        with open(os.path.join(raiz, "package-lock.json"), "r", encoding="utf-8") as f:
            dados = json.load(f)
    except (OSError, ValueError):
        return {}
    instalados = dados.get("packages") if isinstance(dados, dict) else None
    if not isinstance(instalados, dict):
        return {}
    versoes = {}
    for chave, info in instalados.items():
        if not isinstance(chave, str) or not isinstance(info, dict):
            continue
        nome = _nome_pacote_npm(chave)
        versao = info.get("version") or ""
        if nome and versao:
            versoes[normalizar_pacote(nome)] = versao
    return versoes

def _versoes_todas(raiz, instalado):
    """Versoes instaladas de todos os pacotes do projeto, para o tooltip do painel."""
    versoes = dict(instalado or {})
    versoes.update(_versoes_npm(raiz))
    return versoes

def _assinatura_instalado(instalado):
    """Identidade barata do ambiente instalado: muda quando algo sobe ou desce."""
    if not instalado:
        return ""
    return "|".join(nome + "==" + str(versao)
                    for nome, versao in sorted(instalado.items()))

def _presos_do_ambiente(raiz, pacotes, instalado):
    """Remarca os travados quando o ambiente instalado mudou desde a ultima vez.

    A marca `preso` (ex: sympy exige mpmath<1.4) nao vem do PyPI: e derivada dos
    metadados do ambiente. Uma cache gravada antes desta marca - ou um dono da
    restricao atualizado a meio da sessao - deixaria o painel em silencio ou a
    mentir durante as 24h do TTL. A assinatura das versoes instaladas diz quando
    vale a pena pagar a leitura dos metadados; sem mudanca, devolve tudo intacto.
    """
    if not pacotes:
        return pacotes
    assinatura = _assinatura_instalado(instalado)
    with _trava_desatualizados:
        if assinatura and assinatura == _estado_desatualizados["instalado_assinatura"]:
            return pacotes
    restricoes = _restricoes_instaladas(raiz)
    if not restricoes:
        return pacotes
    marcados = {chave: dict(info) for chave, info in pacotes.items()}
    _marcar_presos(marcados, restricoes)
    with _trava_desatualizados:
        _estado_desatualizados["instalado_assinatura"] = assinatura
    return marcados

def _ja_atualizado(instalada, ultima):
    """Diz se a versao instalada alcancou (ou passou) a ultima publicada."""
    if not instalada or not ultima:
        return False
    try:
        return Version(instalada) >= Version(ultima)
    except InvalidVersion:
        return instalada == ultima

def _revalidar_desatualizados(raiz, pacotes):
    """Tira da lista quem ja foi instalado depois da medicao.

    Compara cada pacote marcado com a versao que esta instalada agora: quem ja
    alcancou a ultima versao que a medicao conhecia deixa de ser um aviso. E o
    que faz o sinal do painel desaparecer logo a seguir a um `pip install` feito
    com o Axio fechado, sem esperar as 24h do TTL. So o pip passa por aqui: o npm
    fica intacto e a sua cache e invalidada pelo lockfile (_cache_vencido_pelo_npm).
    Devolve tambem as versoes instaladas, que o painel usa no tooltip de cada pacote.
    """
    instalado, erro = _versao_instalada(raiz)
    if erro or not instalado:
        return pacotes, {}
    filtrados = {}
    for nome, info in pacotes.items():
        if info.get("gestor") == "npm":
            filtrados[nome] = info
            continue
        atual = instalado.get(nome) or info.get("atual") or ""
        if not _ja_atualizado(atual, info.get("ultima")):
            novo = dict(info)
            novo["atual"] = atual
            filtrados[nome] = novo
    return filtrados, instalado

def _mtime_manifestos_npm(raiz):
    """Data da ultima mexida nos manifestos npm (instalar atualiza o lock)."""
    mtime = 0.0
    for nome in ("package.json", "package-lock.json"):
        try:
            mtime = max(mtime, os.path.getmtime(os.path.join(raiz, nome)))
        except OSError:
            continue
    return mtime

def _cache_vencido_pelo_npm(raiz, ts):
    """True quando os manifestos npm sao mais recentes que a medicao guardada."""
    return bool(ts) and _mtime_manifestos_npm(raiz) > ts

def _revalidar_se_preciso(raiz, agora):
    """Revalida o cache contra o ambiente instalado, no maximo 1x por minuto.

    O painel consulta a rota a cada 3s e o `pip list` local custa 1-2s: sem esta
    janela, revalidar em cada pedido tornava o polling caro. Quando a revalidacao
    muda a lista, o resultado vai para o cache (memoria e disco) e as consultas
    seguintes ja respondem corrigidas.
    """
    with _trava_desatualizados:
        if (agora - _estado_desatualizados["revalidado_ts"]) < INTERVALO_REVALIDACAO:
            return
        _estado_desatualizados["revalidado_ts"] = agora
        pacotes = _estado_desatualizados["pacotes"]
        erro = _estado_desatualizados["erro"]
    filtrados, instalado = _revalidar_desatualizados(raiz, pacotes)
    filtrados = _presos_do_ambiente(raiz, filtrados, instalado)
    versoes = _versoes_todas(raiz, instalado)
    with _trava_desatualizados:
        if versoes:
            _estado_desatualizados["versoes"] = versoes
        if filtrados != pacotes:
            _estado_desatualizados.update({"pacotes": filtrados, "ts": time.time(),
                                           "erro": erro})
    if filtrados != pacotes:
        gravar_cache_projeto("projeto_outdated.json",
                              {"pacotes": filtrados, "erro": erro})

def _garantir_medicao_desatualizados(raiz, agora):
    """Hidrata a cache (memoria -> disco) e, se estiver vencida, mede em fundo."""
    with _trava_desatualizados:
        if _estado_desatualizados["raiz"] != raiz:
            _estado_desatualizados.update({"raiz": raiz, "ts": 0.0, "pacotes": {},
                                           "versoes": {}, "erro": "", "falha_ts": 0.0,
                                           "revalidado_ts": 0.0, "instalado_assinatura": ""})
        if not _estado_desatualizados["ts"]:
            disco = ler_cache_projeto("projeto_outdated.json", ("ts",))
            if disco:
                _estado_desatualizados.update({"ts": disco.get("ts") or 0.0,
                                               "pacotes": disco.get("pacotes") or {},
                                               "erro": disco.get("erro") or ""})
        if _estado_desatualizados["ts"] and (agora - _estado_desatualizados["ts"]) < TTL_DESATUALIZADOS:
            if not _cache_vencido_pelo_npm(raiz, _estado_desatualizados["ts"]):
                return
        if _estado_desatualizados["correndo"]:
            return
        if (agora - _estado_desatualizados["falha_ts"]) < INTERVALO_RETENTATIVA:
            return
        _estado_desatualizados["correndo"] = True
        threading.Thread(target=_medir_desatualizados_em_fundo, args=(raiz,), daemon=True).start()

def pacotes_desatualizados():
    """Estado dos pacotes atras da ultima versao publicada (PyPI + npm).

    Responde sempre depressa: com cache dentro da janela de 24h devolve-a logo e,
    caso contrario, arranca a medicao num fio de fundo e responde "a_verificar".
    A rede nunca bloqueia o painel: `pip list --outdated` pergunta ao PyPI por
    centenas de pacotes e leva dezenas de segundos.
    """
    raiz = estado.get("pasta_raiz", "")
    if not raiz or not os.path.isdir(raiz):
        return {"erro": MSG_SEM_PASTA}
    agora = time.time()
    _garantir_medicao_desatualizados(raiz, agora)
    atual = _estado_desatualizados
    if atual["ts"] and (agora - atual["ts"]) < TTL_DESATUALIZADOS:
        if _cache_vencido_pelo_npm(raiz, atual["ts"]):
            situacao = "a_verificar"
        else:
            _revalidar_se_preciso(raiz, agora)
            situacao = "pronto"
    elif atual["correndo"] or not atual["falha_ts"]:
        situacao = "a_verificar"
    else:
        situacao = "indisponivel"
    return {"estado": situacao, "pacotes": atual["pacotes"],
            "versoes": atual["versoes"],
            "erro": atual["erro"], "ts": atual["ts"]}

def _trava_de_pacote(info):
    """Sufixo do pacote que outro instalado segura (ex: sympy exige mpmath<1.4), ou vazio."""
    preso = info.get("preso") or {}
    if not preso:
        return ""
    return (f" [TRAVADO: {preso.get('dono')} exige {preso.get('margem')} - subir para "
            f"{info.get('ultima')} quebra essa exigencia]")

def _linha_pacote(nome, info):
    """Uma linha por pacote desatualizado: instalada -> ultima publicada."""
    return (f"- {nome}: {info.get('atual') or '?'} -> {info.get('ultima') or '?'} "
            f"({info.get('gestor') or 'pip'}){_trava_de_pacote(info)}")

def _ficha_de_pacote(pacote, pacotes, versoes):
    """Consulta de UM pacote: instalada, ultima publicada e trava, quando existirem."""
    alvo = normalizar_pacote(pacote)
    instalada = next((f"{nome} {versao}" for nome, versao in versoes.items()
                      if normalizar_pacote(nome) == alvo), "")
    info = pacotes.get(alvo) or {}
    if info:
        return (f"- {info.get('gestor') or 'pip'}: instalada {instalada or info.get('atual')} -> "
                f"ultima publicada {info.get('ultima')}{_trava_de_pacote(info)}")
    if instalada:
        return f"- {instalada}: ja e a ultima versao publicada que o registo oferece"
    achados, erro = _consultar_registo(pacote)
    if not achados:
        return (f"- {pacote}: nao consta do ambiente instalado e os registos nao responderam "
                f"({erro}). Confirme o nome antes de instalar qualquer coisa.")
    partes = " | ".join(f"{gestor} {ultima}{_texto_do_exige(exige)}"
                        for gestor, ultima, exige in achados)
    return f"- {pacote}: NAO esta instalado. Ultima publicada: {partes}"

def _consultar_registo(pacote):
    """(achados, erro): o que cada registo oficial publica com esse nome, todos os que respondem.

    Devolve todos e nao o primeiro porque o mesmo nome pode existir nos dois (`three` e 0.8.0
    no PyPI e 0.186.0 no npm): escolher um em silencio daria a versao errada. O `exige` de
    cada achado traz os peerDependencies do npm ou o requires-python do PyPI.
    """
    achados, erros = [], []
    for gestor, molde in REGISTOS:
        try:
            resposta = requests.get(molde.format(pacote), timeout=TIMEOUT_REGISTO,
                                    headers={"Accept": "application/json"})
        except requests.RequestException as exc:
            erros.append(f"{gestor}: {type(exc).__name__}")
            continue
        if resposta.status_code != 200:
            erros.append(f"{gestor}: HTTP {resposta.status_code}")
            continue
        try:
            dados = resposta.json()
        except ValueError:
            erros.append(f"{gestor}: resposta ilegivel")
            continue
        if gestor == "npm":
            ultima = dados.get("version") or ""
            exige = dados.get("peerDependencies") or {}
        else:
            info = dados.get("info") or {}
            ultima = info.get("version") or ""
            exige = {"requires-python": info["requires_python"]} if info.get("requires_python") else {}
        if ultima:
            achados.append((gestor, ultima, exige))
        else:
            erros.append(f"{gestor}: resposta sem versao")
    return achados, "; ".join(erros)

def _exigencias_publicadas(nome, versao):
    """O `requires_dist` que o PyPI publica para essa versao (vazio se nao responder)."""
    try:
        resposta = requests.get(f"https://pypi.org/pypi/{nome}/{versao}/json",
                                timeout=TIMEOUT_REGISTO, headers={"Accept": "application/json"})
        if resposta.status_code != 200:
            return []
        info = (resposta.json() or {}).get("info") or {}
    except (requests.RequestException, ValueError):
        return []
    return info.get("requires_dist") or []

def _texto_do_exige(exige):
    """Sufixo com o que a versao publicada exige, quando o registo o declara."""
    if not exige:
        return ""
    pares = ", ".join(f"{nome} {margem}" for nome, margem in sorted(exige.items()))
    return f" | exige: {pares}"

def _texto_dependencias(dados, pacote=""):
    """Medicao de dependencias em texto: o que subir, o que esta travado, o que falhou.

    A lista sai partida em "atualizaveis" e "travados" porque a decisao e diferente:
    um travado nao pode subir sozinho (outro instalado recusa a versao nova), logo
    sugerir a subida dele seria um erro que so apareceria no fim do pip install.
    """
    situacao = dados.get("estado") or "indisponivel"
    pacotes = dados.get("pacotes") or {}
    versoes = dados.get("versoes") or {}
    linhas = ["=== DEPENDENCIAS DO PROJETO (PyPI + npm) ==="]
    for nome in _nomes_pedidos(pacote):
        linhas.append(_ficha_de_pacote(nome, pacotes, versoes))
    desatualizados = sorted(pacotes.items())
    travados = [(nome, info) for nome, info in desatualizados if info.get("preso")]
    livres = [(nome, info) for nome, info in desatualizados if not info.get("preso")]
    linhas.append(f"Instalados medidos: {len(versoes)} | desatualizados: {len(desatualizados)} "
                  f"({len(livres)} atualizaveis agora, {len(travados)} travados por outro pacote)")
    if livres:
        linhas.append("Atualizaveis (instalar a ultima versao, sem pinar de memoria):")
        linhas += [_linha_pacote(nome, info) for nome, info in livres[:LIMITE_LISTA_DEPENDENCIAS]]
    if travados:
        linhas.append("Travados (a ultima versao quebra uma exigencia de outro instalado - NAO force):")
        linhas += [_linha_pacote(nome, info) for nome, info in travados[:LIMITE_LISTA_DEPENDENCIAS]]
    if not desatualizados:
        linhas.append("Nada atras do registo: as dependencias instaladas estao na ultima versao publicada.")
    if situacao == "a_verificar":
        linhas.append("AVISO: a medicao ainda corre em background (o pip consulta o PyPI pacote a pacote e "
                      "demora dezenas de segundos): a lista acima pode estar INCOMPLETA - repita a chamada "
                      "daqui a pouco antes de concluir que esta tudo em dia.")
    elif situacao == "indisponivel":
        linhas.append("AVISO: a medicao falhou (rede ou registo fora do alcance). Isto NAO quer dizer que "
                      "esta tudo em dia - confirme a versao no registo oficial antes de instalar.")
    if dados.get("erro"):
        linhas.append(f"Erro da medicao: {dados['erro']}")
    return "\n".join(linhas)

def _nomes_pedidos(texto):
    """Nomes de pacote pedidos numa chamada: virgula, ponto-e-virgula ou espaco separam."""
    partes = []
    for bruto in str(texto or "").replace(";", ",").replace("\n", ",").split(","):
        partes.extend(bruto.split())
    return [nome for nome in (p.strip() for p in partes) if nome]


def bloco_dependencias():
    """Bloco do prompt com o que esta atras do registo, lido da cache (nunca toca na rede).

    O agente tem de saber que ha atualizacoes a fazer sem perguntar ao PyPI a cada
    rodada; a medicao que o painel ja faz fica em cache e chega aqui. Sem medicao
    guardada devolve "" e o bloco nem entra na injecao.
    """
    raiz = estado.get("pasta_raiz", "")
    if not raiz:
        return ""
    with _trava_desatualizados:
        pacotes = dict(_estado_desatualizados["pacotes"])
        ts = _estado_desatualizados["ts"]
    if not pacotes:
        disco = ler_cache_projeto("projeto_outdated.json", ("ts",))
        pacotes = (disco or {}).get("pacotes") or {}
        ts = (disco or {}).get("ts") or ts
    if not pacotes:
        return ""
    atualizaveis = sorted(nome for nome, info in pacotes.items() if not info.get("preso"))
    travados = len(pacotes) - len(atualizaveis)
    quando = time.strftime("%d/%m %H:%M", time.localtime(ts)) if ts else "sem data"
    lista = ", ".join(f"{nome} {pacotes[nome].get('atual')}->{pacotes[nome].get('ultima')}"
                      for nome in atualizaveis[:8])
    return (
        "=== DEPENDENCIAS ATRAS DO REGISTO (manutencao autonoma, regras 4.2-4.4) ===\n"
        f"{len(pacotes)} pacote(s) atras da ultima publicada (medido {quando}): "
        f"{len(atualizaveis)} atualizavel(is) agora"
        + (f" - {lista}" if lista else "")
        + f" - e {travados} travado(s) por outro instalado (esses NAO se forcam).\n"
        "Rodada longa ou mexida em requirements.txt/package.json: suba o que sobe sem quebra, prove que "
        "nada partiu e reporte o antes/depois. O detalhe sai de tool_verificar_dependencias.\n"
    )

@register(
    "tool_verificar_dependencias",
    'Lista as dependencias instaladas que estao atras da ultima versao publicada (PyPI/npm), separando as que podem subir agora das que outro pacote trava, e diz a versao instalada de um pacote especifico. Se o pacote pedido AINDA NAO ESTIVER INSTALADO, consulta os registos oficiais e devolve a ultima versao publicada com as exigencias que ela declara (peerDependencies no npm, requires-python no PyPI) - e o caminho para saber a versao a pedir antes de instalar. Use ANTES de instalar, atualizar ou pinar qualquer dependencia (requirements.txt/package.json): a versao a instalar deve ser a mais recente compativel com o que ja existe, nunca uma versao lembrada de memoria.',
    {
        'pacote': {"tipo": "STRING", "desc": 'Um ou VARIOS pacotes, separados por virgula ou espaco (ex: "mediapipe, three", "flask jwt"). Vazio devolve a lista completa das dependencias desatualizadas.', "padrao": ""},
    },
)
def tool_verificar_dependencias(pacote=""):
    emit_event("executing", function="Medindo dependencias desatualizadas")
    raiz = estado.get("pasta_raiz", "")
    if not raiz or not os.path.isdir(raiz):
        return MSG_SEM_PASTA
    fim = time.time() + ESPERA_MEDICAO_DEPENDENCIAS
    dados = pacotes_desatualizados()
    while dados.get("estado") == "a_verificar" and time.time() < fim:
        time.sleep(1.0)
        dados = pacotes_desatualizados()
    return _texto_dependencias(dados, pacote)

LIMITE_API_DEPENDENCIA = 8000
LIMITE_DECLARACAO_JS = 24 * 1024 * 1024
LIMITE_LINHAS_FILTRO = 400
_CAMPOS_DE_API_JS = ("main", "module", "types", "typings", "exports", "bin")
_DECLARACOES_JS = ("index.d.ts", "types/index.d.ts", "dist/index.d.ts", "lib/index.d.ts")
_FONTES_JS = (".js", ".mjs", ".cjs")
MAX_FICHEIROS_FONTE = 200
LIMITE_VARREDURA_FONTE = 16 * 1024 * 1024
MAX_TRECHOS_FONTE = 12
LARGURA_TRECHO_FONTE = 320


def _ler_fonte(caminho, limite=LIMITE_API_DEPENDENCIA):
    try:
        with open(caminho, "r", encoding="utf-8", errors="ignore") as f:
            return f.read(limite)
    except OSError:
        return ""


def _filtrar_linhas(texto, filtro):
    """Linhas com o termo, COM o numero de linha a frente.

    O numero e o que permite voltar ao ficheiro e ver o contexto que a linha sozinha nao
    da; e o que se diz quando o termo existe mas o chamador nao o encontra.
    """
    if not filtro:
        return texto
    chave = filtro.lower()
    guardadas = [f"{numero}: {linha}" for numero, linha in enumerate(texto.splitlines(), 1)
                 if chave in linha.lower()]
    if not guardadas:
        return f"(nenhuma linha com '{filtro}')"
    if len(guardadas) > LIMITE_LINHAS_FILTRO:
        sobra = len(guardadas) - LIMITE_LINHAS_FILTRO
        return "\n".join(guardadas[:LIMITE_LINHAS_FILTRO]) + f"\n... (+{sobra} linhas com o termo)"
    return "\n".join(guardadas)


def _declaracao_js(pasta, manifesto):
    for campo in ("types", "typings"):
        alvo = manifesto.get(campo)
        if alvo:
            caminho = os.path.join(pasta, alvo)
            if os.path.isfile(caminho):
                return caminho
    for relativo in _DECLARACOES_JS:
        caminho = os.path.join(pasta, relativo)
        if os.path.isfile(caminho):
            return caminho
    candidatas = []
    for raiz, pastas, ficheiros in os.walk(pasta):
        pastas[:] = [p for p in pastas if p != "node_modules" and not p.startswith(".")]
        profundidade = raiz[len(pasta):].count(os.sep)
        if profundidade > 3:
            pastas[:] = []
            continue
        for nome in ficheiros:
            if nome.endswith(".d.ts"):
                candidatas.append((0 if nome == "index.d.ts" else 1, profundidade,
                                   os.path.join(raiz, nome)))
    if not candidatas:
        return ""
    candidatas.sort()
    return candidatas[0][2]


def _ler_declaracao(caminho, filtro):
    """Le a declaracao para procurar um termo.

    Com 'filtro', le o ficheiro INTEIRO: cortar nos primeiros 8000 caracteres fazia a
    ferramenta jurar que um nome nao existia quando ele estava na linha 729 - era o corte
    a mentir, nao o ficheiro. Sem filtro mantem o teto curto (o que sai daqui vai para o
    contexto do modelo) e DIZ que cortou.
    """
    if filtro:
        return _filtrar_linhas(_ler_fonte(caminho, LIMITE_DECLARACAO_JS), filtro)
    try:
        tamanho = os.path.getsize(caminho)
    except OSError:
        tamanho = 0
    texto = _ler_fonte(caminho, LIMITE_API_DEPENDENCIA)
    if tamanho > LIMITE_API_DEPENDENCIA:
        texto += (f"\n... (ficheiro com {tamanho} caracteres; mostrados so os primeiros "
                  f"{LIMITE_API_DEPENDENCIA} - passe 'filtro' para achar um nome la dentro)")
    return texto


def _varrer_fontes(pasta, extensoes, pastas_ignoradas):
    caminhos = []
    for raiz, pastas, ficheiros in os.walk(pasta):
        pastas[:] = [p for p in pastas if p not in pastas_ignoradas and not p.startswith(".")]
        pastas.sort()
        if raiz[len(pasta):].count(os.sep) > 3:
            pastas[:] = []
            continue
        for nome in sorted(ficheiros):
            if os.path.splitext(nome)[1] not in extensoes:
                continue
            caminhos.append(os.path.join(raiz, nome))
            if len(caminhos) >= MAX_FICHEIROS_FONTE:
                return caminhos
    return caminhos


def _candidatos_js(pasta, manifesto):
    caminhos = []
    for campo in ("module", "main", "browser"):
        alvo = manifesto.get(campo)
        if isinstance(alvo, str) and alvo:
            caminho = os.path.join(pasta, alvo)
            if os.path.isfile(caminho):
                caminhos.append(caminho)
    for caminho in _varrer_fontes(pasta, _FONTES_JS, ("node_modules",)):
        if caminho not in caminhos:
            caminhos.append(caminho)
    return caminhos[:MAX_FICHEIROS_FONTE]


def _candidatos_py(pasta):
    return _varrer_fontes(pasta, (".py",), ("__pycache__",))


def _fontes_do_pacote(caminho):
    pasta = os.path.dirname(caminho)
    if os.path.basename(caminho) != "__init__.py" or os.path.basename(pasta) in ("site-packages", "dist-packages"):
        return [caminho]
    return _candidatos_py(pasta)


def _trechos_nos_caminhos(raiz, caminhos, filtro):
    chave = filtro.lower()
    trechos = []
    lidos = 0
    for caminho in caminhos:
        if lidos >= LIMITE_VARREDURA_FONTE:
            break
        try:
            tamanho = os.path.getsize(caminho)
        except OSError:
            continue
        if tamanho > LIMITE_VARREDURA_FONTE - lidos:
            continue
        texto = _ler_fonte(caminho, tamanho + 1)
        lidos += tamanho
        if chave not in texto.lower():
            continue
        relativo = os.path.relpath(caminho, raiz).replace(os.sep, "/")
        for numero, linha in enumerate(texto.splitlines(), 1):
            posicao = linha.lower().find(chave)
            if posicao == -1:
                continue
            comeco = max(0, posicao - LARGURA_TRECHO_FONTE // 2)
            trechos.append(f"{relativo}:{numero}  ...{linha[comeco:comeco + LARGURA_TRECHO_FONTE]}...")
            if len(trechos) >= MAX_TRECHOS_FONTE:
                return trechos
    return trechos


def _trechos_js(raiz, pasta, manifesto, filtro):
    return _trechos_nos_caminhos(raiz, _candidatos_js(pasta, manifesto), filtro)


def _bloco_fonte_js(raiz, pasta, manifesto, filtro, trecho):
    if not filtro:
        return []
    if trecho and trecho != f"(nenhuma linha com '{filtro}')":
        return []
    trechos = _trechos_js(raiz, pasta, manifesto, filtro)
    if not trechos:
        return ["(o termo nao aparece nas declaracoes nem no codigo-fonte do pacote)"]
    return ["\n--- codigo-fonte do pacote (o termo nao esta nas declaracoes) ---"] + trechos


def _api_js(raiz, pacote, filtro):
    pasta = os.path.join(raiz, "node_modules", pacote)
    if not os.path.isdir(pasta):
        return ""
    manifesto = {}
    bruto = _ler_fonte(os.path.join(pasta, "package.json"))
    if bruto:
        try:
            manifesto = json.loads(bruto)
        except ValueError:
            manifesto = {}
    linhas = [f"{manifesto.get('name', pacote)} {manifesto.get('version', '?')} "
              f"(npm, instalado em node_modules/{pacote})"]
    for campo in ("description", "license", "type") + _CAMPOS_DE_API_JS:
        if manifesto.get(campo):
            linhas.append(f"  {campo}: {manifesto[campo]}")
    declaracao = _declaracao_js(pasta, manifesto)
    if declaracao:
        relativo = os.path.relpath(declaracao, raiz).replace(os.sep, "/")
        linhas.append(f"\n--- {relativo} ---")
        trecho = _ler_declaracao(declaracao, filtro)
        linhas.append(trecho)
        linhas.extend(_bloco_fonte_js(raiz, pasta, manifesto, filtro, trecho))
        return "\n".join(linhas)
    leia_me = os.path.join(pasta, "README.md")
    if os.path.isfile(leia_me):
        linhas.append("\n(sem ficheiro de declaracoes; trecho do README)")
        trecho = _ler_declaracao(leia_me, filtro)
        linhas.append(trecho)
        linhas.extend(_bloco_fonte_js(raiz, pasta, manifesto, filtro, trecho))
        return "\n".join(linhas)
    linhas.append("\n(sem ficheiro de declaracoes nem README)")
    linhas.extend(_bloco_fonte_js(raiz, pasta, manifesto, filtro, ""))
    return "\n".join(linhas)


def _assinaturas_py(fonte):
    try:
        arvore = ast.parse(fonte)
    except SyntaxError:
        return []
    linhas = []
    for no in arvore.body:
        if isinstance(no, ast.FunctionDef):
            linhas.append(f"def {no.name}({ast.unparse(no.args)})")
        elif isinstance(no, ast.AsyncFunctionDef):
            linhas.append(f"async def {no.name}({ast.unparse(no.args)})")
        elif isinstance(no, ast.ClassDef):
            bases = ", ".join(ast.unparse(base) for base in no.bases)
            linhas.append(f"class {no.name}({bases})")
        elif isinstance(no, ast.ImportFrom):
            for alias in no.names:
                nome = alias.asname or alias.name
                if not nome.startswith("_"):
                    linhas.append(f"{nome} = {no.module}.{alias.name}")
        elif isinstance(no, ast.Import):
            for alias in no.names:
                nome = alias.asname or alias.name.split(".")[0]
                if not nome.startswith("_"):
                    linhas.append(f"import {nome}")
    return linhas


def _api_py(raiz, pacote, filtro):
    try:
        especificacao = importlib.util.find_spec(pacote)
    except (ImportError, ValueError):
        return ""
    if especificacao is None or not especificacao.origin:
        return ""
    caminho = especificacao.origin
    if os.path.isdir(caminho):
        caminho = os.path.join(caminho, "__init__.py")
    if not os.path.isfile(caminho):
        return ""
    nomes = _assinaturas_py(_ler_fonte(caminho, 400000))
    if filtro:
        chave = filtro.lower()
        nomes = [linha for linha in nomes if chave in linha.lower()]
    try:
        relativo = os.path.relpath(caminho, raiz).replace(os.sep, "/")
    except ValueError:
        relativo = caminho
    if nomes:
        return f"{pacote} (python, instalado em {relativo})\n" + "\n".join(nomes)
    if filtro:
        trechos = _trechos_nos_caminhos(raiz, _fontes_do_pacote(caminho), filtro)
        if trechos:
            return (f"{pacote} (python, instalado em {relativo})\n"
                    f"(o termo nao esta nos nomes de topo; aparece no codigo do pacote)\n"
                    + "\n".join(trechos))
    sem_caso = f"(o modulo esta instalado; nenhum nome de topo contem '{filtro}')"
    sem_nomes = "(o modulo esta instalado mas nao declara nomes publicos de topo)"
    return f"{pacote} (python, instalado em {relativo})\n" + (sem_caso if filtro else sem_nomes)

@register(
    "tool_consultar_api_dependencia",
    'Devolve a API de uma dependencia JA INSTALADA, lida do codigo dela no disco - nao do conhecimento do modelo, que envelhece. Num pacote npm devolve o ficheiro de declaracoes (index.d.ts, ou o campo types) e, sem ele, o README; num modulo Python devolve as assinaturas publicas do topo, extraidas por AST. Use ANTES de escrever codigo contra uma biblioteca de terceiros e sempre que a duvida for "que opcoes, metodos ou propriedades isto tem?": e o caminho para parar de inventar nomes de parametros. Passe filtro quando o ficheiro for grande e quiser so as linhas com um termo (ex: workerFactory, fitToItems, Load). Se o termo NAO existir nas declaracoes, a ferramenta procura-o no codigo-fonte do proprio pacote e devolve ficheiro:linha com o trecho a volta - e o caminho para ver COMO uma funcao da biblioteca esta implementada (ex: _OnResize, FitView) sem andar a abrir node_modules a mao.',
    {
        'pacote': {"tipo": "STRING", "desc": 'Nome do pacote instalado, tal como se importa (ex: dxf-viewer, playwright, flask).', "padrao": ""},
        'filtro': {"tipo": "STRING", "desc": 'Trecho a procurar nas linhas da API (ex: workerFactory). Vazio devolve tudo ate a um teto de 8000 caracteres.', "padrao": ""},
    },
)
def tool_consultar_api_dependencia(pacote="", filtro=""):
    raiz = estado.get("pasta_raiz", "")
    if not pacote.strip():
        return "Diga o nome do pacote (ex: dxf-viewer)."
    nome = pacote.strip()
    emit_event("executing", function=f"Lendo a API de {nome}")
    if raiz and os.path.isdir(raiz):
        texto = _api_js(raiz, nome, filtro)
        if texto:
            return texto
    texto = _api_py(raiz or ".", nome, filtro)
    if texto:
        return texto
    return (f"'{nome}' nao foi encontrada: nem em node_modules/ do projeto aberto, nem entre os "
            f"modulos Python instalados. Confirme o nome publicado (o nome importado as vezes difere) "
            f"ou use tool_verificar_dependencias para ver o que esta instalado.")
