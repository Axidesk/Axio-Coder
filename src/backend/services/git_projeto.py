"""Repositorio da pasta do projeto: cada projeto no seu, nunca no repositorio de outro."""

import os

from src.backend.config import APP_ROOT
from src.backend.services.file_service import git_saida, raiz_repositorio

_LINHAS_DO_GITIGNORE = (
    ".env",
    ".env.*",
    "!.env.example",
    ".axio/",
    ".venv/",
    "venv/",
    "__pycache__/",
    "*.pyc",
    "node_modules/",
    "dist/",
    "build/",
)


def criar_repositorio(caminho):
    """Cria o repositorio DENTRO desta pasta. Devolve raiz, se criou, se escreveu o gitignore e o erro."""
    alvo = os.path.abspath(caminho or "")
    if not os.path.isdir(alvo):
        return {"raiz": "", "criado": False, "gitignore": False, "erro": f"'{caminho}' nao e uma pasta."}
    existente = raiz_repositorio(alvo)
    if existente and _mesma_pasta(existente, alvo):
        return {"raiz": existente, "criado": False, "gitignore": False, "erro": ""}
    _, erro = git_saida(alvo, "init")
    if erro:
        return {"raiz": "", "criado": False, "gitignore": False, "erro": erro}
    git_saida(alvo, "symbolic-ref", "HEAD", "refs/heads/main")
    return {"raiz": alvo, "criado": True, "gitignore": _escrever_gitignore(alvo), "erro": ""}


def _escrever_gitignore(raiz):
    caminho = os.path.join(raiz, ".gitignore")
    if os.path.exists(caminho):
        return False
    try:
        with open(caminho, "w", encoding="utf-8") as f:
            f.write("\n".join(_LINHAS_DO_GITIGNORE) + "\n")
    except OSError:
        return False
    return True


def preparar_ao_abrir(pasta):
    """Devolve as linhas do que foi preciso fazer para o commit deste projeto ter onde acontecer."""
    alvo = os.path.abspath(pasta or "")
    if not os.path.isdir(alvo) or _dentro_do_axio(alvo):
        return []
    raiz = raiz_repositorio(alvo)
    linhas = []
    if raiz and not _mesma_pasta(raiz, alvo):
        resultado = criar_repositorio(alvo)
        if resultado["erro"] or not _mesma_pasta(resultado["raiz"], alvo):
            return [f"AVISO: esta pasta vive dentro do repositorio '{raiz}' e nao consegui criar um proprio aqui: "
                    f"{resultado['erro'] or 'o git nao criou o repositorio nesta pasta'}"]
        linhas.append(f"REPOSITORIO DA PASTA: '{alvo}' vivia dentro do repositorio '{raiz}' - criei um repositorio "
                      "proprio aqui, para o trabalho deste projeto nao se misturar com o de outro.")
        raiz = resultado["raiz"]
    if raiz and not _identidade_configurada(raiz):
        linhas.append("AVISO: o git nao sabe quem esta a commitar (user.name/user.email) - sem isso o primeiro "
                      "commit falha; configure-os no git.")
    return linhas


def _mesma_pasta(a, b):
    return os.path.normcase(os.path.normpath(os.path.abspath(a))) == os.path.normcase(os.path.normpath(os.path.abspath(b)))


def _dentro_do_axio(pasta):
    raiz = os.path.normcase(os.path.normpath(os.path.abspath(APP_ROOT)))
    alvo = os.path.normcase(os.path.normpath(os.path.abspath(pasta)))
    return alvo == raiz or alvo.startswith(raiz + os.sep)


def _identidade_configurada(raiz):
    nome, _ = git_saida(raiz, "config", "user.name")
    email, _ = git_saida(raiz, "config", "user.email")
    return bool((nome or "").strip() and (email or "").strip())
