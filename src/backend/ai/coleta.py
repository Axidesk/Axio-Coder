"""Coleta do contexto de um turno: projeto, memoria, knowledge e codigo.

Extraido de ai/loop.py por recorte VERBATIM (o bloco veio do disco, nao foi
redigitado). O loop de raciocinio ficou so com a orquestracao (modelo -> tools ->
modelo); a busca de contexto, que corre em 4 threads com animacao de fase no
status, vive aqui.

Nao confundir com ai/context.py: aquele mede e compacta o contexto (tokens e
historico); este vai BUSCAR o contexto antes do primeiro pedido ao modelo.
"""

import os
import re
import threading
import time

from src.backend.state import emit_event
from src.backend.memory.vector import buscar_memorias_com_timeout, ROOM_NOTAS
from src.backend.memory.store import (
    carregar_indice_knowledge,
    buscar_knowledge_textual,
    idade_legivel,
    data_legivel,
)
from src.backend.memory.manutencao import deduplicar_textos
from src.backend.tools.code_index import buscar_codigo_relevante_para_contexto
from src.backend.tools.projeto_info import gerar_contexto_projeto


def _origem_da_memoria(source_path):
    """Classifica de onde veio uma memoria recuperada.

    A busca semantica mistura duas coisas muito diferentes na mesma lista: as
    notas curadas (.axio/knowledge) e as transcricoes de conversas antigas
    (.axio/chats, mineradas pelo mempalace). Sem as distinguir, uma frase dita
    em rodadas passadas entra no contexto com o mesmo peso de um facto atual -
    foi assim que "os 1,9 GB do palacequebrado continuam la" sobreviveu depois
    de a pasta ja ter sido apagada.
    """
    caminho = (source_path or "").replace("\\", "/").lower()
    if "/knowledge/" in caminho:
        return "nota curada"
    if "/chats/" in caminho:
        return "conversa antiga (historico)"
    return "memoria minerada"


def _e_nota_curada(hit):
    return _origem_da_memoria(hit.get("source_path")) == "nota curada"


def _e_historico(hit):
    return _origem_da_memoria(hit.get("source_path")) == "conversa antiga (historico)"


_EPOCH_NO_NOME = re.compile(r"_(\d{9,14})(?=\.[a-z0-9]+$)", re.IGNORECASE)

def _instante_no_nome(nome):
    """Instante codificado no nome do ficheiro (sessao_1788037736.txt).

    E a unica data FIAVEL das transcricoes: medido no palace real, o created_at
    delas aponta a mineracao (12/09) e nao o dia em que a conversa aconteceu
    (29/08, 13 dias antes). Sem isto, uma rodada de duas semanas entrava no
    contexto com a data de hoje.
    """
    if not nome:
        return None
    m = _EPOCH_NO_NOME.search(nome)
    return m.group(1) if m else None

def _instante_da_memoria(hit):
    """Instante mais fiavel da memoria, por ordem de confianca.

    1. epoch no nome do ficheiro (data REAL do conteudo, para as transcricoes);
    2. mtime da fonte no disco (data real de uma nota curada, que o metadata de
       indexacao nao guarda);
    3. created_at do metadata, como ultimo recurso.
    """
    return (
        _instante_no_nome(hit.get("source_file"))
        or _mtime_da_fonte(hit.get("source_path"))
        or hit.get("created_at")
    )

def _mtime_da_fonte(caminho):
    """Data de modificacao da fonte no disco, ou None se ja nao existir."""
    if not caminho:
        return None
    try:
        return os.path.getmtime(caminho)
    except OSError:
        return None

def _bloco_memoria(hit, projeto_atual=None):
    """Uma memoria recuperada: origem, projeto, ficheiro, data/idade e similaridade.

    O projeto sai do wing do drawer e a idade da data real do conteudo (ver
    _instante_da_memoria). Sem estes dois campos eu nao tinha como saber que uma
    memoria vinha de OUTRO projeto nem que ja tinha semanas - e citava-a como
    estado atual. O aviso "(OUTRO PROJETO)" so aparece quando o wing difere do
    projeto aberto agora.
    """
    fonte = hit.get("source_file") or "?"
    quando = _instante_da_memoria(hit)
    projeto = hit.get("wing") or "?"
    if projeto_atual and projeto != projeto_atual:
        projeto = f"{projeto} (OUTRO PROJETO)"
    cabecalho = (
        f"[{_origem_da_memoria(hit.get('source_path'))} | projeto {projeto} | {fonte} | "
        f"{data_legivel(quando)} ({idade_legivel(quando)}) | simil {hit.get('similarity')}]"
    )
    return f"{cabecalho}\n{hit.get('text', '')}"


