"""Exclusao e lixeira: apagar ficheiro/pasta (recuperavel) e listar a lixeira.

Verbatim de tools/filesystem.py; importa-lo e o que regista as suas 2 tools de
exclusao. Todo o apagamento passa por `_validar_alvo_exclusao`, que recusa a raiz
do projeto e as pastas de estado (.git/.axio) antes de tocar em nada.
"""
import os

from src.backend.state import MSG_SEM_PASTA, estado, emit_event, notificar_mudanca_arquivos
from src.backend.tools.registry import register
from src.backend.services.file_service import caminho_contido, resolver_caminho, registrar_edicao, mover_para_lixeira, listar_lixeira, listar_conteudo_lixeira, resolver_item_lixeira, restaurar_item_lixeira


_PASTAS_PROTEGIDAS = {".git", ".axio"}


def _validar_alvo_exclusao(caminho_relativo, caminho_absoluto):
    """Bloqueia exclusoes perigosas antes de tocar no disco.

    Recusa a propria raiz do projeto, qualquer caminho fora dela (defesa em
    profundidade: resolver_caminho ja bloqueia escrita fora, mas a exclusao e
    irreversivel) e as pastas estruturalmente protegidas: o .axio guarda a
    lixeira usada para recuperar o que foi apagado.
    """
    raiz = estado.get("pasta_raiz", "")
    if not raiz:
        return MSG_SEM_PASTA
    raiz_abs = os.path.abspath(raiz)
    alvo = os.path.abspath(caminho_absoluto)
    if not caminho_contido(alvo, raiz_abs):
        return f"ERRO: '{caminho_relativo}' esta fora da pasta do projeto (exclusao bloqueada)."
    if alvo == raiz_abs:
        return "ERRO: nao e possivel excluir a pasta raiz do projeto."
    nome = os.path.basename(alvo).lower()
    if nome in _PASTAS_PROTEGIDAS:
        return f"ERRO: a pasta '{nome}' e protegida (contem o controle de versao ou o estado do projeto, incluindo a propria lixeira)."
    return None


def _deletar_pasta(caminho_relativo, caminho_absoluto):
    """Move uma pasta (vazia ou com conteudo) para a lixeira.

    A pasta vazia tambem vai para a lixeira: listar_lixeira lista esse
    diretorio como item proprio (tipo 'dir') e restaura-lo recria a pasta.
    Sem isso a estrutura apagada desaparecia sem qualquer forma de recuperacao.
    """
    try:
        total = sum(len(arquivos) for _raiz, _dirs, arquivos in os.walk(caminho_absoluto))
        mover_para_lixeira(caminho_absoluto)
        if os.path.exists(caminho_absoluto):
            return f"ERRO: nao foi possivel mover a pasta '{caminho_relativo}' para a lixeira."
        notificar_mudanca_arquivos()
        if total == 0:
            return f"SUCESSO: Pasta vazia '{caminho_relativo}' movida para a lixeira."
        return f"SUCESSO: Pasta '{caminho_relativo}' movida para a lixeira ({total} arquivo(s) recuperaveis na interface)."
    except OSError as e:
        return f"ERRO: {e}"


@register(
    "tool_deletar_arquivo",
    'Move um arquivo ou uma pasta do projeto para a lixeira (recuperável pela interface, inclusive pasta vazia). Não exclui a raiz do projeto nem as pastas .git e .axio.',
    {
        'caminho_relativo': {"tipo": "STRING", "obrig": True, "padrao": ""},
    },
    disponivel="edicao",
)
def tool_deletar_arquivo(caminho_relativo: str):
    if estado.get("bloquear_edicao"):
        return "BLOQUEADO (FASE 1): Você está em modo semi-automático e ainda não recebeu aprovação para editar. Apresente seu plano e pergunte ao usuário se pode aplicar. Após a aprovação, chame 'tool_aprovar_plano' para destravar a edição."
    emit_event("executing", function=f"Excluindo: {caminho_relativo}")
    caminho_absoluto, erro_caminho = resolver_caminho(caminho_relativo, permitir_extra=False, permitir_escrita=True)
    if erro_caminho: return erro_caminho
    if not os.path.exists(caminho_absoluto): return f"ERRO: O arquivo '{caminho_relativo}' não existe."
    erro_alvo = _validar_alvo_exclusao(caminho_relativo, caminho_absoluto)
    if erro_alvo: return erro_alvo
    if os.path.isdir(caminho_absoluto): return _deletar_pasta(caminho_relativo, caminho_absoluto)
    try:
        with open(caminho_absoluto, 'r', encoding='utf-8', errors='ignore') as f:
            texto_antigo = f.read()
        mover_para_lixeira(caminho_absoluto)
        if os.path.exists(caminho_absoluto):
            return f"ERRO: não foi possível mover '{caminho_relativo}' para a lixeira."
        registrar_edicao(caminho_absoluto, texto_antigo, None)
        emit_event("action_diff", actionName=f"Excluído: {caminho_relativo}", diff=[{"type": "deleted", "text": texto_antigo}])
        notificar_mudanca_arquivos()
        return f"SUCESSO: Arquivo '{caminho_relativo}' movido para a lixeira."
    except Exception as e: return f"ERRO: {str(e)}"


