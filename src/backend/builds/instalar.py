"""Instalar, sozinho, o que falta para o projeto compilar.

Os ids dos componentes NAO sao escritos de memoria: saem do proprio instalador da Qt, que
responde em XML ao 'list' (o que esta instalado) e ao 'search --type package' (o que existe
para instalar). Um id que o instalador nao liste nunca e usado - e por isso que um modulo
sem componente instalavel e reportado como tal, em vez de se inventar um nome.
https://doc.qt.io/qt-6/get-and-install-qt-cli.html
"""

import os
import subprocess
import xml.etree.ElementTree as ET

TIMEOUT_LISTAR = 240
TIMEOUT_PROCURAR = 900
TIMEOUT_INSTALAR = 3600

FLAGS_DE_ACORDO = ("--accept-licenses", "--default-answer", "--confirm-command")

_SUFIXOS_DE_MODULO = ("widgets", "quick", "core", "gui", "plugin", "extras")

_FALHAS = (
    ("Component(s) not found", "o instalador nao consegue selecionar este componente"),
    ("archive of historical versions", "esta versao da Qt so existe no arquivo historico"),
    ("No components available with the current selection",
     "nao ha nenhum componente disponivel para esta selecao"),
    ("There is an important update available",
     "o proprio instalador pede que se atualize primeiro"),
)

_cache = {}


def instalados(instalador):
    """Componentes ja instalados, pelo id que o instalador usa."""
    return _pacotes(instalador, ("list",), TIMEOUT_LISTAR)


def disponiveis(instalador):
    """Componentes que o instalador sabe instalar (lidos do catalogo que a Qt mantem em cache)."""
    return _pacotes(instalador, ("search", "--type", "package"), TIMEOUT_PROCURAR)


def codigo_da_versao(versao):
    """Codigo que a Qt usa nos ids dos componentes: 6.10.0 -> '6100', 6.8.2 -> '682' (medido)."""
    return "".join(p for p in (versao or "").split(".")[:3] if p.isdigit())


def componentes_para(instalador, versao, modulos):
    """Componentes que trazem estes modulos, cada um confirmado no catalogo do instalador."""
    if not modulos:
        return {"ids": [], "nomes": [], "sem_componente": []}
    catalogo = disponiveis(instalador)
    if not catalogo:
        return {"ids": [], "nomes": [], "sem_componente": list(modulos)}
    codigo = codigo_da_versao(versao)
    ja_tem = instalados(instalador)
    ids = []
    nomes = []
    sem_componente = []
    for modulo in modulos:
        achado = _componente_do_modulo(catalogo, codigo, modulo)
        if not achado:
            sem_componente.append(modulo)
            continue
        if achado in ja_tem or achado in ids:
            continue
        ids.append(achado)
        nomes.append(catalogo[achado] or achado)
    return {"ids": ids, "nomes": nomes, "sem_componente": sem_componente}


def comando_instalar(instalador, ids):
    """Comando que instala os componentes sem uma unica janela."""
    return " ".join([f'"{instalador}"', *FLAGS_DE_ACORDO, "install", *ids])


def explicar(saida):
    """Traduz o que o instalador escreveu numa razao legivel - sem inventar causa nenhuma.

    Medido nesta maquina (2026-10-06): o 'search' lista componentes que o 'install' depois recusa,
    logo a lista de disponiveis NAO prova que se instala. Quem decide e o proprio instalador.
    """
    texto = saida or ""
    razoes = list(dict.fromkeys(frase for marca, frase in _FALHAS if marca in texto))
    if not razoes:
        return []
    return ["PORQUE NAO DEU (palavras do proprio instalador):"] + [f"  - {r}" for r in razoes]


def _componente_do_modulo(catalogo, codigo, modulo):
    for candidato in _candidatos(codigo, modulo):
        if candidato in catalogo:
            return candidato
    return _por_semelhanca(catalogo, codigo, modulo)


def _candidatos(codigo, modulo):
    baixo = (modulo or "").lower()
    if not baixo or not codigo:
        return []
    candidatos = [f"qt.qt6.{codigo}.addons.qt{baixo}"]
    for sufixo in _SUFIXOS_DE_MODULO:
        if baixo.endswith(sufixo) and len(baixo) > len(sufixo):
            candidatos.append(f"qt.qt6.{codigo}.addons.qt{baixo[:-len(sufixo)]}")
    return candidatos


def _por_semelhanca(catalogo, codigo, modulo):
    """Ultimo recurso: um id do proprio catalogo cujo nome acaba no nome do modulo."""
    alvo = ".qt" + (modulo or "").lower()
    candidatos = sorted(
        chave for chave in catalogo
        if codigo in chave and (chave.endswith(alvo) or f"{alvo}." in chave)
    )
    return candidatos[0] if candidatos else ""


def _pacotes(instalador, argumentos, timeout):
    chave = (os.path.abspath(instalador), argumentos)
    if chave in _cache:
        return _cache[chave]
    pacotes = _ler_xml(_saida(instalador, argumentos, timeout))
    if pacotes:
        _cache[chave] = pacotes
    return pacotes


def _saida(instalador, argumentos, timeout):
    try:
        resultado = subprocess.run(
            [instalador, *argumentos], capture_output=True, text=True, timeout=timeout, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return (resultado.stdout or "") + (resultado.stderr or "")


def _ler_xml(texto):
    """Le o XML que o instalador escreve, saltando as linhas de log que o precedem."""
    inicio = (texto or "").find("<?xml")
    if inicio < 0:
        return {}
    try:
        raiz = ET.fromstring(texto[inicio:])
    except ET.ParseError:
        return {}
    return {
        p.get("name"): p.get("displayname") or ""
        for p in raiz.iter("package")
        if p.get("name")
    }
