import os
import shutil

from src.backend.memory.glossary import (
    load_glossary,
    save_glossary,
    normalizar,
    normalizar_lista,
    identificador_concreto,
    achar_linha_identificador,
    localizar_alvos,
)
from src.backend.memory.store import garantir_pasta_knowledge, nome_arquivo_seguro, dedup_nota, listar_notas_knowledge, buscar_titulos_parecidos
from src.backend.tools.registry import register
from src.backend.memory.vector import salvar_memoria_no_vetor, excluir_memoria_do_vetor, varrer_memoria_vetor, reparar_memoria_vetor, limpar_memoria_orfaos, compactar_memoria_vetor, vetor_status
from src.backend.memory.manutencao import raio_x_da_injecao, formatar_raio_x
from src.backend.state import emit_event, estado

@register(
    "tool_gerenciar_memoria",
    "Acessa a memoria persistente (notas de knowledge). acao='escrever' grava/atualiza uma nota, 'ler' devolve o corpo, 'listar' mostra as notas com idade e tamanho (passe 'filtro' - um ou varios termos, um por linha - para filtrar pelo titulo e pelo corpo, em vez de despejar as centenas de notas do acervo inteiro), 'excluir' apaga, e 'diagnostico' mede TUDO o que e injetado no contexto a cada rodada (glossario com alvos ausentes/duplicados, notas com referencias mortas ou redundantes, tamanho do vetor) e, se passar 'query', mede tambem a busca semantica (hits, quantos a dedup removeu, faixa de similaridade). Use 'diagnostico' quando o usuario quiser saber se a memoria esta limpa.",
    {
        'acao': {"tipo": "STRING", "enum": ['ler', 'escrever', 'listar', 'excluir', 'diagnostico'], "obrig": True},
        'titulo': {"tipo": "STRING"},
        'conteudo': {"tipo": "STRING"},
        'query': {"tipo": "STRING", "desc": "Somente para acao='diagnostico': frase para medir a busca semantica"},
        'filtro': {"tipo": "STRING", "desc": "Somente para acao='listar': um ou varios termos, um por linha, para filtrar as notas pelo titulo e pelo corpo"},
    },
)
def tool_gerenciar_memoria(acao: str, titulo: str = None, conteudo: str = None, query: str = None, filtro: str = None):
    emit_event("executing", function="Gerenciando memoria")
    pasta = garantir_pasta_knowledge()
    if acao == "escrever" and titulo and conteudo:
        nome_seguro = nome_arquivo_seguro(titulo)
        duplicata = dedup_nota(titulo, conteudo)
        if duplicata:
            return duplicata
        with open(os.path.join(pasta, f"{nome_seguro}.md"), "w", encoding="utf-8") as f:
            f.write(conteudo)
        status_vetor = salvar_memoria_no_vetor(titulo, conteudo)
        if status_vetor == "ok":
            return f"Memória '{titulo}' atualizada e gravada no mempalace."
        if status_vetor.startswith("adiado"):
            return (f"Memória '{titulo}' atualizada (.md). Indexação no vetor ADIADA "
                    f"- {status_vetor[8:]}: entra sozinha na fila assim que o vetor libertar. "
                    "Não é preciso repetir a gravação.")
        return f"Memória '{titulo}' atualizada (.md). Gravação no vetor: {status_vetor}."
    elif acao == "ler" and titulo:
        nome_seguro = nome_arquivo_seguro(titulo)
        caminho = os.path.join(pasta, f"{nome_seguro}.md")
        if os.path.exists(caminho):
            with open(caminho, "r", encoding="utf-8") as f:
                return f.read()
        parecidos = buscar_titulos_parecidos(titulo)
        if parecidos:
            return ("Nota não encontrada com este titulo exato. Titulos proximos:\n- "
                    + "\n- ".join(parecidos))
        return "Nota não encontrada."
    elif acao == "excluir" and titulo:
        nome_seguro = nome_arquivo_seguro(titulo)
        caminho = os.path.join(pasta, f"{nome_seguro}.md")
        if not os.path.exists(caminho):
            return "Nota não encontrada."
        os.remove(caminho)
        status_vetor = excluir_memoria_do_vetor(titulo)
        if status_vetor == "ok":
            return f"Memória '{titulo}' excluída (.md) e removida do mempalace."
        if status_vetor.startswith("adiado"):
            return (f"Memória '{titulo}' excluída (.md). Remoção no vetor ADIADA "
                    f"- {status_vetor[8:]}: sai sozinha da fila assim que o vetor libertar. "
                    "Não é preciso repetir a exclusão.")
        return f"Memória '{titulo}' excluída (.md). Remoção no vetor: {status_vetor}."
    elif acao == "listar":
        return listar_notas_knowledge(filtro)
    elif acao == "diagnostico":
        return formatar_raio_x(raio_x_da_injecao(query=query, incluir_vetor=True))
    return "Ação inválida."


