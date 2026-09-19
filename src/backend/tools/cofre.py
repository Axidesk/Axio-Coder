"""Ferramenta do cofre de credenciais: ler, guardar, revelar e apagar entradas.

A regra de ouro vive aqui, nao no prompt: o que o agente recebe por omissao e a
versao MASCARADA. O valor em claro so sai quando ele o pede com 'revelar', e o
caminho preferido nem isso e - '{{cofre:<id>.<campo>}}' no texto de um gesto faz
o backend abrir o cofre na hora de escrever no ecra, e o segredo nunca entra no
contexto do modelo.
"""

from src.backend.services import cofre
from src.backend.tools.registry import register


@register(
    "tool_gerenciar_cofre",
    "Le e escreve o cofre de credenciais do utilizador (data/cofre.json): identidade, email, contas de sites e chaves de API. "
    "O cofre e o que me deixa trabalhar sem interromper o utilizador - abrir uma conta num site, gerar uma chave, entrar num "
    "email para ler o codigo de confirmacao. Acoes: 'listar' devolve tudo o que existe com os valores sensiveis MASCARADOS "
    "(comprimento a vista, conteudo nao); 'escrever' cria ou atualiza uma entrada (campos no formato 'nome=valor', um por "
    "linha); 'revelar' devolve o valor em claro - use so quando precisar mesmo dele; 'remover' apaga uma entrada. "
    "PARA USAR um valor SEM O VER: escreva '{{cofre:<id>.<campo>}}' no texto de tool_operar_preview(acao='escrever') ou "
    "tool_operar_janela(acao='escrever') - o backend troca a referencia pelo valor guardado no instante do gesto. E o "
    "caminho preferido para senhas: o segredo chega ao ecra sem passar pelo seu contexto nem pelo log da conversa. "
    "A chave de API vive DENTRO do cartao da conta que a gerou (categoria='site', campo 'chave'): com ela preenchida voce "
    "usa-a direto; em branco, entre pela conta e va busca-la ou gera-la no painel do servico. Se o servico RECUSAR a "
    "chave guardada (revogada, expirada), nao pare: entre pela conta, gere outra e grave por CIMA do mesmo campo. Ao criar "
    "uma chave nova, guarde-a no cartao dessa conta para as proximas sessoes. Numa conta de site o login vive no campo "
    "'usuario', que aceita email e nome de utilizador como o site aceitar - e um campo so, porque o site tem uma caixa so.",
    {
        "acao": {
            "tipo": "STRING",
            "desc": "listar | escrever | revelar | remover",
            "enum": ["listar", "escrever", "revelar", "remover"],
            "obrig": True,
        },
        "id": {
            "tipo": "STRING",
            "desc": "Identificador da entrada (ex: 'gmail', 'openai'). Em branco no 'escrever' gera-se a partir do titulo.",
            "padrao": "",
        },
        "titulo": {
            "tipo": "STRING",
            "desc": "Nome legivel da entrada (ex: 'Gmail pessoal').",
            "padrao": "",
        },
        "categoria": {
            "tipo": "STRING",
            "desc": "identidade | email | site | servidor",
            "enum": ["identidade", "email", "site", "servidor"],
            "padrao": "",
        },
        "campos": {
            "tipo": "STRING",
            "desc": "Campos no formato 'nome=valor', um por linha. Ex: 'endereco=eu@gmail.com\\nsenha=segredo\\nservidor_imap=imap.gmail.com'",
            "padrao": "",
        },
        "campo": {
            "tipo": "STRING",
            "desc": "Com acao='revelar', qual campo revelar. Em branco devolve a entrada inteira em claro.",
            "padrao": "",
        },
    },
)
def tool_gerenciar_cofre(acao, id="", titulo="", categoria="", campos="", campo=""):
    acao = (acao or "").strip().lower()
    if acao == "listar":
        return _listar_cofre()
    if acao == "escrever":
        return _escrever_no_cofre(id, titulo, categoria, campos)
    if acao == "revelar":
        return _revelar_do_cofre(id, campo)
    if acao == "remover":
        return _remover_do_cofre(id)
    return f"ERRO: acao desconhecida '{acao}'. Use listar, escrever, revelar ou remover."


