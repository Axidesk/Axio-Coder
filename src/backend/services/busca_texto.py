import os
import re
from bisect import bisect_right

PASTAS_IGNORADAS = {
    '.git', 'node_modules', 'build', '__pycache__', '.vs', 'Intermediate',
    'Binaries', 'Saved', 'dist', '.next', 'venv', '.venv', '.axio', '.idea',
}

EXTS_BINARIAS = {
    '.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.ico', '.exe', '.dll',
    '.obj', '.lib', '.pdb', '.so', '.dylib', '.zip', '.pdf', '.pyc', '.woff',
    '.woff2', '.ttf', '.mp3', '.mp4', '.mov', '.svgz',
}

EXTS_TEXTO = {
    '.py', '.js', '.mjs', '.cjs', '.ts', '.tsx', '.jsx', '.html', '.htm',
    '.css', '.scss', '.less', '.json', '.md', '.cpp', '.cc', '.h', '.hpp',
    '.c', '.sh', '.bash', '.sql', '.yaml', '.yml', '.xml', '.java', '.cs',
    '.go', '.rs', '.php', '.rb', '.swift', '.kt', '.lua', '.r', '.txt',
    '.toml', '.ini', '.cfg', '.env', '.vue', '.svelte',
}

LIMITE_ARQUIVOS = 300
LIMITE_OCORRENCIAS = 100
LIMITE_TRECHO = 200

_RE_ESPACOS = re.compile(r"\s+")
_RE_NOVA_LINHA = re.compile(r"\n")


def _compactar(texto):
    return _RE_ESPACOS.sub("", texto)


def _mapa_sem_espacos(texto):
    return [i for i, ch in enumerate(texto) if not ch.isspace()]


def _recorte_de_linha(linha, destaque, limite):
    texto = linha.strip()
    if len(texto) <= limite:
        return texto
    pos = texto.find(destaque) if destaque else -1
    if pos < 0:
        return texto[:limite] + "…"
    inicio = max(0, pos - limite // 4)
    recorte = texto[inicio:inicio + limite]
    return ("…" if inicio > 0 else "") + recorte + ("…" if inicio + limite < len(texto) else "")


def busca_no_texto(texto, termo, limite=LIMITE_OCORRENCIAS):
    """Ocorrencias (linha, trecho, destaque) de um termo num texto e o total achado.

    A comparacao e feita sem espaco nenhum dos dois lados, por isso indentacao,
    tabs e quebras de linha (mesmo coladas sem separador) deixam de importar.
    """
    alvo = _compactar(str(termo or "")).lower()
    if not alvo or not texto:
        return [], 0
    compacto = _compactar(texto).lower()
    posicoes = []
    total = 0
    encontrado = compacto.find(alvo)
    while encontrado >= 0:
        if len(posicoes) < limite:
            posicoes.append(encontrado)
        total += 1
        encontrado = compacto.find(alvo, encontrado + 1)
    if not posicoes:
        return [], 0
    mapa = _mapa_sem_espacos(texto)
    inicios_de_linha = [0] + [m.end() for m in _RE_NOVA_LINHA.finditer(texto)]
    largura = len(alvo)
    ocorrencias = []
    for pos in posicoes:
        if pos + largura > len(mapa):
            continue
        inicio = mapa[pos]
        fim = mapa[pos + largura - 1] + 1
        destaque = texto[inicio:fim]
        numero_linha = bisect_right(inicios_de_linha, inicio)
        inicio_linha = inicios_de_linha[numero_linha - 1]
        fim_linha = texto.find("\n", inicio_linha)
        if fim_linha < 0:
            fim_linha = len(texto)
        linha_texto = texto[inicio_linha:fim_linha]
        if "\n" not in destaque and destaque in linha_texto:
            trecho = _recorte_de_linha(linha_texto, destaque, LIMITE_TRECHO)
            destaque = destaque if destaque in trecho else None
        else:
            trecho = " ".join(destaque.split())
            if len(trecho) > LIMITE_TRECHO:
                trecho = trecho[:LIMITE_TRECHO] + "…"
            destaque = trecho
        ocorrencias.append({"linha": numero_linha, "trecho": trecho, "destaque": destaque})
    return ocorrencias, total


def buscar_no_projeto(raiz, termo, limite_arquivos=LIMITE_ARQUIVOS):
    """Varre a arvore a partir de 'raiz' e devolve os ficheiros com ocorrencias do termo."""
    termo = str(termo or "").strip()
    resultados = []
    if not raiz or not termo or not os.path.isdir(raiz):
        return resultados
    for dirpath, dirnames, filenames in os.walk(raiz):
        dirnames[:] = [d for d in dirnames if d not in PASTAS_IGNORADAS and not d.startswith(".")]
        for nome in filenames:
            if nome.startswith("."):
                continue
            ext = os.path.splitext(nome)[1].lower()
            if ext in EXTS_BINARIAS:
                continue
            if ext and ext not in EXTS_TEXTO:
                continue
            caminho = os.path.join(dirpath, nome)
            try:
                with open(caminho, "r", encoding="utf-8", errors="ignore") as f:
                    texto = f.read()
            except Exception:
                continue
            ocorrencias, total = busca_no_texto(texto, termo)
            if total:
                resultados.append({
                    "arquivo": os.path.relpath(caminho, raiz).replace("\\", "/"),
                    "total": total,
                    "ocorrencias": ocorrencias,
                })
            if len(resultados) >= limite_arquivos:
                return resultados
    return resultados