@register(
    "tool_ajustar_contexto",
    "Controla o teto de tokens do historico desta sessao - quanto de conversa cabe antes de o Axio resumir e perder detalhe. Sem 'limite' devolve o valor em uso, o padrao do .env e o maximo do modelo. Use quando a tarefa for longa (modelagem com varias iteracoes, refatoracao grande, depuracao de varias voltas): suba o teto ANTES de chegar ao padrao, para nao compactar a conversa a meio do trabalho. O ajuste vale so para esta sessao e a interface reflete-o na hora (anel, barras e rotulo da memoria).",
    {
        'limite': {"tipo": "INTEGER", "desc": "Novo teto em tokens. Omita para consultar o valor atual."},
    },
)
def tool_ajustar_contexto(limite: int = None):
    from src.backend.ai.context import (
        LIMITE_TOKENS_HISTORICO_GLOBAL,
        LIMITE_TOKENS_HISTORICO_MAX,
        limite_tokens,
    )

    emit_event("executing", function="Ajustando o teto de contexto")
    atual = limite_tokens()
    if not limite:
        return (
            f"Teto de contexto em uso: {atual:,} tokens.\n"
            f"Padrao do .env: {LIMITE_TOKENS_HISTORICO_GLOBAL:,}.\n"
            f"Maximo do modelo: {LIMITE_TOKENS_HISTORICO_MAX:,}.\n"
            f"Historico agora: {sum(1 for _ in estado.get('historico_chat', []))} mensagens."
        )
    novo = max(1000, min(int(limite), LIMITE_TOKENS_HISTORICO_MAX))
    estado["limite_tokens_contexto"] = novo
    aviso = ""
    if int(limite) > LIMITE_TOKENS_HISTORICO_MAX:
        aviso = f" Pedido de {int(limite):,} cortado no maximo do modelo."
    elif int(limite) < 1000:
        aviso = f" Pedido de {int(limite):,} elevado ao minimo de 1.000."
    from src.backend.ai.context import medir_contexto
    medir_contexto(fase="execucao")
    emit_event("context_limit", anterior=atual, limite=novo, maximo=LIMITE_TOKENS_HISTORICO_MAX)
    return f"Teto de contexto: {atual:,} -> {novo:,} tokens, nesta sessao.{aviso}"

