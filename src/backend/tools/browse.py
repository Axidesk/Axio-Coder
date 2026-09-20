"""Navegacao e estrutura do projeto: listar pasta, listar arvore e pesquisar texto.

Verbatim de tools/filesystem.py; importa-lo e o que regista as suas 3 tools e
a pasta mostrada ao modelo passa a ser a que este modulo devolve.
"""
import os
import time

from src.backend.state import estado, emit_event
from src.backend.tools.registry import register
from src.backend.services.file_service import resolver_caminho, entradas_diretorio, resumo_entradas, normalizar_unicode, buscar_em_revisao, PASTAS_FORA_DA_BUSCA, EXT_FORA_DA_BUSCA

LIMITE_BYTES_LIDOS = 8 * 1024 * 1024


def _formato_tamanho(num):
    try:
        n = float(num)
    except (TypeError, ValueError):
        return "-"
    if n < 1024:
        return f"{n:.0f} B"
    for unidade in ("KB", "MB", "GB", "TB"):
        n /= 1024
        if n < 1024:
            return f"{n:.1f} {unidade}"
    return f"{n:.1f} PB"


@register(
    "tool_listar_pasta",
    "Lista o conteúdo de uma pasta. Use sem argumentos para a raiz ou passe 'caminho_relativo' para explorar subpastas.",
    {
        'caminho_relativo': {"tipo": "STRING", "desc": 'Subpasta opcional', "padrao": ""},
    },
)
def tool_listar_pasta(caminho_relativo=""):
    emit_event("executing", function=f"Listando: {caminho_relativo or 'Raiz'}")
    
    caminho_alvo, erro_caminho = resolver_caminho(caminho_relativo, permitir_extra=True)
    if erro_caminho:
        return erro_caminho
    
    if not os.path.exists(caminho_alvo):
        return f"ERRO: O caminho '{caminho_relativo}' não existe."

    try:
        entradas, ocultos = resumo_entradas(caminho_alvo)
        entradas.sort(key=lambda e: (e["tipo"] != "dir", e["nome"].lower()))
        resumo = f"{len(entradas)} itens"
        if ocultos:
            resumo += f" (+{ocultos} oculto(s): pastas de build/sistema e binarios ficam fora da listagem)"
        linhas = [f"Caminho: {caminho_relativo or os.path.basename(caminho_alvo.rstrip(os.sep)) or caminho_alvo}",
                  resumo]
        for e in entradas:
            nome = e["nome"] + "/" if e["tipo"] == "dir" else e["nome"]
            try:
                st = os.stat(os.path.join(caminho_alvo, e["nome"]))
                tam = _formato_tamanho(st.st_size)
                data = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime))
            except OSError:
                tam, data = "-", "-"
            linhas.append(f"{data}  {tam:>10}  {nome}")
        if len(linhas) > 2:
            return "\n".join(linhas)
        if ocultos:
            return f"{linhas[0]}\nNenhum item visivel ({ocultos} oculto(s): pastas de build/sistema e binarios)."
        return "Pasta vazia."
    except Exception as e:
        return f"ERRO ao acessar pasta: {str(e)}"


@register(
    "tool_listar_arvore",
    "Mapeia recursivamente a árvore/estrutura de pastas e arquivos do projeto em formato de árvore (com ramos e indentação), já ignorando pastas inúteis (node_modules, .git, __pycache__, binários etc.). USE ESTA ferramenta (não tool_listar_pasta) quando precisar descobrir a estrutura geral do projeto ou localizar onde um arquivo/pasta está, sem navegar pasta a pasta. Pastas muito grandes são truncadas com aviso explícito '( +N itens ocultos)'. Binários e pastas de build ficam fora da árvore por desenho: para auditar um diretório exato (e saber quantos itens foram ocultados) use tool_listar_pasta.",
    {
        'caminho_relativo': {"tipo": "STRING", "desc": 'Pasta inicial (padrão: raiz do projeto)', "padrao": ""},
        'profundidade_max': {"tipo": "INTEGER", "desc": 'Profundidade máxima (padrão 4)', "padrao": 4},
        'max_entradas': {"tipo": "INTEGER", "desc": 'Teto de entradas exibidas no total (padrão 400)', "padrao": 400},
    },
)
def tool_listar_arvore(caminho_relativo="", profundidade_max=4, max_entradas=400):
    emit_event("executing", function=f"Mapeando árvore: {caminho_relativo or 'Raiz'}")
    caminho_alvo, erro_caminho = resolver_caminho(caminho_relativo, permitir_extra=True)
    if erro_caminho:
        return erro_caminho
    if not os.path.isdir(caminho_alvo):
        return f"ERRO: O caminho '{caminho_relativo}' não é uma pasta."

    contador = {"n": 0}
    linhas = []
    limite_por_dir = 60

    def _arvore(pasta, prefixo, profundidade):
        if profundidade > profundidade_max:
            linhas.append(prefixo + "(...)")
            return False
        entradas = entradas_diretorio(pasta)
        entradas.sort(key=lambda e: (e["tipo"] != "dir", e["nome"].lower()))
        total = len(entradas)
        exibir = entradas[:limite_por_dir]
        for idx, e in enumerate(exibir):
            contador["n"] += 1
            if contador["n"] > max_entradas:
                linhas.append(prefixo + "... (limite de entradas atingido)")
                return True
            eh_ultimo = (idx == len(exibir) - 1) and (total <= limite_por_dir)
            ramo = "└── " if eh_ultimo else "├── "
            if e["tipo"] == "dir":
                linhas.append(prefixo + ramo + e["nome"] + "/")
                if _arvore(os.path.join(pasta, e["nome"]), prefixo + ("    " if eh_ultimo else "│   "), profundidade + 1):
                    return True
            else:
                linhas.append(prefixo + ramo + e["nome"])
        if total > limite_por_dir:
            linhas.append(prefixo + f"... (+{total - limite_por_dir} itens ocultos nesta pasta)")
        return False

    try:
        _arvore(caminho_alvo, "", 1)
        cabecalho = caminho_relativo if caminho_relativo else os.path.basename(caminho_alvo.rstrip(os.sep))
        resultado = cabecalho + "/\n" + "\n".join(linhas) if linhas else cabecalho + "/\n(pasta vazia)"
        return resultado
    except Exception as e:
        return f"ERRO ao mapear árvore: {str(e)}"