def _campos_do_texto(texto):
    """Le 'nome=valor' por linha, separando no PRIMEIRO '=' para o valor poder conter '='."""
    if not texto:
        return {}
    linhas = texto.split("\n") if "\n" in texto else texto.split(";")
    campos = {}
    for linha in linhas:
        if "=" not in linha:
            continue
        nome, valor = linha.split("=", 1)
        nome = nome.strip().lower()
        if nome:
            campos[nome] = valor.strip()
    return campos


def _linhas_da_entrada(entrada):
    categoria = entrada.get("categoria")
    esperados = list((cofre.CATEGORIAS.get(categoria) or {}).get("campos") or ())
    campos = entrada.get("campos") or {}
    linhas = []
    for nome in dict.fromkeys(esperados + list(campos)):
        valor = campos.get(nome) or ""
        linhas.append(f"  {nome}: {cofre.mascarar(valor, detalhe=True) if (valor and cofre.e_sensivel(nome)) else (valor or '(vazio)')}")
    return "\n".join(linhas)


def _listar_cofre():
    entradas = cofre.listar(detalhe=True)
    if not entradas:
        return (
            "O cofre esta vazio. Guarde a primeira credencial com acao='escrever', por exemplo:\n"
            "  titulo='Gmail pessoal', categoria='email', campos='endereco=eu@gmail.com\\nsenha=...\\n"
            "servidor_imap=imap.gmail.com'"
        )
    partes = []
    for entrada in entradas:
        linhas = [f"[{entrada['id']}] {entrada['titulo']} ({entrada['categoria']})"]
        for nome, valor in (entrada.get("campos") or {}).items():
            linhas.append(f"  {nome}: {valor or '(vazio)'}")
        if entrada.get("faltando"):
            linhas.append(f"  FALTA definir: {', '.join(entrada['faltando'])}")
        partes.append("\n".join(linhas))
    return (
        "\n".join(partes)
        + "\n\nSensiveis vem mascarados de proposito. Para USAR um valor sem o ver, escreva "
        "'{{cofre:<id>.<campo>}}' no texto de tool_operar_preview(escrever) ou tool_operar_janela(escrever)."
    )


def _escrever_no_cofre(id, titulo, categoria, campos):
    id = (id or "").strip()
    existente = cofre.obter(id, revelar=True) if id else None
    if not existente and not (titulo or "").strip():
        return "ERRO: escrever exige 'titulo' (ex: 'Gmail') ou o 'id' de uma entrada que ja exista."
    titulo = (titulo or "").strip() or (existente or {}).get("titulo") or id
    categoria = (categoria or "").strip().lower() or (existente or {}).get("categoria") or "site"
    try:
        entrada = cofre.definir({
            "id": id or None,
            "titulo": titulo,
            "categoria": categoria,
            "campos": _campos_do_texto(campos),
        })
    except ValueError as e:
        return f"ERRO: {e}"
    return (
        f"Guardado no cofre: [{entrada['id']}] {entrada['titulo']} ({entrada['categoria']}).\n"
        f"{_linhas_da_entrada(entrada)}\n"
        f"Para usar um destes valores sem o escrever aqui, referencie '{{{{cofre:{entrada['id']}.<campo>}}}}' no texto do gesto."
    )


def _revelar_do_cofre(id, campo):
    if not id:
        return "ERRO: revelar exige 'id' (veja os identificadores com acao='listar')."
    campo = (campo or "").strip().lower()
    if campo:
        valor = cofre.obter(id, revelar=True, campo=campo)
        if valor is None:
            return f"ERRO: nao ha o campo '{campo}' em '{id}'."
        return f"{id}.{campo} = {valor}"
    entrada = cofre.obter(id, revelar=True)
    if entrada is None:
        return f"ERRO: nao ha entrada '{id}' no cofre."
    linhas = [f"[{entrada['id']}] {entrada['titulo']} ({entrada['categoria']})"]
    for nome, valor in (entrada.get("campos") or {}).items():
        linhas.append(f"  {nome}: {valor or '(vazio)'}")
    return "\n".join(linhas)


def _remover_do_cofre(id):
    if not id:
        return "ERRO: remover exige 'id'."
    if not cofre.remover(id):
        return f"ERRO: nao ha entrada '{id}' no cofre."
    return f"Entrada '{id}' removida do cofre."