@register(
    "tool_listar_lixeira",
    'Lista os itens recuperáveis na lixeira do projeto (arquivos e pastas vazias), com o item_id de cada um. Passe item_id para ver o conteúdo de uma pasta da lixeira. Use para conferir o que foi apagado, ver a contagem real e localizar um item para ler ou restaurar.',
    {
        'item_id': {"tipo": "STRING", "desc": 'Id de uma pasta da lixeira (para ver o conteúdo dela)', "padrao": ""},
    },
    disponivel="edicao",
)
def tool_listar_lixeira(item_id: str = ""):
    """Lista a lixeira do projeto - topo ou o conteúdo de uma pasta lá dentro.

    Fecha o ciclo do tool_deletar_arquivo: sem o item_id mostra o que foi apagado
    (com o id que tool_ler_lixeira e tool_restaurar_lixeira exigem); com o
    item_id, desce para dentro de uma pasta apagada sem a restaurar.
    """
    if item_id:
        emit_event("executing", function=f"Lixeira: {item_id}")
        conteudo = listar_conteudo_lixeira(item_id)
        if not conteudo:
            return (f"ERRO: '{item_id}' não é uma pasta da lixeira (ou está vazia). "
                    "Chame tool_listar_lixeira sem argumentos para ver os itens de topo.")
        linhas = [f"Conteúdo de '{item_id}' na lixeira ({len(conteudo)} item(ns)):"]
        for it in conteudo:
            linhas.append(f"  [{it.get('tipo', 'file')}] {it['id']}")
        return "\n".join(linhas)
    emit_event("executing", function="Listando lixeira")
    itens = listar_lixeira()
    if not itens:
        return "A lixeira está vazia."
    linhas = [f"{len(itens)} item(ns) recuperável(is) na lixeira (mais recentes primeiro):"]
    for it in itens:
        tipo = it.get("tipo", "file")
        alvo = it.get("original") or it.get("nome", "")
        linhas.append(f"  [{tipo}] {alvo}  (id: {it.get('id', '')})")
    return "\n".join(linhas)


@register(
    "tool_ler_lixeira",
    'Lê um arquivo que está na lixeira do projeto, SEM o restaurar (não altera nada). Passe o item_id devolvido por tool_listar_lixeira e, opcionalmente, um intervalo de linhas.',
    {
        'item_id': {"tipo": "STRING", "obrig": True, "padrao": ""},
        'linha_inicio': {"tipo": "INTEGER", "padrao": 1},
        'linha_fim': {"tipo": "INTEGER", "desc": 'Ultima linha (0 = 200 linhas a partir do inicio)', "padrao": 0},
    },
)
def tool_ler_lixeira(item_id: str, linha_inicio: int = 1, linha_fim: int = 0):
    """Lê um ficheiro guardado na lixeira sem o devolver ao projeto.

    Serve para decidir com conhecimento de causa (o que era isto?) antes de
    restaurar. Como a lixeira vive em .axio/, todos os varrimentos do projeto a
    ignoram: esta é a única porta de leitura para lá.
    """
    emit_event("executing", function=f"Lendo da lixeira: {item_id}")
    origem, erro = resolver_item_lixeira(item_id)
    if erro:
        return erro
    if os.path.isdir(origem):
        return (f"ERRO: '{item_id}' é uma pasta da lixeira, não um arquivo. "
                f"Use tool_listar_lixeira com item_id='{item_id}' para ver o conteúdo, "
                "ou tool_restaurar_lixeira para a devolver ao projeto.")
    try:
        with open(origem, "r", encoding="utf-8", errors="ignore") as f:
            linhas = f.readlines()
    except OSError as e:
        return f"ERRO: {e}"
    total = len(linhas)
    inicio = max(0, int(linha_inicio) - 1)
    fim = int(linha_fim) if linha_fim else inicio + 200
    fim = min(total, fim)
    if inicio >= fim:
        return f"ERRO: intervalo inválido (o arquivo na lixeira tem {total} linha(s))."
    trecho = "".join(linhas[inicio:fim])
    return f"--- {item_id} na lixeira ({total} linha(s); a mostrar {inicio + 1}-{fim}) ---\n{trecho}"


@register(
    "tool_restaurar_lixeira",
    'Restaura um item da lixeira para a pasta do projeto, no caminho onde estava (ou em outro caminho do projeto, se indicado em destino). Use o item_id devolvido por tool_listar_lixeira.',
    {
        'item_id': {"tipo": "STRING", "obrig": True, "padrao": ""},
        'destino': {"tipo": "STRING", "desc": 'Caminho alternativo dentro do projeto (opcional)', "padrao": ""},
    },
    disponivel="edicao",
)
def tool_restaurar_lixeira(item_id: str, destino: str = ""):
    """Devolve um item da lixeira ao projeto (caminho original ou um novo).

    O núcleo da operação vive em services/file_service.restaurar_item_lixeira,
    para ser exatamente o mesmo que a rota /api/trash_restore usa.
    """
    if estado.get("bloquear_edicao"):
        return "BLOQUEADO (FASE 1): Você está em modo semi-automático e ainda não recebeu aprovação para editar. Apresente seu plano e pergunte ao usuário se pode aplicar. Após a aprovação, chame 'tool_aprovar_plano' para destravar a edição."
    emit_event("executing", function=f"Restaurando: {item_id}")
    rel, erro = restaurar_item_lixeira(item_id, destino)
    if erro:
        return erro if erro.startswith("ERRO") else f"ERRO: {erro}"
    notificar_mudanca_arquivos()
    return f"SUCESSO: '{rel}' restaurado da lixeira para o projeto."
