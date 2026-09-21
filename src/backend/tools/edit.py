"""Escrita de conteudo: substituir texto (uma ou todas as ocorrencias) e salvar.

Verbatim de tools/filesystem.py; importa-lo e o que regista as suas 3 tools de
gravacao, todas passando por `gravar_edicao_com_diff` - o unico ponto onde se
escreve um ficheiro (a cadeia de avisos/gates de escrita esta em tools/syntax.py).
"""
import os

from src.backend.state import estado, emit_event, notificar_mudanca_arquivos
from src.backend.tools.registry import register
from src.backend.services.file_service import resolver_caminho, normalizar_unicode, registrar_edicao
from src.backend.services.diff import gerar_diff
from src.backend.tools.syntax import aviso_estrutural_pos_edicao, aviso_import_local, bloquear_import_local, validar_arquivo_apos_edicao


def _ler_para_edicao(caminho_relativo, rotulo):
    if estado.get("bloquear_edicao"):
        return None, "BLOQUEADO (FASE 1): Você está em modo semi-automático e ainda não recebeu aprovação para editar. Apresente seu plano e pergunte ao usuário se pode aplicar. Após a aprovação, chame 'tool_aprovar_plano' para destravar a edição."
    emit_event("executing", function=f"{rotulo}: {caminho_relativo}")
    caminho_absoluto, erro_caminho = resolver_caminho(caminho_relativo, permitir_extra=False, permitir_escrita=True)
    if erro_caminho:
        return None, erro_caminho
    if not os.path.exists(caminho_absoluto):
        return None, f"ERRO: O arquivo '{caminho_relativo}' não existe."
    try:
        with open(caminho_absoluto, 'r', encoding='utf-8') as f:
            conteudo = f.read()
    except Exception as e:
        return None, f"ERRO: {str(e)}"
    return (caminho_absoluto, conteudo, normalizar_unicode(conteudo)), None


def _preparar_substituicao(caminho_relativo, rotulo, texto_antigo, texto_novo):
    """Valida o caminho, le o arquivo alvo e normaliza os textos (NFC).

    Devolve ((caminho_absoluto, conteudo, conteudo_nfc, texto_antigo_nfc,
    texto_novo_nfc, ocorrencias), erro). Quando `erro` nao for None, o chamador
    deve devolve-lo imediatamente.
    """
    dados, erro = _ler_para_edicao(caminho_relativo, rotulo)
    if erro:
        return None, erro
    caminho_absoluto, conteudo, conteudo_nfc = dados
    texto_antigo_nfc = normalizar_unicode(texto_antigo)
    texto_novo_nfc = normalizar_unicode(texto_novo)
    return (caminho_absoluto, conteudo, conteudo_nfc, texto_antigo_nfc, texto_novo_nfc, conteudo_nfc.count(texto_antigo_nfc)), None


def _diagnostico_ancora(conteudo, texto_antigo):
    """Aponta onde a ancora diverge do ficheiro, para nao se adivinhar espacos."""
    linhas_arquivo = conteudo.split("\n")
    busca = texto_antigo.split("\n")
    primeira = next((l for l in busca if l.strip()), None)
    if primeira is None:
        return " O trecho antigo nao tem nenhuma linha com conteudo."
    for i, linha in enumerate(linhas_arquivo):
        if linha.strip() != primeira.strip():
            continue
        if linha != primeira:
            return (f" A linha {i + 1} tem esse texto mas com indentacao DIFERENTE: "
                    f"ficheiro={linha!r} vs ancora={primeira!r}.")
        for j, alvo in enumerate(busca):
            if i + j >= len(linhas_arquivo):
                return f" O trecho comeca a casar na linha {i + 1} mas acaba antes do fim do ficheiro."
            if linhas_arquivo[i + j] != alvo:
                return (f" O trecho comeca a casar na linha {i + 1} e diverge na linha {i + j + 1}: "
                        f"ficheiro={linhas_arquivo[i + j]!r} vs ancora={alvo!r}.")
        return (f" O trecho aparece inteiro a partir da linha {i + 1} - se a busca nao casou, "
                "ha diferenca de caracteres invisivel (reporte isto).")
    return (f" Nenhuma linha do ficheiro e igual a primeira linha da ancora "
            f"({primeira.strip()[:70]!r}).")


