import os
import re
import time
from datetime import datetime

from src.backend.state import caminho_estado_projeto
from src.backend.services.file_service import normalizar_unicode

_STOPWORDS = {
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
    "the", "and", "that", "with", "this", "from", "have", "has", "are",
    "was", "were", "will", "would", "should", "could", "can", "may", "might",
    "must", "shall", "you", "your", "them", "they", "their", "there", "here",
    "what", "when", "where", "which", "who", "how", "why", "not", "but", "all",
    "any", "some", "each", "more", "most", "much", "many", "about", "into",
    "over", "under", "than", "then", "out", "just", "only", "very", "also",
    "such", "these", "those",
}

def garantir_pasta_knowledge():
    """Pasta de notas do projeto (.axio/knowledge), criada se ainda nao existir.

    Devolve "" quando nenhuma pasta de projeto esta selecionada: sem esta guarda,
    caminho_estado_projeto devolve "" e o os.makedirs("") levantava
    FileNotFoundError, derrubando qualquer operacao de memoria fora de um projeto.
    """
    pasta = caminho_estado_projeto("knowledge")
    if not pasta:
        return ""
    if not os.path.exists(pasta):
        os.makedirs(pasta)
    return pasta

def nome_arquivo_seguro(titulo: str) -> str:
    """Converte um título em um nome de arquivo seguro (Windows/Linux)."""
    titulo = titulo.strip()
    titulo = re.sub(r'[<>:"/\\|?*]+', '-', titulo)
    titulo = re.sub(r'[\x00-\x1f]+', '', titulo).strip()
    reservados = {"CON", "PRN", "AUX", "NUL",
                  *[f"COM{i}" for i in range(1, 10)],
                  *[f"LPT{i}" for i in range(1, 10)]}
    if not titulo or titulo.upper() in reservados:
        titulo = "nota"
    return titulo

def _para_timestamp(quando):
    """Normaliza epoch (segundos ou milissegundos) ou data ISO para um timestamp.

    Aceita o que aparece na pratica: float do os.path.getmtime, os digitos do
    nome de um ficheiro (sessao_1788037736.txt), o "2026-09-12T05:46:47.529529"
    do metadata do mempalace e a data simples "2026-09-12". Valor acima de 1e11
    e tratado como milissegundos (o sessionlog_1789181107976.json).
    """
    if quando is None or quando == "":
        return None
    if isinstance(quando, (int, float)):
        valor = float(quando)
        return valor / 1000.0 if valor > 1e11 else valor
    texto = str(quando).strip()
    if not texto:
        return None
    if texto.isdigit():
        valor = float(texto)
        return valor / 1000.0 if valor > 1e11 else valor
    try:
        return datetime.fromisoformat(texto).timestamp()
    except ValueError:
        return None

def idade_legivel(quando):
    """Idade curta e legivel ("hoje", "ha 3 dias", "ha 2 meses") de um instante.

    Ponto UNICO desta formatacao: alimenta o rotulo das memorias recuperadas
    (ai/coleta.py) e a listagem/indice das notas de knowledge. Sem idade
    explicita nao ha como distinguir uma nota de hoje de uma conversa de tres
    semanas - foi assim que uma pendencia ja concluida (o bootstrap do Supabase)
    foi repetida como se ainda estivesse em aberto.
    """
    ts = _para_timestamp(quando)
    if ts is None:
        return "?"
    dias = int((time.time() - ts) / 86400)
    if dias <= 0:
        return "hoje"
    if dias == 1:
        return "ontem"
    if dias < 14:
        return f"ha {dias} dias"
    if dias < 35:
        semanas = dias // 7
        return "ha 1 semana" if semanas == 1 else f"ha {semanas} semanas"
    if dias < 365:
        meses = dias // 30
        return "ha 1 mes" if meses == 1 else f"ha {meses} meses"
    anos = dias // 365
    return "ha 1 ano" if anos == 1 else f"ha {anos} anos"

def data_legivel(quando):
    """Data curta (AAAA-MM-DD) de um instante, para acompanhar a idade."""
    ts = _para_timestamp(quando)
    if ts is None:
        return "?"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")

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
    """Cobertura: quantos termos DA CONSULTA aparecem no texto.

    Nao e contagem de ocorrencias. Medido em 2026-09-12, com 113 notas: a
    contagem crua premiava a EXTENSAO da nota - a mais comprida (12 KB) vencia
    qualquer consulta, sobre qualquer assunto, so por repetir as palavras. A
    cobertura mede o que interessa ("esta nota fala do que perguntei?") e e
    independente do tamanho; o empate e resolvido por idade, nos chamadores.
    """
    termos = _termos_relevantes(query)
    if not termos:
        return 0.0
    texto = normalizar_unicode(conteudo).lower()
    texto = re.sub(r"[^a-z0-9\s]", " ", texto)
    return float(sum(1 for t in termos if t in texto))

def coletar_notas_knowledge():
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

NOTAS_RECENTES_NO_INDICE = 4
LIMITE_NOTAS_FALLBACK = 3
LIMITE_TRECHO_FALLBACK = 1500


