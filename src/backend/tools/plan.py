"""Plano de execucao e arquitetura: planejar, iniciar, atualizar e adicionar etapa.

Verbatim de tools/filesystem.py; importa-lo e o que regista as suas 4 tools de
plano. Acoplamento a saber: `tool_planejar_arquitetura` valida as URLs contra as
navegacoes do turno em `estado['urls_navegadas_turno']` (preenchido em tools/web.py),
por isso inventar URL ali continua a ser recusado.
"""
import json
import re
from datetime import datetime

from src.backend.services.materiais import destino_datado, rotulo_de_material
from src.backend.state import estado, emit_event
from src.backend.tools.registry import register


@register(
    "tool_planejar_arquitetura",
    "Obrigatório antes de criar projetos novos. Fluxo PESQUISA-PRIMEIRO: pesquise a stack na documentação oficial ANTES e decida com base no que leu; o backend valida que as URLs citadas foram realmente navegadas neste turno (inventou = rejeitado). Valida a stack e libera a trava de segurança para salvar arquivos. A linguagem e a família do projeto são decisões SUAS, tomadas pelo PROBLEMA e não pelo hábito (nativo/tempo real -> C++ ou Rust; serviço, dados e automação -> Python; browser -> HTML/JS ou o framework que a documentação oficial eleger; aplicação nativa com interface -> C++/Qt ou a ferramenta oficial da plataforma): Python NÃO é a resposta por omissão. Toda versão citada é a ESTÁVEL mais recente publicada (alpha/beta/rc/preview não entram) e confirmada na documentação oficial que você abriu neste turno. No campo 'stack' preencha uma LISTA técnica COM RÓTULO: UMA linha POR categoria, agrupando itens da MESMA categoria separados por vírgula (padrão 'Categoria: Nome versão_real', ex: 'Linguagem: Python 3.14', 'Framework: Flask 3.1.3', 'Estilo: CSS', 'Linguagem: HTML5, JavaScript (ES Modules)'; num projeto nativo: 'Linguagem: C++20', 'Build: CMake, Ninja, MSVC', 'Dependências: Qt 6, Vulkan SDK'). NUNCA repita a mesma categoria em duas linhas. Categorias NESTA ordem: Linguagem, Runtime, Framework, Dependências, API externa, Build, CI/CD, Banco de dados, Estilo — num projeto nativo o kit e o compilador entram dentro de 'Build' ('Build: CMake 4, Ninja, MSVC 19') e o toolkit (Qt, Vulkan) entra em 'Dependências'. OMITA 'Formato de saída' e 'Ambiente' quando triviais (site estático não precisa deles). Versão só quando houver versão real (HTML/CSS/JS vanilla não têm). PROIBIDO escrever 'sem framework', 'sem build step', 'sem dependências' (omita o item inexistente) e adjetivos vagos ('CSS3 moderno'/'HTML5 semântico' -> use só 'CSS'/'HTML5'). Nunca invente versões. Em 'urls_pesquisadas' PESQUISE antes (mesmo projeto estático, ao menos MDN) e cite APENAS as URLs que realmente abriu (as do status 'Navegando:'), UMA por linha; nunca escreva 'Nenhuma' nem invente/troque blog por MDN; se a fonte não for oficial, refaça a pesquisa em documentação oficial ou GitHub oficial. No campo 'estrutura_pastas' descreva a árvore de diretórios completa.",
    {
        'stack': {"tipo": "STRING", "obrig": True, "padrao": ""},
        'urls_pesquisadas': {"tipo": "STRING", "obrig": True, "padrao": ""},
        'estrutura_pastas': {"tipo": "STRING", "obrig": True, "padrao": ""},
        'etapas_planejamento': {"tipo": "STRING", "obrig": True, "padrao": ""},
    },
    disponivel="edicao",
)
def tool_planejar_arquitetura(stack: str, urls_pesquisadas: str, estrutura_pastas: str, etapas_planejamento: str):
    urls_declaradas = [u.rstrip('/').rstrip('.,;') for u in re.findall(r'https?://[^\s,;]+', urls_pesquisadas or "")]
    navegadas = {u.rstrip('/') for u in estado.get("urls_navegadas_turno", set())}

    if not navegadas:
        return (
            "⚠️ VALIDAÇÃO DE FONTES FALHOU: você ainda não pesquisou na web neste turno.\n"
            "Antes de planejar a arquitetura, PESQUISE (tool_buscar_web) a stack e as melhores práticas "
            "na documentação OFICIAL (docs.*, developer.mozilla.org, site oficial ou GitHub oficial).\n"
            "Só então liste no campo 'urls_pesquisadas' APENAS as URLs que realmente abriu."
        )

    if not urls_declaradas:
        return (
            "⚠️ VALIDAÇÃO DE FONTES FALHOU: o campo 'urls_pesquisadas' está vazio ou sem URLs.\n"
            "Liste UMA por linha as URLs que você REALMENTE abriu neste turno (as que apareceram no status 'Navegando:')."
        )

    inventadas = [u for u in urls_declaradas if u not in navegadas]
    if inventadas:
        return (
            "⚠️ VALIDAÇÃO DE FONTES FALHOU: as URLs abaixo NÃO correspondem a nenhuma navegação real deste turno "
            "(não as invente nem troque blog por MDN):\n" +
            "\n".join(f"  - {u}" for u in inventadas) +
            "\n\nURLs realmente navegadas neste turno:\n" +
            "\n".join(f"  - {u}" for u in sorted(navegadas)) +
            "\n\nRefaça a pesquisa em documentação oficial e cite apenas o que abriu de verdade."
        )

    estado["projeto_planejado"] = True
    estado["plano_stack"] = {
        "stack": stack,
        "urls_pesquisadas": urls_pesquisadas,
        "estrutura_pastas": estrutura_pastas,
    }
    emit_event("executing", function="Planejamento de Arquitetura Concluído")
    return f"SUCESSO: Arquitetura planejada e validada. Trava de segurança liberada. Você pode começar a criar os arquivos.\nStack: {stack}\nEtapas: {etapas_planejamento}"


