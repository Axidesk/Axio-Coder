import os
import json

from src.backend.config import APP_ROOT, caminho_data
from src.backend.services.persistencia import gravar_json_atomico
from src.backend.state import estado

def _glossary_path():
    return caminho_data("glossary.json")

def load_glossary():
    caminho = _glossary_path()
    if not os.path.exists(caminho):
        return {"termos": []}
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)
        if not isinstance(dados, dict) or "termos" not in dados:
            return {"termos": []}
        return dados
    except Exception:
        return {"termos": []}

def save_glossary(dados):
    """Grava o glossario de forma ATOMICA.

    A auto-curacao escreve este ficheiro em segundo plano enquanto o Flask o le
    a cada rodada; sem a troca atomica um load_glossary podia apanhar o ficheiro
    a meio e devolver o glossario vazio naquela rodada. A escrita em si vive em
    gravar_json_atomico, partilhada com o log de sessao e o radar de atrito.
    """
    return gravar_json_atomico(_glossary_path(), dados)

def normalizar(texto):
    if texto is None:
        return ""
    return str(texto).strip().lower()

def normalizar_lista(aliases):
    if aliases is None:
        return []
    if isinstance(aliases, str):
        raw = [a for a in aliases.split(",") if a.strip()]
    elif isinstance(aliases, (list, tuple)):
        raw = [str(a) for a in aliases]
    else:
        return []
    vistos = []
    for a in raw:
        a = a.strip()
        if a and a.lower() not in vistos:
            vistos.append(a.lower())
    return vistos

def identificador_concreto(identificador):
    if not identificador or not str(identificador).strip():
        return False
    ident = str(identificador).strip()
    vagos = ("coisa", "jeito", "aquilo", "isso", "algum", "algo", "elemento", "item", "botao", "janela")
    if ident.lower() in vagos:
        return False
    return True

def caminho_do_arquivo(arquivo):
    """Caminho absoluto de um arquivo citado pelo glossario.

    Mede primeiro contra a pasta do projeto aberto (termos do projeto do usuario)
    e, se ai nao existir, contra a raiz do Axio: o glossario e GLOBAL
    (data/glossary.json) e a maioria dos alvos sao ficheiros do proprio Axio. Sem
    a segunda base, abrir qualquer outro projeto fazia `verificar_glossario`
    marcar as ~46 entradas como "ausente" e encher o bloco de pendencias de ruido
    em todas as rodadas, apagando a linha conferida de cada termo.
    """
    if not arquivo:
        return ""
    if os.path.isabs(arquivo):
        return arquivo
    for base in (estado.get("pasta_raiz") or "", APP_ROOT):
        if not base:
            continue
        caminho = os.path.join(base, arquivo)
        if os.path.exists(caminho):
            return caminho
    return ""

def _alvo_do_identificador(identificador):
    """Reduz um identificador composto ao token que realmente existe no codigo.

    No glossario, alguns identificadores sao descritivos e nao um nome puro:
    'doPurgeTrash / setLimpezaLixeira', 'corDeFundoTerminal (theme.cursor)',
    '#term-log .xterm-scrollable-element > .slider'. Procurar a string inteira
    nunca casaria nada; aqui fica so o primeiro token utilizavel.
    """
    texto = (identificador or "").strip()
    for corte in (" > ", " / ", " (", "[", "{"):
        texto = texto.split(corte)[0].strip()
    if texto.startswith(("#", ".")) and " " in texto:
        texto = texto.split(" ")[0].strip()
    return texto

def _variantes_do_identificador(identificador):
    """Do identificador mais especifico para o mais generico.

    Um seletor composto ('#term-log .xterm > .scrollbar > .slider') tem de ser
    procurado primeiro INTEIRO: reduzido logo ao primeiro token, a linha medida e
    a do ancestral (a primeira linha onde '#term-log' aparece) e o glossario
    passa a apontar para o sitio errado sem que ninguem note. Um identificador com
    partes ('A / B') mede tambem a segunda, mas SO depois do alvo: a primeira parte
    e quem manda na linha, e inverter esta ordem muda a linha de tudo o que ja esta
    gravado.
    """
    texto = " ".join((identificador or "").split())
    variantes = [texto] if texto else []
    while variantes and " > " in variantes[-1]:
        variantes.append(variantes[-1].rsplit(" > ", 1)[0].strip())
    alvo = _alvo_do_identificador(identificador)
    if alvo and alvo not in variantes:
        variantes.append(alvo)
    for parte in texto.split(" / ")[1:]:
        parte = parte.strip()
        if parte and parte not in variantes:
            variantes.append(parte)
    return variantes

def _padroes_do_identificador(ident):
    """Padroes que DEFINEM o identificador, nao os que apenas o mencionam.

    A distincao e o que decide entre "a casa do simbolo" e "um sitio onde ele
    aparece": `id="term-log"` cria o elemento, `#term-log` num CSS so o estiliza.
    """
    if ident.startswith("#"):
        return (f'id="{ident[1:]}"', f"id='{ident[1:]}'", ident)
    if ident.startswith("."):
        return (ident[1:],)
    return (f"def {ident}(", f"function {ident}(", f"class {ident}",
            f"{ident} = function", f"{ident}: function", f"{ident} = (",
            f"{ident} =", f"{ident}:")


