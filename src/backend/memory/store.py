import os
import re

from src.backend.state import caminho_estado_projeto
from src.backend.services.file_service import normalizar_unicode

_STOPWORDS = {
    # português
    "como", "para", "uma", "umas", "uns", "que", "com", "dos", "das", "por",
    "pela", "pelo", "mas", "nao", "isso", "isto", "entao", "ser", "sao", "mais",
    "muito", "muita", "muitos", "muitas", "ele", "ela", "eles", "elas", "voce",
    "seu", "sua", "seus", "suas", "tambem", "quando", "onde", "qual", "quais",
    "porque", "depois", "antes", "sobre", "entre", "cada", "toda", "todo",
    "todos", "todas", "tudo", "nada", "algo", "algum", "alguma", "alguns",
    "algumas", "mesmo", "mesma", "outra", "outro", "outros", "outras", "essa",
    "esse", "esses", "essas", "este", "esta", "estes", "estas", "aquele",
    "aquela", "aqueles", "aquelas", "tem", "foi", "era", "eram", "faz", "fazer",
    "feito", "neste", "nesta", "nesse", "nessa", "nesses", "nessas", "sem",
    "ate", "ainda", "agora", "aqui", "ali", "nos", "nas", "num", "numa", "pode",
    "podem", "deve", "devem", "vai", "vao", "so", "ja", "sim", "bem", "bom",
    "ter", "estar", "for", "haja", "haver", "houve", "dizer", "diz", "quer",
    "apos", "durante", "apenas", "tipo", "tipos", "forma", "maneira", "exemplo",
    "caso", "parte", "coisa", "coisas", "meio", "vez", "vezes",
    # inglês
    "the", "and", "for", "that", "with", "this", "from", "have", "has", "are",
    "was", "were", "will", "would", "should", "could", "can", "may", "might",
    "must", "shall", "you", "your", "them", "they", "their", "there", "here",
    "what", "when", "where", "which", "who", "how", "why", "not", "but", "all",
    "any", "some", "each", "more", "most", "much", "many", "about", "into",
    "over", "under", "than", "then", "out", "just", "only", "very", "also",
    "such", "these", "those",
}

def garantir_pasta_knowledge():
    pasta = caminho_estado_projeto("knowledge")
    if not os.path.exists(pasta):
        os.makedirs(pasta)
    return pasta

def nome_arquivo_seguro(titulo: str) -> str:
    """Converte um título em um nome de arquivo seguro (Windows/Linux)."""
    titulo = titulo.strip()
    # Substitui caracteres inválidos em nomes de arquivo por hífen.
    titulo = re.sub(r'[<>:"/\\|?*]+', '-', titulo)
    # Remove caracteres de controle e espaços nas bordas.
    titulo = re.sub(r'[\x00-\x1f]+', '', titulo).strip()
    reservados = {"CON", "PRN", "AUX", "NUL",
                  *[f"COM{i}" for i in range(1, 10)],
                  *[f"LPT{i}" for i in range(1, 10)]}
    if not titulo or titulo.upper() in reservados:
        titulo = "nota"
    return titulo

def _normalizar_para_dedup(texto):
    texto = normalizar_unicode(texto).lower()
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    return " ".join(texto.split())

def _similaridade_jaccard(a, b):
    ta = set(a.split())
    tb = set(b.split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)

def dedup_nota(titulo, conteudo):
    pasta = garantir_pasta_knowledge()
    if not os.path.isdir(pasta):
        return None
    novo = _normalizar_para_dedup(conteudo)
    if not novo:
        return None
    nome_escrita = nome_arquivo_seguro(titulo)
    try:
        nomes = [f for f in os.listdir(pasta) if f.endswith(".md")]
    except OSError:
        return None
    for nome in nomes:
        if nome[:-3] == nome_escrita:
            continue
        caminho = os.path.join(pasta, nome)
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                existente = f.read()
        except Exception:
            continue
        exist_norm = _normalizar_para_dedup(existente)
        if not exist_norm:
            continue
        simil = _similaridade_jaccard(novo, exist_norm)
        curto, longo = sorted((novo, exist_norm), key=len)
        contem = bool(curto) and curto in longo and len(curto) >= 0.6 * len(longo)
        if novo == exist_norm or simil >= 0.8 or contem:
            pct = int(simil * 100)
            return (
                f"⚠️ DEDUP: conteúdo ~{pct}% similar à nota existente '{nome[:-3]}'. "
                f"Não escrevi para não duplicar o fato. Para atualizar, use acao='ler' "
                f"com esse título, edite e reescreva; ou use título/conteúdo genuinamente novo."
            )
    return None