def gravar_edicao_com_diff(caminho_relativo, caminho_absoluto, conteudo, novo_conteudo, action_name):
    """Grava o novo conteudo, registra no undo e emite o diff para a UI.

    Devolve os avisos pos-edicao (sintaxe, checklist estrutural e import local).
    Levanta ValueError quando a trava de import local barra a escrita: nesse caso
    nada e gravado e nada entra na pilha de undo.
    """
    bloqueio = bloquear_import_local(caminho_relativo, conteudo, novo_conteudo)
    if bloqueio:
        raise ValueError(bloqueio)
    registrar_edicao(caminho_absoluto, conteudo, novo_conteudo)
    with open(caminho_absoluto, 'w', encoding='utf-8') as f:
        f.write(novo_conteudo)
    diff = gerar_diff(conteudo, novo_conteudo)
    emit_event("action_diff", actionName=action_name, diff=diff)
    notificar_mudanca_arquivos()
    return (validar_arquivo_apos_edicao(caminho_relativo, caminho_absoluto)
            + aviso_estrutural_pos_edicao(caminho_relativo, conteudo, novo_conteudo)
            + aviso_import_local(caminho_relativo, conteudo, novo_conteudo))


_PARAMS_SUBSTITUICAO = {
    'caminho_relativo': {"tipo": "STRING", "obrig": True, "padrao": ""},
    'texto_antigo': {"tipo": "STRING", "obrig": True, "padrao": ""},
    'texto_novo': {"tipo": "STRING", "obrig": True, "padrao": ""},
}


@register(
    "tool_substituir_texto",
    'Substitui texto (compara com normalização Unicode NFC — acentos compostos e decompostos casam automaticamente). NUNCA substitua caractere acentuado isolado; use âncoras longas e únicas. FUNCAO NOVA: posicione-a ABAIXO da ultima funcao correlacionada do modulo - nunca no fim do ficheiro nem em qualquer lugar; sem correlacionada, vai no fim do ficheiro ou num modulo de utilidades.',
    _PARAMS_SUBSTITUICAO,
    disponivel="edicao",
)
def tool_substituir_texto(caminho_relativo: str, texto_antigo: str, texto_novo: str):
    dados, erro = _preparar_substituicao(caminho_relativo, "Substituindo texto", texto_antigo, texto_novo)
    if erro:
        return erro
    caminho_absoluto, conteudo, conteudo_nfc, texto_antigo_nfc, texto_novo_nfc, ocorrencias = dados
    try:
        if ocorrencias == 0: return ("ERRO: O 'texto_antigo' não foi encontrado." + _diagnostico_ancora(conteudo_nfc, texto_antigo_nfc))
        elif ocorrencias > 1: return f"ERRO: O 'texto_antigo' ocorre {ocorrencias} vezes no arquivo. A âncora é ambígua. Forneça um trecho maior ou mais específico para garantir que apenas o local correto seja alterado."
        
        novo_conteudo = conteudo_nfc.replace(texto_antigo_nfc, texto_novo_nfc, 1)
        aviso = gravar_edicao_com_diff(caminho_relativo, caminho_absoluto, conteudo, novo_conteudo, f"Modificado: {caminho_relativo}")
        return f"SUCESSO: Trecho substituído em '{caminho_relativo}'.{aviso}"
    except Exception as e: return f"ERRO: {str(e)}"


_MARCA_ANTIGO = "<<<<<<< ANTIGO"
_MARCA_SEPARADOR = "======="
_MARCA_NOVO = ">>>>>>> NOVO"


def _dividir_lote(texto):
    """Corta o texto em pares (antigo, novo) pelas marcas de bloco, sem tocar no codigo la dentro."""
    itens = []
    antigo = novo = None
    for linha in normalizar_unicode(texto).split("\n"):
        marca = linha.strip()
        if marca == _MARCA_ANTIGO:
            if antigo is not None:
                return None, "ERRO: o bloco anterior nao foi fechado com '>>>>>>> NOVO'."
            antigo = []
        elif antigo is None:
            if marca:
                return None, f"ERRO: texto fora de um bloco: '{marca[:60]}'. Cada alteracao comeca com uma linha '{_MARCA_ANTIGO}'."
        elif marca == _MARCA_SEPARADOR:
            if novo is not None:
                return None, "ERRO: dois separadores '=======' no mesmo bloco."
            novo = []
        elif marca == _MARCA_NOVO:
            if novo is None:
                return None, "ERRO: o bloco fechou sem o separador '======='."
            itens.append(("\n".join(antigo), "\n".join(novo)))
            antigo = novo = None
        else:
            (antigo if novo is None else novo).append(linha)
    if antigo is not None:
        return None, "ERRO: o ultimo bloco nao foi fechado com '>>>>>>> NOVO'."
    if not itens:
        return None, "ERRO: nenhum bloco encontrado."
    return itens, None