def _linha_da_variante(linhas, ident):
    """Numero da primeira linha que casa com um identificador simples."""
    exatos = _padroes_do_identificador(ident)
    for numero, linha in enumerate(linhas, start=1):
        if any(padrao in linha for padrao in exatos):
            return numero
    if ident.startswith(("#", ".")):
        return None
    for numero, linha in enumerate(linhas, start=1):
        if ident in linha:
            return numero
    return None


def _linha_de_definicao(linhas, ident):
    """Linha onde o identificador e DEFINIDO; sem a queda para a simples mencao."""
    padroes = _padroes_do_identificador(ident)
    for numero, linha in enumerate(linhas, start=1):
        if any(padrao in linha for padrao in padroes):
            return numero
    return None

def achar_linha_identificador(arquivo, identificador):
    """Mede no ficheiro a linha onde o identificador vive; None se nao achar.

    E o que impede o glossario de apodrecer: sem esta medicao, o campo 'linha'
    e so um numero escrito de memoria que fica errado em silencio quando o
    arquivo e reescrito (foi o que aconteceu ao index.html, que passou de ~1300
    para ~600 linhas e deixou ~20 entradas a apontar para o vazio).
    """
    caminho = caminho_do_arquivo(arquivo)
    if not caminho or not os.path.isfile(caminho):
        return None
    try:
        with open(caminho, "r", encoding="utf-8", errors="replace") as f:
            linhas = f.readlines()
    except OSError:
        return None
    for variante in _variantes_do_identificador(identificador):
        numero = _linha_da_variante(linhas, variante)
        if numero:
            return numero
    return None


EXTENSOES_DE_ALVO = (".py", ".js", ".mjs", ".cjs", ".html", ".css")
PASTAS_IGNORADAS_ALVO = {
    ".venv", "venv", "__pycache__", ".git", "node_modules", "build", "dist",
    ".vs", "site-packages", ".trash", "gerados",
}
LIMITE_FICHEIROS_ALVO = 1500
LIMITE_BYTES_ALVO = 512 * 1024
MAX_CANDIDATOS_ALVO = 6


def _caminhos_para_alvo():
    """(arquivo relativo, caminho absoluto) dos ficheiros onde um alvo pode viver.

    Duas bases, pela mesma razao de `caminho_do_arquivo`: o glossario e global
    (data/glossary.json) e a maioria dos alvos sao ficheiros do proprio Axio, que
    nao estao dentro da pasta de outro projeto.
    """
    bases = []
    for base in (estado.get("pasta_raiz") or "", APP_ROOT):
        if base and os.path.isdir(base) and base not in bases:
            bases.append(base)
    saida = []
    vistos = set()
    for base in bases:
        for raiz, pastas, ficheiros in os.walk(base):
            pastas[:] = [p for p in pastas if p not in PASTAS_IGNORADAS_ALVO and not p.startswith(".")]
            for nome in ficheiros:
                if not nome.endswith(EXTENSOES_DE_ALVO):
                    continue
                caminho = os.path.join(raiz, nome)
                try:
                    if os.path.getsize(caminho) > LIMITE_BYTES_ALVO:
                        continue
                except OSError:
                    continue
                real = os.path.realpath(caminho)
                if real in vistos:
                    continue
                vistos.add(real)
                saida.append((os.path.relpath(caminho, base).replace(os.sep, "/"), caminho))
                if len(saida) >= LIMITE_FICHEIROS_ALVO:
                    return saida
    return saida


def localizar_alvos(identificadores, fontes=None):
    """{identificador: [(arquivo, linha), ...]} onde cada um esta DEFINIDO.

    Uma varredura para todos: o custo esta em ler os ficheiros, nao em comparar
    linhas, por isso procurar dez identificadores numa passada custa o mesmo que
    procurar um. Devolve ate MAX_CANDIDATOS_ALVO por identificador - quem chama
    decide se o alvo e unico (e entao o movimento e facto medido) ou ambiguo (e
    entao e uma proposta).
    """
    variantes = {}
    for ident in identificadores or []:
        bruto = (ident or "").strip()
        if bruto and bruto not in variantes:
            variantes[bruto] = _variantes_do_identificador(bruto)
    if not variantes:
        return {}
    if fontes is None:
        fontes = _caminhos_para_alvo()
    achados = {ident: [] for ident in variantes}
    for relativo, caminho in fontes:
        if all(len(v) >= MAX_CANDIDATOS_ALVO for v in achados.values()):
            break
        try:
            with open(caminho, "r", encoding="utf-8", errors="replace") as f:
                linhas = f.readlines()
        except OSError:
            continue
        for ident, lista in variantes.items():
            if len(achados[ident]) >= MAX_CANDIDATOS_ALVO:
                continue
            for variante in lista:
                numero = _linha_de_definicao(linhas, variante)
                if numero:
                    achados[ident].append((relativo, numero))
                    break
    return {ident: locais for ident, locais in achados.items() if locais}