@register(
    "tool_gerenciar_banco_vetorial",
    "Gerencia o banco de dados vetorial do mempalace. Use acao='varredura' para listar as drawers e identificar órfãs/obsoletas, acao='limpar_orfaos' para REMOVER as drawers órfãs (source_file já inexistente) e acao='reparar' para reconstruir o índice HNSW (equivale a 'mempalace repair', rodando dentro do Flask sem risco de lock), acao='compactar' para rodar VACUUM no chroma.sqlite3 e devolver ao disco o espaço das drawers apagadas (sem VACUUM o ficheiro continua com o mesmo tamanho depois da limpeza) e acao='status' para acompanhar. A limpeza ABORTA sem apagar nada se as órfãs passarem de 40% do total (proporção tão alta costuma ser bug no detector, não lixo real): para autorizar acima disso, confirme os nomes em 'varredura' e repita passando limite_orfaos=1.0. Use acao='status' para saber se ha uma operacao pesada em curso (e ha quanto tempo) antes de fechar o app.",
    {
        'acao': {"tipo": "STRING", "enum": ['ler', 'escrever', 'listar', 'deletar', 'varredura', 'reparar', 'limpar_orfaos', 'compactar', 'status'], "obrig": True},
        'caminho_relativo': {"tipo": "STRING", "padrao": ""},
        'conteudo': {"tipo": "STRING"},
        'limite_orfaos': {"tipo": "NUMBER", "desc": "Somente para acao='limpar_orfaos': fração máxima de drawers órfãs tolerada antes de abortar (0 a 1). Padrão 0.4. Use 1.0 para autorizar a limpeza completa, e só depois de conferir os nomes na varredura."},
    },
)
def tool_gerenciar_banco_vetorial(acao: str, caminho_relativo: str = "", conteudo: str = None, limite_orfaos=None):
    emit_event("executing", function="Gerenciando banco vetorial")
    pasta_banco = os.path.expanduser("~/.mempalace/palace")
    if not os.path.exists(pasta_banco):
        return "Banco de dados vetorial não encontrado."
    
    if acao == "status":
        return vetor_status()
    if acao == "varredura":
        return varrer_memoria_vetor()
    elif acao == "compactar":
        return compactar_memoria_vetor()
    elif acao == "reparar":
        return reparar_memoria_vetor()
    elif acao == "limpar_orfaos":
        return limpar_memoria_orfaos(limite_orfaos if limite_orfaos not in (None, "") else None)
    elif acao == "listar":
        caminho_alvo = os.path.join(pasta_banco, caminho_relativo)
        if not os.path.exists(caminho_alvo):
            return f"Caminho {caminho_relativo} não existe."
        if os.path.isdir(caminho_alvo):
            return ", ".join(os.listdir(caminho_alvo))
        return "Não é um diretório."
    elif acao == "ler":
        caminho_alvo = os.path.join(pasta_banco, caminho_relativo)
        if os.path.exists(caminho_alvo) and os.path.isfile(caminho_alvo):
            with open(caminho_alvo, "r", encoding="utf-8") as f:
                return f.read()
        return "Arquivo não encontrado."
    elif acao == "deletar":
        caminho_alvo = os.path.join(pasta_banco, caminho_relativo)
        if os.path.exists(caminho_alvo):
            if os.path.isdir(caminho_alvo):
                shutil.rmtree(caminho_alvo)
            else:
                os.remove(caminho_alvo)
            return f"{caminho_relativo} deletado com sucesso."
        return "Caminho não encontrado."
    elif acao == "escrever" and conteudo is not None:
        caminho_alvo = os.path.join(pasta_banco, caminho_relativo)
        with open(caminho_alvo, "w", encoding="utf-8") as f:
            f.write(conteudo)
        return f"Arquivo {caminho_relativo} escrito com sucesso."
    return "Ação inválida."
def _onde_mais_o_simbolo(identificador, arquivo_indicado):
    """Onde o simbolo vive quando nao esta no ficheiro indicado.

    O aviso de 'nao encontrado' sozinho deixa quem escreveu a olhar para o ficheiro
    errado; dizer o ficheiro certo transforma o aviso em correcao.
    """
    try:
        achados = localizar_alvos([identificador])
    except Exception:
        return ""
    for arquivo, linha in achados.get(identificador) or []:
        if normalizar(arquivo) != normalizar(arquivo_indicado):
            return f"; o simbolo existe em {arquivo}:{linha} - aponte para la"
    return ""


def _texto_do_termo_do_glossario(t):
    partes = [t.get("termo", ""), *(t.get("aliases", []) or []), t.get("identificador", "")]
    return normalizar(" ".join(str(p) for p in partes if p))


def _termos_que_casam(termos, alvos):
    """Sem alvos devolve o acervo inteiro; com alvos, so quem os contem."""
    if not alvos:
        return termos
    return [t for t in termos if any(alvo in _texto_do_termo_do_glossario(t) for alvo in alvos)]