def _aplicar_lote(conteudo_nfc, itens):
    """Aplica os pares por ordem no conteudo ja normalizado; se um falhar, nada e gravado."""
    atual = conteudo_nfc
    for indice, (antigo, novo) in enumerate(itens, 1):
        antigo = normalizar_unicode(antigo)
        novo = normalizar_unicode(novo)
        if not antigo:
            return None, f"ERRO: o bloco {indice} tem o trecho antigo vazio."
        ocorrencias = atual.count(antigo)
        if ocorrencias == 0:
            return None, (f"ERRO: o trecho do bloco {indice} nao foi encontrado (nada foi gravado)."
                          + _diagnostico_ancora(atual, antigo))
        if ocorrencias > 1:
            return None, f"ERRO: o trecho do bloco {indice} ocorre {ocorrencias} vezes no ficheiro (ancora ambigua) - nada foi gravado."
        atual = atual.replace(antigo, novo, 1)
    if atual == conteudo_nfc:
        return None, "ERRO: as substituicoes deixariam o ficheiro igual - nada foi gravado."
    return atual, None


_PARAMS_LOTE = {
    'caminho_relativo': {"tipo": "STRING", "obrig": True, "padrao": ""},
    'substituicoes': {"tipo": "STRING", "obrig": True, "padrao": ""},
}


@register(
    "tool_substituir_lote",
    'Aplica VARIAS substituicoes no mesmo ficheiro numa so gravacao (um unico diff e um unico passo de desfazer) - use quando as alteracoes ja foram decididas em conjunto. Cada alteracao vai num bloco, com quebras de linha REAIS: uma linha "<<<<<<< ANTIGO", o trecho exato como esta agora, uma linha "=======", o trecho novo (vazio para apagar) e uma linha ">>>>>>> NOVO"; repita o bloco quantas vezes precisar. Cada trecho antigo tem de ser UNICO no ficheiro e os blocos sao aplicados por ordem; se UM bloco falhar, NADA e gravado. Para APAGAR uma linha inteira, inclua a quebra de linha no fim do trecho antigo (senao fica uma linha vazia no lugar).',
    _PARAMS_LOTE,
    disponivel="edicao",
)
def tool_substituir_lote(caminho_relativo: str, substituicoes: str):
    itens, erro = _dividir_lote(substituicoes)
    if erro:
        return erro
    dados, erro = _ler_para_edicao(caminho_relativo, "Substituindo em lote")
    if erro:
        return erro
    caminho_absoluto, conteudo, conteudo_nfc = dados
    novo_conteudo, erro = _aplicar_lote(conteudo_nfc, itens)
    if erro:
        return erro
    try:
        aviso = gravar_edicao_com_diff(caminho_relativo, caminho_absoluto, conteudo, novo_conteudo, f"Modificado em lote: {caminho_relativo}")
        return f"SUCESSO: {len(itens)} substituicoes em '{caminho_relativo}'.{aviso}"
    except Exception as e: return f"ERRO: {str(e)}"


