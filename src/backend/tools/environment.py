import os
import sys

from src.backend.state import estado, emit_event
from src.backend.services.file_service import versao_pacote, venv_projeto, dirs_leitura_extra
from src.backend.services.process_manager import detectar_shell

def tool_info_ambiente():
    emit_event("executing", function="Coletando informações do ambiente")
    raiz = estado.get("pasta_raiz") or "(nenhuma)"
    shell = detectar_shell()
    linhas = [
        f"Pasta raiz: {raiz}",
        f"Shell do terminal (painel do Axio): {shell.get('nome')} -> {shell.get('cmd')}",
        "Shell das ferramentas (tool_executar_processo): cmd.exe via subprocess shell=True (allowlist por executavel)",
        f"Venv em uso (Axio): {sys.prefix}",
        f"Executável Python: {sys.executable}",
        f"Versão Python: {sys.version.split()[0]}",
        f"Versão Mempalace: {versao_pacote('mempalace')}",
        f"Versão ChromaDB: {versao_pacote('chromadb')}",
    ]
    venv_proj = venv_projeto()
    if venv_proj:
        linhas.append(f"Venv do projeto selecionado: {venv_proj['dir']} (python: {venv_proj['python']})")
    else:
        linhas.append("Venv do projeto selecionado: nenhum (crie com 'python -m venv .venv' se o projeto precisar de dependências próprias)")
    extras = dirs_leitura_extra()
    linhas.append("Diretórios de leitura permitidos (além da pasta raiz): " + (", ".join(extras) if extras else "(nenhum)"))
    palace = os.path.expanduser("~/.mempalace/palace")
    if os.path.isdir(palace):
        linhas.append(f"Palace do mempalace: {palace}")
        linhas.append(f"chroma.sqlite3 presente: {os.path.isfile(os.path.join(palace, 'chroma.sqlite3'))}")
        linhas.append("Dica: se buscas filtradas por wing falharem, rode 'mempalace repair' (issue #1035 do MemPalace).")
    else:
        linhas.append("Palace do mempalace: não encontrado.")
    return "\n".join(linhas)
