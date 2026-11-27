"""Destino unico do material que o agente produz: gerados/<assunto>/.

A pasta e criada sozinha e o nome e limpo, para que "o que se gera" nunca caia na raiz
nem se misture com o codigo do produto - em qualquer projeto aberto, porque a raiz vem
do estado da sessao e nao de um caminho fixo.
"""

import os
import re
import unicodedata
from datetime import datetime

from src.backend.config import APP_ROOT
from src.backend.services.file_service import caminho_contido
from src.backend.state import estado, no_diretorio_do_axio

PASTA_DE_MATERIAL = "gerados"

ASSUNTOS = {
    "plano": "planos",
    "documento": "documentos",
    "planilha": "planilhas",
    "apresentacao": "apresentacoes",
    "imagem": "imagens",
    "modelo": "modelos",
    "desenho": "desenhos",
    "relatorio": "relatorios",
    "captura": "capturas",
    "gravacao": "gravacoes",
}

EXTENSOES_DE_MATERIAL = {
    ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".csv", ".odt", ".ods",
    ".ifc", ".dxf", ".dwg", ".stl", ".obj", ".glb", ".gltf", ".ply", ".3mf", ".step", ".stp",
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg",
    ".zip", ".7z", ".tar", ".gz", ".mp4", ".mp3", ".wav", ".wmv",
}

PASTAS_DE_ATIVO = ("data/repositorio", "src/", "scripts/", "data/")


def slug(texto, limite=48):
    """Nome de ficheiro seguro a partir de um titulo livre."""
    limpo = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    limpo = re.sub(r"[^A-Za-z0-9]+", "_", limpo).strip("_").lower()
    return (limpo or "sem_titulo")[:limite].strip("_") or "sem_titulo"


def raiz_do_projeto():
    return estado.get("pasta_raiz", "") or ""


def raiz_do_gerados():
    """O gerados/ do Axio, em ABSOLUTO: casa de todo o material, em qualquer projeto.

    E o unico caminho fixo desta materia. Nao depende do projeto aberto nem do
    nome dele, e por isso continua a ser alcançavel de fora do Axio.
    """
    return os.path.join(APP_ROOT, PASTA_DE_MATERIAL)


def raiz_do_material():
    """Pasta ABSOLUTA onde nasce o material DA VEZ: gerados/<projeto>/.

    Dentro do Axio e o gerados/ da raiz. Com OUTRO projeto aberto e
    gerados/<projeto>/ do Axio: a pasta do projeto fica limpa, sem um gerados/
    dentro dela, e o material continua ao alcance porque o caminho e absoluto.
    """
    if no_diretorio_do_axio() or not raiz_do_projeto():
        return raiz_do_gerados()
    nome = os.path.basename(os.path.normpath(raiz_do_projeto())) or "projeto"
    return os.path.join(raiz_do_gerados(), slug(nome))


def pasta_do_material(assunto):
    """Pasta ABSOLUTA do assunto, criada se faltar."""
    nome = ASSUNTOS.get(str(assunto or "").strip().lower(), str(assunto or "").strip())
    absoluta = os.path.join(raiz_do_material(), slug(nome))
    os.makedirs(absoluta, exist_ok=True)
    return absoluta


def destino_de_material(assunto, nome):
    """Caminho ABSOLUTO gerados/<assunto>/<nome>, com a pasta ja criada."""
    pasta = pasta_do_material(assunto)
    return os.path.join(pasta, os.path.basename(str(nome or "").strip()) or "material")


def rotulo_de_material(caminho):
    """Forma curta para mostrar: relativa ao Axio quando o material vive la."""
    absoluto = os.path.abspath(str(caminho or ""))
    try:
        return os.path.relpath(absoluto, APP_ROOT).replace("\\", "/")
    except ValueError:
        return absoluto


def carimbo(agora=None):
    return (agora or datetime.now()).strftime("%Y-%m-%d_%H%M")


def destino_datado(assunto, rotulo, extensao="md"):
    """gerados/<assunto>/<data>_<hora>_<rotulo>.<ext> - dois do mesmo dia nao se sobrepoem."""
    return destino_de_material(assunto, f"{carimbo()}_{slug(rotulo)}.{extensao.lstrip('.')}")


def _normalizar(caminho):
    return str(caminho or "").replace("\\", "/").strip().lstrip("./")


def eh_material(caminho):
    return os.path.splitext(_normalizar(caminho))[1].lower() in EXTENSOES_DE_MATERIAL


def aviso_de_destino(caminho_relativo):
    """Aviso (vazio quando esta tudo certo) para material de saida gravado fora de gerados/."""
    caminho = _normalizar(caminho_relativo)
    if not caminho or not eh_material(caminho):
        return ""
    raiz = raiz_do_projeto()
    absoluto = caminho if os.path.isabs(caminho) else os.path.join(raiz, caminho)
    if caminho_contido(absoluto, raiz_do_gerados()):
        return ""
    try:
        relativo = os.path.relpath(os.path.abspath(absoluto), os.path.abspath(raiz)).replace("\\", "/")
    except ValueError:
        relativo = caminho
    if relativo.startswith(PASTAS_DE_ATIVO):
        return ""
    sugestao = rotulo_de_material(destino_de_material("documento", os.path.basename(caminho)))
    return (f"\nDESTINO DO MATERIAL: '{caminho}' e material gerado e ficou fora de "
            f"{PASTA_DE_MATERIAL}/ - o proximo do mesmo tipo vai para {sugestao}.")
