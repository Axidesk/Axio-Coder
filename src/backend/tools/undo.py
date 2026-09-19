"""Historico de edicoes: desfazer, refazer e consultar a pilha.

Verbatim de tools/filesystem.py; importa-lo e o que regista as suas 3 tools de
historico. A pilha em si vive em services/file_service.py (registrar_edicao /
desfazer_edicao / refazer_edicao) - aqui fica apenas a face visivel ao modelo.
"""
import os

from src.backend.state import estado, emit_event, notificar_mudanca_arquivos
from src.backend.tools.registry import register
from src.backend.services.file_service import resolver_caminho, desfazer_edicao, refazer_edicao


@register(
    "tool_desfazer",
    "Desfaz (undo) a edição mais recente de um arquivo, restaurando o conteúdo de ANTES daquela edição. Use quando uma edição recém-feita quebrou a sintaxe ou a lógica e corrigir manualmente não vale a pena. Funciona também para edições atômicas em grupo (ex: mover função restaura origem+destino juntos). Receba o caminho_relativo do arquivo. Para saber o que pode ser desfeito, chame antes 'tool_status_desfazer'.",
    {
        'caminho_relativo': {"tipo": "STRING", "desc": 'Caminho relativo do arquivo a desfazer (ex: src/backend/app.py)', "obrig": True, "padrao": ""},
    },
    disponivel="edicao",
)
def tool_desfazer(caminho_relativo: str):
    if estado.get("bloquear_edicao"):
        return "BLOQUEADO (FASE 1): Você está em modo semi-automático e ainda não recebeu aprovação para editar. Apresente seu plano e pergunte ao usuário se pode aplicar. Após a aprovação, chame 'tool_aprovar_plano' para destravar a edição."
    emit_event("executing", function=f"Desfazendo: {caminho_relativo}")
    caminho_absoluto, erro_caminho = resolver_caminho(caminho_relativo, permitir_extra=False, permitir_escrita=True)
    if erro_caminho: return erro_caminho
    resultado = desfazer_edicao(caminho_absoluto)
    if resultado.get("status") == "ok":
        emit_event("undo_changed", acao="undo", caminho=caminho_absoluto, nome=os.path.basename(caminho_absoluto))
        notificar_mudanca_arquivos()
    return resultado.get("message", "Operação concluída.")


@register(
    "tool_refazer",
    "Refaz (redo) a edição desfeita mais recente de um arquivo, reaplicando o conteúdo de DEPOIS daquela edição. Use para reverter um 'tool_desfazer' feito por engano.",
    {
        'caminho_relativo': {"tipo": "STRING", "desc": 'Caminho relativo do arquivo a refazer (ex: src/backend/app.py)', "obrig": True, "padrao": ""},
    },
    disponivel="edicao",
)
def tool_refazer(caminho_relativo: str):
    if estado.get("bloquear_edicao"):
        return "BLOQUEADO (FASE 1): Você está em modo semi-automático e ainda não recebeu aprovação para editar. Apresente seu plano e pergunte ao usuário se pode aplicar. Após a aprovação, chame 'tool_aprovar_plano' para destravar a edição."
    emit_event("executing", function=f"Refazendo: {caminho_relativo}")
    caminho_absoluto, erro_caminho = resolver_caminho(caminho_relativo, permitir_extra=False, permitir_escrita=True)
    if erro_caminho: return erro_caminho
    resultado = refazer_edicao(caminho_absoluto)
    if resultado.get("status") == "ok":
        emit_event("undo_changed", acao="redo", caminho=caminho_absoluto, nome=os.path.basename(caminho_absoluto))
        notificar_mudanca_arquivos()
    return resultado.get("message", "Operação concluída.")


@register(
    "tool_status_desfazer",
    'Lista, por arquivo, quantas edições estão disponíveis para desfazer e refazer nesta sessão. Use para decidir qual arquivo desfazer/refazer e em quantos passos.',
    {
    },
    disponivel="edicao",
)
def tool_status_desfazer():
    emit_event("executing", function="Consultando histórico de desfazer/refazer")
    pasta_raiz = estado.get("pasta_raiz", "")
    historico = estado["file_history"]
    arquivos = []
    for caminho, hist in list(historico.items()):
        if not (hist.get("undo") or hist.get("redo")) or not os.path.exists(caminho):
            historico.pop(caminho, None)
            continue
        try:
            rel = os.path.relpath(caminho, pasta_raiz).replace("\\", "/") if pasta_raiz else caminho.replace("\\", "/")
        except ValueError:
            rel = caminho.replace("\\", "/")
        arquivos.append(f"{rel}: {len(hist['undo'])} para desfazer, {len(hist['redo'])} para refazer")
    if not arquivos:
        return "Nenhuma edição registrada para desfazer/refazer nesta sessão."
    return "\n".join(sorted(arquivos))
