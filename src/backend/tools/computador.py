from src.backend.state import emit_event
from src.backend.tools.registry import register


@register(
    "tool_computador",
    "Controla um navegador Chromium real (uso do computador via Gemini 3.8 Flash + Playwright). "
    "Use quando o usuario pedir para automatizar o navegador: navegar, clicar, digitar, preencher formularios, "
    "testar um fluxo web ou coletar informacao de sites. Para tarefas de codigo (ler/editar arquivos), use as "
    "ferramentas normais de arquivo, nao esta. Fluxo: inicie com acao='executar' (objetivo e url_inicial opcional). "
    "Se a resposta indicar que uma acao requer confirmacao do usuario, pergunte ao usuario e, se ele autorizar, "
    "chame acao='continuar' com confirmar=True. Para abandonar, acao='encerrar'.",
    {
        "objetivo": {"tipo": "STRING", "desc": "Descricao da tarefa de navegacao (ex: 'buscar Gemini API no Google')", "padrao": ""},
        "acao": {"tipo": "STRING", "desc": "executar (inicia nova tarefa), continuar (retoma acao pendente) ou encerrar", "enum": ["executar", "continuar", "encerrar"], "padrao": "executar"},
        "url_inicial": {"tipo": "STRING", "desc": "URL inicial opcional para abrir antes de comecar", "padrao": ""},
        "confirmar": {"tipo": "BOOLEAN", "desc": "True para autorizar uma acao pendente que exigia confirmacao", "padrao": False},
    },
    disponivel="computer",
)
def tool_computador(objetivo="", acao="executar", url_inicial="", confirmar=False):
    emit_event("executing", function="Uso do computador (navegador)")
    from src.backend.ai.computer_use import executar_computador
    return executar_computador(objetivo, acao=acao, url_inicial=url_inicial, confirmar=confirmar)