def _resumo_nota(conteudo, limite=160):
    linhas = [l.strip() for l in conteudo.splitlines() if l.strip()]
    if not linhas:
        return "(vazia)"
    primeira = linhas[0].lstrip("#").strip()
    if len(primeira) > limite:
        primeira = primeira[:limite] + "…"
    return primeira

def _termos_relevantes(query):
    if not query:
        return []
    q = normalizar_unicode(query).lower()
    q = re.sub(r"[^a-z0-9\s]", " ", q)
    palavras = [p for p in q.split() if len(p) >= 3 and p not in _STOPWORDS]
    vistos = []
    for p in palavras:
        if p not in vistos:
            vistos.append(p)
    return vistos

def _score_textual(query, conteudo):
    termos = _termos_relevantes(query)
    if not termos:
        return 0.0
    texto = normalizar_unicode(conteudo).lower()
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    return float(sum(texto.count(t) for t in termos))

def _coletar_notas_knowledge():
    pasta = caminho_estado_projeto("knowledge")
    if not os.path.isdir(pasta):
        return []
    notas = []
    try:
        nomes = sorted([f for f in os.listdir(pasta) if f.endswith(".md")])
    except OSError:
        return []
    for nome in nomes:
        caminho = os.path.join(pasta, nome)
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                conteudo = f.read().strip()
            mtime = os.path.getmtime(caminho)
        except Exception:
            continue
        notas.append({"nome": nome[:-3], "conteudo": conteudo, "mtime": mtime})
    return notas

def buscar_knowledge_textual(query, limite=8):
    """Fallback textual: ranqueia as notas de knowledge por ocorrencia de termos da query.

    Usado quando o ChromaDB (busca semantica) falha ou estoura timeout, para nunca
    ficarmos sem contexto de memoria.
    """
    notas = _coletar_notas_knowledge()
    if not notas:
        return "(nenhuma nota de knowledge para fallback textual)"
    for n in notas:
        n["score"] = _score_textual(query, n["conteudo"])
    relevantes = [n for n in notas if n["score"] > 0]
    if not relevantes:
        return "(nenhuma nota de knowledge relevante para esta consulta — fallback textual)"
    relevantes.sort(key=lambda n: n["score"], reverse=True)
    trechos = [f"[{n['nome']}]\n{n['conteudo']}" for n in relevantes[:limite]]
    return (
        "Contexto recuperado por busca textual (fallback do ChromaDB):\n\n"
        + "\n\n".join(trechos)
    )

def carregar_indice_knowledge(query=None, max_notas=12):
    pasta = caminho_estado_projeto("knowledge")
    if not os.path.isdir(pasta):
        return "(nenhuma nota de knowledge)"
    notas = _coletar_notas_knowledge()
    if not notas:
        return "(nenhuma nota de knowledge)"
    if query:
        for n in notas:
            n["score"] = _score_textual(query, n["conteudo"])
        relevantes = [n for n in notas if n["score"] > 0]
        if not relevantes:
            return "(nenhuma nota de knowledge relevante para esta consulta)"
        relevantes.sort(key=lambda n: (n["score"], n["mtime"]), reverse=True)
        notas = relevantes
    else:
        notas.sort(key=lambda n: n["mtime"], reverse=True)
    linhas = [f"- {n['nome']}: {_resumo_nota(n['conteudo'])}" for n in notas[:max_notas]]
    return (
        "Índice de notas (knowledge). Para o conteúdo completo, use a busca "
        "semântica do mempalace ou tool_gerenciar_memoria com acao='ler':\n"
        + "\n".join(linhas)
    )