@register(
    "tool_gerenciar_glossario",
    "Gerencia o glossario de termos leigos -> codigo (data/glossary.json). Use quando descobrir um termo leigo do usuario mapeado para um identificador real (ex: 'icone do editor' -> '#btn-editor'). acao='escrever' grava com filtro critico + dedup no backend; acao='listar' mostra os termos (passe 'termo' - um ou varios, um por linha - para filtrar por termo, alias ou identificador, em vez de despejar o acervo inteiro); acao='verificar' remede a linha real de cada identificador, SEGUE o simbolo quando ele mudou de ficheiro (alvo reapontado sozinho quando so ha um sitio que o define; com varios candidatos, fica a proposta no relatorio) e reporta o que continua ausente; acao='remover' apaga. Use com criterio: so salve termos concretos e verificados no codigo, para nao poluir o glossario (ele e injetado no seu contexto toda rodada).",
    {
        'acao': {"tipo": "STRING", "enum": ['listar', 'escrever', 'verificar', 'remover'], "obrig": True},
        'termo': {"tipo": "STRING", "desc": "Termo leigo do usuario (ex: 'icone do editor'). Em acao='listar', filtra por termo, alias e identificador - aceita varios, um por linha"},
        'aliases': {"tipo": "STRING", "desc": 'Sinonimos separados por virgula'},
        'identificador': {"tipo": "STRING", "desc": "Identificador real no codigo (ex: '#btn-editor', '#editor-host', nome de funcao)"},
        'descricao': {"tipo": "STRING"},
        'localizacao_arquivo': {"tipo": "STRING", "desc": 'Arquivo onde o identificador vive'},
        'localizacao_linha': {"tipo": "INTEGER", "desc": 'Linha aproximada'},
    },
)
def tool_gerenciar_glossario(acao, termo=None, aliases=None, identificador=None, descricao=None, localizacao_arquivo=None, localizacao_linha=None):
    """Gerencia o glossario de termos leigos -> codigo com filtro critico + dedup.

    FILTRO CRITICO (aplicado no backend, deterministico):
      1. 'termo' e 'identificador' sao obrigatorios.
      2. 'identificador' precisa ser concreto (nao generico como 'coisa'/'jeito'/'botao').
      3. Dedup: se 'termo', algum alias ou o 'identificador' ja existir, atualiza a entrada
         existente em vez de duplicar.
      4. A 'linha' nunca e guardada de memoria: e MEDIDA no proprio arquivo (ver
         achar_linha_identificador). Um numero escrito a mao fica errado em silencio
         quando o arquivo e reescrito.

    acao='verificar' percorre o glossario inteiro, remede todas as linhas no ficheiro e
    reporta as entradas cujo identificador ja nao existe (arquivo mudou de nome).
    """
    emit_event("executing", function="Gerenciando glossario")
    dados = load_glossary()
    termos = dados.get("termos", []) if isinstance(dados, dict) else []

    if acao == "listar":
        if not termos:
            return "Glossario vazio."
        alvos = [normalizar(p) for p in str(termo or "").splitlines() if p.strip()]
        escolhidos = _termos_que_casam(termos, alvos)
        if not escolhidos:
            return (f"Nenhum termo do glossario casa com: {', '.join(alvos)}."
                    f" O acervo tem {len(termos)} termos - sem 'termo' a listagem sai inteira.")
        linhas = []
        for t in escolhidos:
            aliases_str = ", ".join(t.get("aliases", []))
            loc = t.get("localizacao", {}) or {}
            arquivo = loc.get("arquivo", "")
            linha = loc.get("linha", "")
            onde = f" ({arquivo}:{linha})" if arquivo else ""
            linhas.append(f"- \"{t.get('termo', '')}\" [aliases: {aliases_str}] -> {t.get('identificador', '')}{onde}")
        cabecalho = "GLOSSARIO ATUAL:" if not alvos else f"GLOSSARIO ({len(escolhidos)} de {len(termos)} casam com {', '.join(alvos)}):"
        return cabecalho + "\n" + "\n".join(linhas)

    if acao == "verificar":
        if not termos:
            return "Glossario vazio."
        # import-local: manutencao importa este modulo no topo (ciclo real), logo a importacao tem de ser tardia
        from src.backend.memory.manutencao import verificar_glossario, relatar_verificacao
        return relatar_verificacao(verificar_glossario(forcar=True))

    if acao == "remover":
        termo_norm = normalizar(termo)
        if not termo_norm:
            return "ERRO: informe o 'termo' a remover."
        novas = []
        removidos = 0
        for t in termos:
            t_norm = normalizar(t.get("termo", ""))
            ident_norm = normalizar(t.get("identificador", ""))
            if t_norm == termo_norm or ident_norm == termo_norm:
                removidos += 1
                continue
            novas.append(t)
        if removidos == 0:
            return "Nenhum termo encontrado para remover."
        save_glossary({"termos": novas})
        return f"REMOVIDO: {removidos} termo(s) removidos do glossario."

    if acao != "escrever":
        return "ERRO: acao deve ser 'listar', 'escrever' ou 'remover'."

    termo_limpo = str(termo).strip() if termo else ""
    identificador_limpo = str(identificador).strip() if identificador else ""

    if not termo_limpo:
        return "ERRO (FILTRO CRITICO): 'termo' e obrigatorio. Nao salvei nada."
    if not identificador_concreto(identificador_limpo):
        return "ERRO (FILTRO CRITICO): 'identificador' vazio ou generico ('coisa', 'jeito', 'botao' etc.). Use o identificador real (ex: '#btn-editor', '#editor-host', nome de funcao/classe). Nao salvei nada."

    alias_lista = normalizar_lista(aliases)
    termo_norm = normalizar(termo_limpo)
    ident_norm = normalizar(identificador_limpo)

    alvo = None
    for t in termos:
        t_norm = normalizar(t.get("termo", ""))
        id_norm = normalizar(t.get("identificador", ""))
        aliases_existentes = [normalizar(a) for a in t.get("aliases", [])]
        if (t_norm == termo_norm or ident_norm == id_norm or ident_norm in aliases_existentes
                or termo_norm in aliases_existentes or termo_norm == id_norm):
            alvo = t
            break

    arquivo_limpo = str(localizacao_arquivo).strip() if localizacao_arquivo else ""
    medida = achar_linha_identificador(arquivo_limpo, identificador_limpo) if arquivo_limpo else None
    if medida is not None:
        linha_final = medida
        if localizacao_linha is not None and str(localizacao_linha).strip() != str(medida):
            nota = f" [linha medida no ficheiro: {medida}; ignorado o {localizacao_linha} informado]"
        else:
            nota = f" [linha medida no ficheiro: {medida}]"
    else:
        linha_final = localizacao_linha if localizacao_linha is not None else ""
        nota = ""
        if arquivo_limpo and localizacao_linha is not None:
            nota = (f" [AVISO: '{identificador_limpo}' nao encontrado em {arquivo_limpo}; "
                    f"linha {localizacao_linha} guardada SEM conferir"
                    f"{_onde_mais_o_simbolo(identificador_limpo, arquivo_limpo)}]")

    entrada = {
        "termo": termo_limpo,
        "aliases": alias_lista,
        "identificador": identificador_limpo,
        "descricao": str(descricao).strip() if descricao else "",
        "localizacao": {
            "arquivo": arquivo_limpo,
            "linha": linha_final,
        },
    }

    if alvo is not None:
        id_alvo = normalizar(alvo.get("identificador", ""))
        termo_alvo = normalizar(alvo.get("termo", ""))
        if id_alvo == ident_norm and termo_alvo != termo_norm:
            aliases_atuais = [str(a).strip() for a in alvo.get("aliases", [])]
            lowers = [a.lower() for a in aliases_atuais]
            if termo_limpo.lower() not in lowers and termo_limpo.lower() != str(alvo.get("termo", "")).lower():
                aliases_atuais.append(termo_limpo)
            alvo["aliases"] = aliases_atuais
            if descricao:
                alvo["descricao"] = str(descricao).strip()
            if localizacao_arquivo or localizacao_linha is not None:
                alvo["localizacao"] = entrada["localizacao"]
            acao_feita = "SINONIMO ADICIONADO"
        else:
            alvo.update(entrada)
            acao_feita = "ATUALIZADO"
    else:
        termos.append(entrada)
        acao_feita = "ADICIONADO"

    save_glossary({"termos": termos})
    return (f"GLOSSARIO {acao_feita}: \"{termo_limpo}\" -> {identificador_limpo}{nota} "
            f"(total: {len(termos)} termos).")