def _rotular_memorias(hits, max_historicos=3, projeto_atual=None):
    """Formata os hits da busca com a origem de cada um, sem repetir textos.

    Reusa deduplicar_textos para a unicidade (comparacao normalizada) e mantem
    a associacao hit -> texto descartando os sobreviventes um a um.

    As notas curadas vem PRIMEIRO e as conversas antigas ficam limitadas a
    `max_historicos`. Contadas no palace real, as notas sao 111 drawers contra
    36.715 de transcricoes (331x, nao os 13x que a contagem de ficheiros
    sugere): injetar os 8 hits crus enchia o contexto de frases minhas de
    rodadas passadas, que e o que me fazia repetir o que ja tinha sido dito. O
    limite nao esconde nenhuma nota curada - e _reforcar_notas_curadas garante
    que alguma chega para ser priorizada.
    """
    ordenados = sorted(hits, key=_e_historico)
    restantes = list(deduplicar_textos([hit.get("text", "") for hit in ordenados]))
    blocos = []
    historicos = 0
    for hit in ordenados:
        texto = hit.get("text", "")
        if texto not in restantes:
            continue
        if _e_historico(hit):
            if historicos >= max_historicos:
                continue
            historicos += 1
        restantes.remove(texto)
        blocos.append(_bloco_memoria(hit, projeto_atual))
    return "\n".join(blocos)


def _reforcar_notas_curadas(query, palace_path, wing, hits):
    """Acrescenta uma busca restrita ao room das notas curadas.

    As notas vivem no room `ai_memory` e as conversas mineradas nos rooms
    tematicos do minerador. Como a proporcao e de 331x a favor das conversas,
    e normal a busca geral devolver 8 transcricoes e nenhuma nota - e sem nota
    no resultado a prioridade de _rotular_memorias nao tem o que priorizar.
    Esta segunda busca, filtrada pelo room, garante que a nota chega.

    So corre quando a primeira busca nao trouxe NENHUMA nota curada, para nao
    pagar duas buscas por rodada. Uma falha dela nao perde o que ja veio: os
    hits originais voltam intactos.

    O teto e 4s, nao os 8s da busca geral: esta e a busca BARATA por desenho
    (o filtro por room desce ao SQL do Chroma), medido em 0,35s quente contra
    4,82s a frio da busca sem filtro. Dar-lhe o orcamento grande da geral so
    serviria para, no pior caso, somar dois timeouts e prender o turno.
    """
    extra = buscar_memorias_com_timeout(
        query=query,
        palace_path=palace_path,
        wing=wing,
        n_results=3,
        timeout=4.0,
        room=ROOM_NOTAS,
    )
    return list(extra.get("results") or []) + list(hits)


def coletar_contexto(prompt_usuario, wing_atual, palace_path):
    """Busca em paralelo as 4 fontes de contexto e devolve {"nome": texto}.

    As tarefas sao independentes (rede, disco e vetor), por isso correm em
    threads; o status do frontend avanca por fases enquanto elas decorrem, para
    nao parecer que a interface parou. Uma fonte que falhe nao derruba as
    outras: o erro dela fica registado como texto do proprio campo.
    """
    def _buscar_memoria():
        if not os.path.exists(palace_path):
            return "Nenhuma memória encontrada. Esta é a primeira interação."
        resultados = buscar_memorias_com_timeout(
            query=prompt_usuario,
            palace_path=palace_path,
            wing=wing_atual,
            n_results=8,
        )
        if resultados.get("error"):
            print(f"Erro no mempalace: {resultados['error']}")
            return buscar_knowledge_textual(prompt_usuario)
        hits = resultados.get("results", [])
        if not hits:
            return "(nenhuma memória relevante para esta consulta)"
        if not any(_e_nota_curada(h) for h in hits):
            hits = _reforcar_notas_curadas(prompt_usuario, palace_path, wing_atual, hits)
        return _rotular_memorias(hits, projeto_atual=wing_atual)

    contexto = {}

    def _coletar(nome, fn):
        try:
            contexto[nome] = fn()
        except Exception as e:
            contexto[nome] = f"[falha ao carregar contexto de {nome}: {e}]"

    tarefas = [
        ("projeto", gerar_contexto_projeto),
        ("memoria", _buscar_memoria),
        ("ai_memory", lambda: carregar_indice_knowledge(prompt_usuario)),
        ("codigo", lambda: buscar_codigo_relevante_para_contexto(prompt_usuario)),
    ]
    threads = [threading.Thread(target=_coletar, args=(n, f), daemon=True) for n, f in tarefas]
    for t in threads:
        t.start()

    fases = ["Coletando memória", "Indexado", "Processando..."]
    INTERVALO_FASE = 1.0
    idx_fase = 0
    ultimo_avanco = time.time()

    while True:
        todas_concluidas = not any(t.is_alive() for t in threads)
        agora = time.time()
        if idx_fase < len(fases) - 1 and (agora - ultimo_avanco) >= INTERVALO_FASE:
            idx_fase += 1
            emit_event("status", message=f"{fases[idx_fase]}...")
            ultimo_avanco = agora
        if todas_concluidas and idx_fase >= len(fases) - 1 and (agora - ultimo_avanco) >= INTERVALO_FASE:
            break
        time.sleep(0.04)

    for t in threads:
        t.join()

    return contexto