@register(
    "tool_pesquisar_no_projeto",
    'Busca ocorrências de string no código (compara com normalização Unicode NFC — acentos compostos e decompostos casam automaticamente). PROIBIDO pesquisar termos de leigo passados pelo humano (Ex: porta, alisar, camera, parede etc). Se o usuário citar, primeiro mapeie o código ou leia as assinaturas para descobrir o nome correto e evitar perder tempo. Passa o parametro revisao (ex: HEAD) para procurar na versao do git em vez do disco. Ignora por predefinicao node_modules, .venv, .git e pastas afins: ligue incluir_ignoradas para procurar tambem la dentro (tipagens e codigo das dependencias instaladas).',
    {
        'termo': {"tipo": "STRING", "obrig": True, "padrao": ""},
        'revisao': {"tipo": "STRING", "padrao": ""},
        'incluir_ignoradas': {"tipo": "BOOLEAN", "obrig": False, "padrao": False, "desc": "Procura tambem dentro das pastas ignoradas por predefinicao (node_modules, .venv, .git, build, dist). Serve para ler tipagens e codigo das dependencias instaladas. Custa tempo - em pastas enormes o limite de 10s corta a busca."},
        'pasta': {"tipo": "STRING", "padrao": "", "desc": "Limita a busca a uma pasta do projeto (ex: node_modules/dxf-viewer). E o caminho para procurar dentro de uma dependencia SEM percorrer as outras todas: sem isto, incluir_ignoradas varre o node_modules inteiro e o limite de 10s devolve resultados parciais (os ficheiros ordenados depois do corte nunca sao vistos)."},
    },
)
def tool_pesquisar_no_projeto(termo: str, revisao: str = "", incluir_ignoradas: bool = False, pasta: str = ""):
    emit_event("executing", function=f"Pesquisando: {termo}")
    if revisao:
        resultados, erro = buscar_em_revisao(termo, revisao, estado["pasta_raiz"])
        if erro:
            return erro
        if not resultados:
            return f"Nenhuma ocorrência encontrada para o termo '{termo}' na revisao {revisao}."
        saida = "\\n".join(resultados)
        return saida[:10000] + "\\n... [RESULTADO TRUNCADO]" if len(saida) > 10000 else saida
    termo_norm = normalizar_unicode(termo)
    resultados = []
    tempo_inicio = time.time()
    pastas_ignoradas = PASTAS_FORA_DA_BUSCA
    extensoes_ignoradas = EXT_FORA_DA_BUSCA

    raiz_projeto = estado["pasta_raiz"]
    raiz_busca = raiz_projeto
    if pasta and pasta.strip():
        candidata = os.path.abspath(os.path.join(raiz_projeto, pasta.strip().strip("/\\")))
        if not candidata.startswith(os.path.abspath(raiz_projeto)):
            return f"ERRO: '{pasta}' esta fora do projeto."
        if not os.path.isdir(candidata):
            return f"ERRO: '{pasta}' nao e uma pasta do projeto."
        raiz_busca = candidata

    ignorados_por_tamanho = 0

    for root, dirs, files in os.walk(raiz_busca):
        if not incluir_ignoradas:
            dirs[:] = [d for d in dirs if d not in pastas_ignoradas and not d.startswith('.')]

        
        for name in files:
            if time.time() - tempo_inicio > 10:
                resultados.append("[AVISO] Timeout de 10s atingido. Resultados parciais.")
                saida = "\\n".join(resultados)
                return saida[:10000] + "\\n... [RESULTADO TRUNCADO]" if len(saida) > 10000 else saida

            if name.endswith(extensoes_ignoradas): continue
            caminho_absoluto = os.path.join(root, name)
            
            try:
                if os.path.getsize(caminho_absoluto) > LIMITE_BYTES_LIDOS:
                    ignorados_por_tamanho += 1
                    continue
                caminho_relativo = os.path.relpath(caminho_absoluto, estado["pasta_raiz"])
                
                with open(caminho_absoluto, 'r', encoding='utf-8', errors='ignore') as f:
                    for i, linha in enumerate(f):
                        if termo_norm in normalizar_unicode(linha):
                            resultados.append(f"{caminho_relativo} (Linha {i+1}): {linha.strip()}")
            except Exception: pass
            
    aviso = ""
    if ignorados_por_tamanho:
        aviso = (f" [{ignorados_por_tamanho} ficheiro(s) com mais de {LIMITE_BYTES_LIDOS // (1024 * 1024)} MB"
                 f" nao foram lidos nesta busca; os bundles em dist/ ficam sempre de fora.]")
    if not resultados: return f"Nenhuma ocorrência encontrada para o termo '{termo}'." + aviso
    saida = "\\n".join(resultados)
    if len(saida) > 10000: return saida[:10000] + "\\n... [RESULTADO TRUNCADO]"
    return saida
