"""Varredura de ficheiros do projeto partilhada pelos modulos de dominio.

Extensoes de codigo, pastas a ignorar, listagem e contagem de linhas, a forma
comparavel de um nome de pacote e a cache JSON do painel de informacoes. Vive
aqui, e nao num dos modulos de dominio, porque os tres (indice de codigo, retrato
do projeto e dependencias) precisam da MESMA varredura: com uma copia em cada um,
a primeira regra que mudasse deixava as outras a divergir em silencio.
"""
import os
import json
import time

from src.backend.state import estado, caminho_estado_projeto

EXTENSOES_CODIGO = (
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".html", ".css", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".c",
    ".java", ".rs", ".go", ".rb", ".php", ".md",
    ".yaml", ".yml", ".toml", ".sh",
)
PALAVRAS_SENSIVEIS = (
    "credential", "secret", "password", "apikey", "api_key",
    "private_key", "access_key",
)
PASTAS_IGNORADAS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    "dist", "build", "vendor", ".axio", ".mempalace", "target", ".next",
    ".idea", ".vscode", "coverage", ".tox", ".nox", ".pytest_cache",
}
NOMES_MANIFESTO = {"requirements.txt", "package.json"}
EXTENSOES_PY = (".py",)
EXTENSOES_JS = (".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs")
MAX_ARQUIVOS_INDEX = 3000


def caminho_relativo(caminho):
    raiz = estado.get("pasta_raiz", "")
    if not raiz:
        return caminho
    return os.path.relpath(caminho, raiz).replace("\\", "/")

def arquivos_de_codigo(max_arquivos=MAX_ARQUIVOS_INDEX):
    raiz = estado.get("pasta_raiz", "")
    if not raiz or not os.path.isdir(raiz):
        return []
    arquivos = []
    for root, dirs, files in os.walk(raiz):
        dirs[:] = [d for d in dirs if d not in PASTAS_IGNORADAS and not d.startswith(".")]
        for name in files:
            nome = name.lower()
            if not nome.endswith(EXTENSOES_CODIGO):
                continue
            if any(p in nome for p in PALAVRAS_SENSIVEIS):
                continue
            caminho = os.path.join(root, name)
            try:
                if os.path.getsize(caminho) > 512000:
                    continue
            except OSError:
                continue
            arquivos.append(caminho)
            if len(arquivos) >= max_arquivos:
                return arquivos
    return arquivos

def eh_arquivo_de_codigo(nome):
    """Codigo do projeto + manifestos de dependencias (assets ficam fora)."""
    if nome in NOMES_MANIFESTO:
        return True
    return os.path.splitext(nome)[1].lower() in EXTENSOES_CODIGO

def contar_linhas(caminho):
    """Linhas de um ficheiro de texto (0 quando nao for legivel)."""
    try:
        with open(caminho, "r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0

def ler_cache_projeto(nome, chaves, versao=None):
    """Le um cache JSON do projeto; None se faltar o ficheiro ou vier incompleto.

    `chaves` sao as que tem de vir preenchidas para o cache servir: um ficheiro
    truncado, apanhado a meio de uma gravacao ou escrito por uma versao anterior
    nao pode passar por bom. `versao`, quando dada, exige que o cache tenha sido
    gravado por esta mesma versao da logica: a assinatura do projeto prova que os
    ficheiros nao mudaram, NAO que o retrato guardado foi medido como o codigo
    atual o mede - sem esta trava, um retrato antigo sobrevive ao reinicio e o
    painel continua a mostrar o desenho da versao anterior. Serve as duas medicoes
    lentas do painel (o retrato do projeto e os pacotes desatualizados), que
    guardam coisas diferentes no mesmo formato. Os caches poupam centenas de
    pedidos de rede e a leitura do projeto inteiro por dia.
    """
    caminho = caminho_estado_projeto(nome)
    if not caminho or not os.path.exists(caminho):
        return None
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(dados, dict) or any(not dados.get(k) for k in chaves):
        return None
    if versao is not None and dados.get("versao") != versao:
        return None
    return dados

def gravar_cache_projeto(nome, conteudo):
    """Grava um cache JSON do projeto, carimbado com o instante da medicao.

    Melhor esforco: um cache que nao se consegue gravar nao pode derrubar a
    medicao que ja foi feita e ja esta em memoria.
    """
    caminho = caminho_estado_projeto(nome)
    if not caminho:
        return
    try:
        os.makedirs(os.path.dirname(caminho), exist_ok=True)
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump({"ts": time.time(), **conteudo}, f)
    except OSError:
        pass