def buscar_knowledge_textual(query, limite=8):
    """Fallback textual: ranqueia as notas de knowledge por cobertura dos termos da query.

    Usado quando o ChromaDB (busca semantica) falha ou estoura timeout, para nunca
    ficarmos sem contexto de memoria.
    """
    notas = coletar_notas_knowledge()
    if not notas:
        return "(nenhuma nota de knowledge para fallback textual)"
    for n in notas:
        n["score"] = _score_textual(query, n["conteudo"])
    relevantes = [n for n in notas if n["score"] > 0]
    relevantes.sort(key=lambda n: (n["score"], n["mtime"]), reverse=True)
    if not relevantes:
        recentes = sorted(notas, key=lambda n: n["mtime"], reverse=True)[:LIMITE_NOTAS_FALLBACK]
        trechos = [
            f"[{n['nome']}]\n{n['conteudo'][:LIMITE_TRECHO_FALLBACK]}" for n in recentes
        ]
        return (
            "Fallback textual do ChromaDB: nada casou com esta consulta. Abaixo as notas MAIS RECENTES "
            "(estado atual do projeto, nao necessariamente relacionadas):\n\n"
            + "\n\n".join(trechos)
        )
    trechos = [f"[{n['nome']}]\n{n['conteudo']}" for n in relevantes[:limite]]
    return (
        "Contexto recuperado por busca textual (fallback do ChromaDB):\n\n"
        + "\n\n".join(trechos)
    )

def carregar_indice_knowledge(query=None, max_notas=12):
    """Amostra do acervo: as notas que casam com a mensagem + as mais recentes.

    O piso de recencia (NOTAS_RECENTES_NO_INDICE) existe porque um indice que
    fosse so por casamento deixava notas do DIA de fora. Medido em 2026-09-12,
    com 113 notas: a nota do plano da varinha (escrita nesse dia) caiu para a
    posicao 37 de 113 numa mensagem sobre memoria e nao chegou ao contexto - eu
    conclui "nao tenho esse plano" com o plano memoria adentro. As notas
    recentes SAO o estado atual do projeto, por isso tem lugar reservado.
    O cabecalho diz quantas notas existem para o indice nunca passar por
    acervo: indice pequeno nao significa memoria vazia, significa procurar.
    """
    pasta = caminho_estado_projeto("knowledge")
    if not os.path.isdir(pasta):
        return "(nenhuma nota de knowledge)"
    notas = coletar_notas_knowledge()
    if not notas:
        return "(nenhuma nota de knowledge)"
    recentes = sorted(notas, key=lambda n: n["mtime"], reverse=True)
    if query:
        for n in notas:
            n["score"] = _score_textual(query, n["conteudo"])
        casadas = sorted(
            (n for n in notas if n["score"] > 0),
            key=lambda n: (n["score"], n["mtime"]),
            reverse=True,
        )
        limite_casadas = max(0, max_notas - NOTAS_RECENTES_NO_INDICE)
        selecionadas = casadas[:limite_casadas]
        escolhidas = {n["nome"] for n in selecionadas}
        for n in recentes:
            if len(selecionadas) >= max_notas:
                break
            if n["nome"] not in escolhidas:
                selecionadas.append(n)
                escolhidas.add(n["nome"])
        cabecalho = (
            f"{min(len(casadas), limite_casadas)} casam com esta mensagem, "
            "o resto sao as mais recentes"
        )
    else:
        selecionadas = recentes[:max_notas]
        cabecalho = "as mais recentes"
    linhas = [
        f"- {n['nome']} ({idade_legivel(n['mtime'])}): {_resumo_nota(n['conteudo'])}"
        for n in selecionadas
    ]
    return (
        f"Índice de notas (knowledge) - {len(linhas)} de {len(notas)} notas ({cabecalho}). "
        "É uma AMOSTRA, não o acervo: para ver todas use tool_gerenciar_memoria "
        "acao='listar'; para o texto completo, acao='ler'.\n"
        + "\n".join(linhas)
    )

def listar_notas_knowledge():
    """Lista as notas de knowledge com idade e tamanho, mais recentes primeiro.

    Da ao agente a informacao que faltava para CURAR a memoria de longo prazo
    (regra 24): sem a idade nao ha como perceber que uma nota ficou obsoleta, e
    o resumo permite decidir se vale a pena reler o conteudo completo.
    """
    notas = coletar_notas_knowledge()
    if not notas:
        return "(nenhuma nota de knowledge)"
    notas.sort(key=lambda n: n["mtime"], reverse=True)
    linhas = []
    for n in notas:
        idade = idade_legivel(n["mtime"])
        kb = len(n["conteudo"].encode("utf-8")) / 1024
        linhas.append(f"- {n['nome']} ({idade}, {kb:.1f} KB): {_resumo_nota(n['conteudo'])}")
    return f"{len(notas)} nota(s) de memoria (mais recente primeiro):\n" + "\n".join(linhas)
