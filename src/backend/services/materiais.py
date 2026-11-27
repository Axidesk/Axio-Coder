"""Destino unico do material que o agente produz: gerados/<assunto>/.

A pasta e criada sozinha e o nome e limpo, para que "o que se gera" nunca caia na raiz
nem se misture com o codigo do produto - em qualquer projeto aberto, porque a raiz vem
do estado da sessao e nao de um caminho fixo.
"""

import os
import re
import unicodedata
from datetime import datetime

from src.backend.state import estado

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

PASTAS_DE_ATIVO = ("docs/repositorio", "src/", "scripts/", "data/")


def slug(texto, limite=48):
    """Nome de ficheiro seguro a partir de um titulo livre."""
    limpo = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    limpo = re.sub(r"[^A-Za-z0-9]+", "_", limpo).strip("_").lower()
    return (limpo or "sem_titulo")[:limite].strip("_") or "sem_titulo"


def raiz_do_projeto():
    return estado.get("pasta_raiz", "") or ""


def pasta_do_material(assunto):
    """Pasta relativa do assunto, criada dentro da raiz do projeto aberto."""
    nome = ASSUNTOS.get(str(assunto or "").strip().lower(), str(assunto or "").strip())
    relativa = f"{PASTA_DE_MATERIAL}/{slug(nome)}"
    raiz = raiz_do_projeto()
    if raiz:
        os.makedirs(os.path.join(raiz, PASTA_DE_MATERIAL, slug(nome)), exist_ok=True)
    return relativa


def destino_de_material(assunto, nome):
    """Caminho relativo gerados/<assunto>/<nome>, com a pasta ja criada quando ha projeto."""
    pasta = pasta_do_material(assunto)
    return f"{pasta}/{os.path.basename(str(nome or '').strip()) or 'material'}"


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
    if caminho.startswith(f"{PASTA_DE_MATERIAL}/") or caminho.startswith(PASTAS_DE_ATIVO):
        return ""
    sugestao = destino_de_material("documento", os.path.basename(caminho))
    return (f"\nDESTINO DO MATERIAL: '{caminho}' e material gerado e ficou fora de "
            f"{PASTA_DE_MATERIAL}/ - o proximo do mesmo tipo vai para {sugestao}.")