def _eh_projeto_novo():
    raiz = estado.get("pasta_raiz", "")
    if not raiz or not os.path.isdir(raiz):
        return False
    src = os.path.join(raiz, "src")
    if os.path.isdir(src):
        if os.path.isdir(os.path.join(src, "backend")) or os.path.isdir(os.path.join(src, "frontend")):
            return False
    ignorados = {".axio", ".git", "__pycache__", "node_modules", ".venv", "venv"}
    dirs_codigo = {"src", "app", "backend", "frontend", "lib", "packages"}
    ext_codigo = (".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".json", ".vue", ".toml", ".yaml", ".yml")
    try:
        itens = os.listdir(raiz)
    except OSError:
        return False
    for item in itens:
        if item in ignorados or item.startswith("."):
            continue
        caminho = os.path.join(raiz, item)
        if os.path.isdir(caminho) and item.lower() in dirs_codigo:
            return False
        if os.path.isfile(caminho) and item.lower().endswith(ext_codigo):
            return False
    return True


@register(
    "tool_salvar_arquivo",
    'Salva arquivo. FUNCAO NOVA: posicione-a ABAIXO da ultima funcao correlacionada do modulo (ex: novo getter abaixo dos getters existentes) - nunca no fim do ficheiro nem em qualquer lugar; sem correlacionada, vai no fim do ficheiro ou num modulo de utilidades. Nunca espalhe funcoes aleatoriamente.',
    {
        'caminho_relativo': {"tipo": "STRING", "obrig": True, "padrao": ""},
        'conteudo': {"tipo": "STRING", "obrig": True, "padrao": ""},
    },
    disponivel="edicao",
)
def tool_salvar_arquivo(caminho_relativo: str, conteudo: str):
    if estado.get("bloquear_edicao"):
        return "BLOQUEADO (FASE 1): Você está em modo semi-automático e ainda não recebeu aprovação para editar. Apresente seu plano e pergunte ao usuário se pode aplicar. Após a aprovação, chame 'tool_aprovar_plano' para destravar a edição."
    
    caminho_absoluto, erro_caminho = resolver_caminho(caminho_relativo, permitir_extra=False, permitir_escrita=True)
    if not erro_caminho and not os.path.exists(caminho_absoluto):
        if not estado.get("projeto_planejado") and _eh_projeto_novo():
            return (
                "⚠️ TRAVA DE SEGURANÇA DO SISTEMA: Acesso negado.\n"
                "Você tentou criar um arquivo de um projeto NOVO sem concluir as etapas obrigatórias de preparação. "
                "Esta ação foi BLOQUEADA pelo backend.\n\n"
                "Para destravar, siga EXATAMENTE nesta ordem:\n"
                "1. PESQUISE NA WEB (tool_buscar_web) a stack, a documentação atualizada e as melhores práticas/modernas.\n"
                "2. Monte a LISTA DE ETAPAS DE PLANEJAMENTO (criação de pastas, criação de módulos, validação, finalização...).\n"
                "3. Chame 'tool_planejar_arquitetura' (stack, urls_pesquisadas, estrutura_pastas, etapas_planejamento) para liberar a trava.\n"
                "4. Chame 'tool_iniciar_plano' para exibir as etapas visualmente na interface (coluna 3).\n"
                "5. Só então comece a criar os arquivos, atualizando o plano com 'tool_atualizar_plano' a cada tarefa concluída.\n\n"
                "DIRETRIZES DE CRIAÇÃO DE CÓDIGO (obrigatórias):\n"
                "- Raiz limpa: apenas arquivos de configuração essenciais.\n"
                "- Código em src/, dividido em backend/ e frontend/.\n"
                "- No máximo UMA subpasta por domínio dentro de backend/ e frontend/.\n"
                "- Modular: 1-2 arquivos para adicionar/remover uma feature sem quebrar o resto.\n"
                "- Nomes curtos, ES Modules para JS, stacks mais modernas e justificadas.\n"
            )

    emit_event("executing", function=f"Salvando Arquivo: {caminho_relativo}")
    caminho_absoluto, erro_caminho = resolver_caminho(caminho_relativo, permitir_extra=False, permitir_escrita=True)
    if erro_caminho: return erro_caminho
    try:
        texto_antigo = None
        if os.path.exists(caminho_absoluto):
            with open(caminho_absoluto, 'r', encoding='utf-8') as f:
                texto_antigo = f.read()
                
        bloqueio = bloquear_import_local(caminho_relativo, texto_antigo or "", conteudo)
        if bloqueio:
            raise ValueError(bloqueio)

        os.makedirs(os.path.dirname(caminho_absoluto), exist_ok=True)
        with open(caminho_absoluto, 'w', encoding='utf-8') as f:
            f.write(conteudo)

        registrar_edicao(caminho_absoluto, texto_antigo, conteudo)
            
        if texto_antigo:
            diff = gerar_diff(texto_antigo, conteudo)
            emit_event("action_diff", actionName=f"Salvo/Sobrescrito: {caminho_relativo}", diff=diff)
        else:
            diff = [{"type": "added", "text": conteudo}]
            emit_event("action_diff", actionName=f"Criado: {caminho_relativo}", actionType="created", diff=diff)
        notificar_mudanca_arquivos()
        
        aviso = validar_arquivo_apos_edicao(caminho_relativo, caminho_absoluto) + aviso_estrutural_pos_edicao(caminho_relativo, texto_antigo, conteudo) + aviso_import_local(caminho_relativo, texto_antigo or "", conteudo)
        return f"SUCESSO: Arquivo '{caminho_relativo}' salvo.{aviso}"
    except Exception as e: return f"ERRO: {str(e)}"


@register(
    "tool_substituir_tudo",
    "Substitui todas as ocorrências (compara com normalização Unicode NFC). PERIGO: nunca use para caractere acentuado isolado (ex: 'ó'->'o') — corrompe o arquivo; use apenas com palavras/âncoras completas.",
    _PARAMS_SUBSTITUICAO,
    disponivel="edicao",
)
def tool_substituir_tudo(caminho_relativo: str, texto_antigo: str, texto_novo: str):
    dados, erro = _preparar_substituicao(caminho_relativo, "Substituindo tudo em", texto_antigo, texto_novo)
    if erro:
        return erro
    caminho_absoluto, conteudo, conteudo_nfc, texto_antigo_nfc, texto_novo_nfc, ocorrencias = dados
    try:
        if ocorrencias == 0: return "ERRO: O 'texto_antigo' não foi encontrado. Nenhuma substituição feita."
        novo_conteudo = conteudo_nfc.replace(texto_antigo_nfc, texto_novo_nfc)
        aviso = gravar_edicao_com_diff(caminho_relativo, caminho_absoluto, conteudo, novo_conteudo, f"Substituição Global: {caminho_relativo}")
        return f"SUCESSO: Substituição global realizada. {ocorrencias} ocorrências de '{texto_antigo}' foram substituídas no arquivo '{caminho_relativo}'.{aviso}"
    except Exception as e: return f"ERRO ao realizar substituição global: {str(e)}"