@register(
    "tool_iniciar_plano",
    "Inicia a exibição visual de um plano de execução na interface (coluna 3). Use antes de começar tarefas complexas ou projetos novos. O plano_json deve ser uma string JSON com a estrutura: [{'id': 'etapa1', 'titulo': 'Validando Stack', 'tarefas': ['Pesquisar', 'Definir']}]",
    {
        'plano_json': {"tipo": "STRING", "obrig": True, "padrao": ""},
    },
    disponivel="edicao",
)
def tool_iniciar_plano(plano_json: str):
    try:
        plano = json.loads(plano_json)
        for i, etapa in enumerate(plano):
            etapa["tarefas_concluidas"] = []
            etapa["revelada"] = (i == 0)
        estado["plano_atual"] = plano
        guardado = _gravar_plano(plano)
        primeira = plano[0] if plano else None
        emit_event("executing", function="Iniciando plano de execução")
        emit_event("plan_started", plan=[primeira] if primeira else [], stack=estado.get("plano_stack"), total=len(plano))
        return f"SUCESSO: Plano iniciado e exibido na interface.{guardado}"
    except Exception as e:
        return f"ERRO ao iniciar plano: {str(e)}"


def _markdown_do_plano(plano):
    """O plano em markdown, com as tarefas ja concluidas riscadas como caixas marcadas."""
    partes = [f"# Plano de execução\n\n_Atualizado a {datetime.now().strftime('%Y-%m-%d %H:%M')}_\n\n"]
    for numero, etapa in enumerate(plano, 1):
        partes.append(f"## {numero}. {etapa.get('titulo', 'Etapa')}\n\n")
        feitas = set(etapa.get("tarefas_concluidas", []))
        for tarefa in etapa.get("tarefas", []):
            partes.append(f"- [{'x' if tarefa in feitas else ' '}] {tarefa}\n")
        partes.append("\n")
    return "".join(partes)


def _gravar_plano(plano):
    """Grava o plano em gerados/planos/ e devolve a linha a juntar a resposta."""
    try:
        if not estado.get("pasta_raiz"):
            return ""
        caminho = estado.get("plano_arquivo") or destino_datado(
            "plano", (plano[0].get("titulo") if plano else "") or "plano")
        estado["plano_arquivo"] = caminho
        with open(caminho, "w", encoding="utf-8") as f:
            f.write(_markdown_do_plano(plano))
        return f" Gravado em {rotulo_de_material(caminho)}."
    except Exception as falha:
        return f" (o plano nao pode ser gravado em disco: {falha})"


@register(
    "tool_atualizar_plano",
    'Atualiza o status de uma tarefa no plano visual. Risca a tarefa concluída e, se etapa_concluida=true, marca a etapa inteira como concluída.',
    {
        'id_etapa': {"tipo": "STRING", "obrig": True, "padrao": ""},
        'tarefa_concluida': {"tipo": "STRING", "obrig": True, "padrao": ""},
        'etapa_concluida': {"tipo": "BOOLEAN", "obrig": True, "padrao": False},
    },
    disponivel="edicao",
)
def tool_atualizar_plano(id_etapa: str, tarefa_concluida: str, etapa_concluida: bool):
    plano = estado.get("plano_atual")
    proxima = None
    if plano:
        for i, etapa in enumerate(plano):
            if etapa.get("id") == id_etapa:
                concluidas = etapa.setdefault("tarefas_concluidas", [])
                if etapa_concluida:
                    concluidas = list(etapa.get("tarefas", []))
                elif tarefa_concluida and tarefa_concluida not in concluidas:
                    concluidas.append(tarefa_concluida)
                etapa["tarefas_concluidas"] = concluidas
                if etapa_concluida and i + 1 < len(plano):
                    prox = plano[i + 1]
                    if not prox.get("revelada"):
                        prox["revelada"] = True
                        proxima = prox
                break
    emit_event("executing", function="Concluindo etapa do plano" if etapa_concluida else f"Atualizando plano: {tarefa_concluida}")
    emit_event("plan_updated", id_etapa=id_etapa, tarefa_concluida=tarefa_concluida, etapa_concluida=etapa_concluida)
    if proxima:
        emit_event("plan_step_added", step=proxima, total=len(plano))
    return f"SUCESSO: Plano atualizado na interface.{_gravar_plano(plano or [])}"


@register(
    "tool_adicionar_etapa_plano",
    "Adiciona uma nova etapa ao plano visual em andamento. nova_etapa_json deve ser uma string JSON: {'id': 'etapa_extra', 'titulo': 'Nova Etapa', 'tarefas': ['Tarefa 1']}",
    {
        'nova_etapa_json': {"tipo": "STRING", "obrig": True, "padrao": ""},
    },
    disponivel="edicao",
)
def tool_adicionar_etapa_plano(nova_etapa_json: str):
    try:
        etapa = json.loads(nova_etapa_json)
        etapa["tarefas_concluidas"] = []
        etapa["revelada"] = True
        plano = estado.get("plano_atual")
        if isinstance(plano, list):
            plano.append(etapa)
        emit_event("executing", function="Adicionando etapa ao plano")
        emit_event("plan_step_added", step=etapa, total=len(plano) if isinstance(plano, list) else 0)
        return f"SUCESSO: Nova etapa adicionada ao plano na interface.{_gravar_plano(plano if isinstance(plano, list) else [])}"
    except Exception as e:
        return f"ERRO ao adicionar etapa: {str(e)}"
