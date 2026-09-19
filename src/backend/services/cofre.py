"""Cofre de credenciais do utilizador: identidade, email, contas de sites e chaves de API.

O agente precisa de credenciais para trabalhar sozinho - abrir uma conta, gerar
uma chave, ler o email de confirmacao - e pedi-las ao utilizador a cada vez
interrompe o trabalho dele. O cofre guarda-as entre sessoes, ao lado das chaves
que ja vivem em settings.json.

SEGURANCA, sem teatro: o ficheiro e JSON em claro (data/cofre.json). Nao ha
palavra-passe mestra, logo nao ha cifra que valha - cifrar com uma chave guardada
ao lado do ficheiro e decoracao, e decoracao que da a sensacao falsa de
proteccao. O que este modulo garante de facto:
  (a) o ficheiro esta no .gitignore e nunca entra no repositorio;
  (b) a leitura devolve MASCARADO por omissao, para nenhum valor cair no contexto
      do modelo nem no log da sessao por acidente;
  (c) o valor pode ser USADO sem ser visto - '{{cofre:<id>.<campo>}}' escrito no
      texto de um gesto e trocado aqui, no backend, no momento de escrever no
      ecra; o segredo nunca passa pelo modelo. Revelar um valor em claro e um ato
      explicito ('revelar'), nunca o caminho por omissao.

O ficheiro e UM so e vive no DATA_DIR do proprio Axio: nao depende do projeto
aberto, logo o que esta aqui (identidade, email, contas) esta em TODOS os
projetos, e o que se guarda num projeto fica ao alcance no proximo.

LIMITE CONHECIDO: o DATA_DIR esta dentro de uma pasta do Dropbox - o cofre viaja
para a nuvem como qualquer outro ficheiro de data/. Se isso nao servir, muda-se o
caminho numa linha.
"""

import json
import re
import time

from src.backend.config import caminho_data
from src.backend.services.persistencia import gravar_json_atomico

NOME_ARQUIVO = "cofre.json"

CATEGORIAS = {
    "identidade": {
        "rotulo": "Identidade",
        "dica": "Quem voce e. E daqui que eu tiro nome, email e telefone para preencher formularios de cadastro sem perguntar.",
        "campos": ("nome", "email", "telefone", "documento", "nascimento", "morada"),
    },
    "email": {
        "rotulo": "Email",
        "dica": "A sua caixa de entrada. Guardo aqui endereco e senha para eu abrir o email e ler o codigo de confirmacao de um cadastro, sem interromper o trabalho.",
        "campos": ("endereco", "senha", "servidor_imap", "email_de_busca"),
    },
    "site": {
        "rotulo": "Contas de sites",
        "dica": "Login num site ou servico e, no mesmo cartao, a chave de API dele. O campo 'E-mail / usuario' aceita os dois - e o mesmo que o site pede na caixa de entrada. Com a chave preenchida eu uso-a direto; em branco, entro pela conta (ou crio-a) e vou busca-la ou gera-la no painel do servico.",
        "campos": ("url", "usuario", "senha", "chave", "notas"),
        "rotulos": {"usuario": "E-mail / usuario"},
        "opcionais": ("chave",),
    },
    "servidor": {
        "rotulo": "Servidores e acessos",
        "dica": "Acesso a uma maquina, nao a um site: host, porta, usuario e senha (SSH de uma VPS, banco de dados, FTP). E onde o codigo corre ou onde os dados vivem.",
        "campos": ("host", "usuario", "senha", "porta", "notas"),
    },
}

CAMPOS_SENSIVEIS = ("senha", "password", "valor", "token", "secret", "chave", "api_key")

ROTULOS_DE_CAMPO = {
    "nome": "Nome",
    "email": "Email",
    "endereco": "Endereco",
    "telefone": "Telefone",
    "documento": "Documento",
    "nascimento": "Nascimento",
    "morada": "Morada",
    "servidor_imap": "Servidor IMAP",
    "email_de_busca": "Email de busca",
    "url": "Site",
    "usuario": "Usuario",
    "senha": "Senha",
    "chave": "Chave de API",
    "host": "Host",
    "porta": "Porta",
    "notas": "Notas",
}

_ALIAS_DE_CAMPO = {"email": "usuario"}

_PLACEHOLDER = re.compile(r"\{\{\s*cofre:\s*([^}.]+?)\s*(?:\.\s*([A-Za-z0-9_]+))?\s*\}\}")


def _caminho():
    return caminho_data(NOME_ARQUIVO)


def categorias():
    """Metadados das categorias para a janela: rotulo, dica, campos e como cada campo se le.

    Os rotulos sao a UNICA traducao de nome tecnico para texto de ecra - a janela
    nao inventa nenhum, para nao haver dois sitios a dizer coisas diferentes sobre
    o mesmo campo.
    """
    return {
        chave: {
            "rotulo": dados["rotulo"],
            "dica": dados["dica"],
            "campos": list(dados["campos"]),
            "rotulos": {**ROTULOS_DE_CAMPO, **(dados.get("rotulos") or {})},
        }
        for chave, dados in CATEGORIAS.items()
    }


def e_sensivel(campo):
    return any(termo in (campo or "").lower() for termo in CAMPOS_SENSIVEIS)


def identificador(titulo):
    """Id estavel a partir do titulo: 'Gmail pessoal' -> 'gmail_pessoal'."""
    base = re.sub(r"[^a-z0-9]+", "_", (titulo or "").strip().lower()).strip("_")
    return base or "entrada"


def mascarar(valor, detalhe=False):
    """Deixa o valor reconhecivel sem o entregar.

    Na JANELA (detalhe=False) a mascara e sempre a mesma - oito pontos - e nao
    revela nem o comprimento nem o fim do valor: quem olha para o ecra ve que ha
    uma senha guardada, e nada mais. Com detalhe=True (para a ferramenta) aparece
    o comprimento e os ultimos quatro caracteres, que e o que permite reconhecer
    um valor truncado numa colagem - um erro comum e silencioso - sem o mostrar a
    quem esta a olhar para a janela.
    """
    texto = valor if isinstance(valor, str) else json.dumps(valor, ensure_ascii=False)
    if not texto:
        return ""
    if not detalhe:
        return "•" * 8
    if len(texto) <= 8:
        return "•" * len(texto)
    return "•" * 6 + texto[-4:] + f" ({len(texto)})"


def _fundir_chaves_nas_contas(entradas):
    """Traz o cofre antigo para a forma atual: a categoria 'api' virou o campo 'chave' da conta do site.

    Existiam duas entradas para o mesmo servico - a conta (com 'senha') e a chave
    (com 'valor') -, e isso obrigava a guardar duas vezes o que so faz sentido
    junto. Quem tinha a categoria 'api' passa a 'site': com conta de mesmo id, a
    chave entra nela e o duplicado sai; sem conta, a propria entrada vira a conta.
    O campo 'conta' (que apontava para o site) desaparece, porque a chave passou a
    viver dentro do cartao que ele apontava.
    """
    contas = {e.get("id"): e for e in entradas if (e.get("categoria") or "").lower() == "site"}
    saida = []
    for entrada in entradas:
        if (entrada.get("categoria") or "").lower() != "api":
            saida.append(entrada)
            continue
        campos = dict(entrada.get("campos") or {})
        chave = campos.pop("valor", "")
        campos.pop("conta", None)
        conta = contas.get(entrada.get("id"))
        if conta is None:
            campos["chave"] = chave
            entrada["categoria"] = "site"
            entrada["campos"] = campos
            saida.append(entrada)
            continue
        alvo = dict(conta.get("campos") or {})
        for nome, valor in [("chave", chave), *campos.items()]:
            if valor and not alvo.get(nome):
                alvo[nome] = valor
        conta["campos"] = alvo
    return saida


def _fundir_email_no_usuario(entradas):
    """Traz o cofre antigo para a forma atual: nas contas de site, 'email' virou 'usuario'.

    Eram dois campos para a mesma coisa - a caixa de entrada do site aceita email
    ou nome de utilizador, e quem preenchia escrevia sempre num deles. Com os dois
    no cartao, um ficava eternamente vazio e ainda era anunciado como falta, sem
    dizer nada a mais. Valor que so tenha num dos campos passa para 'usuario';
    valor diferente nos dois nao se apaga - vai para as notas, para o utilizador
    o ver e corrigir a mao. Idempotente: sem 'email' no cartao, nao faz nada.
    """
    for entrada in entradas:
        if (entrada.get("categoria") or "").lower() != "site":
            continue
        campos = dict(entrada.get("campos") or {})
        if "email" not in campos:
            continue
        email = str(campos.pop("email") or "").strip()
        login = str(campos.get("usuario") or "").strip()
        if email and not login:
            campos["usuario"] = email
        elif email and email.lower() != login.lower():
            notas = str(campos.get("notas") or "").strip()
            aviso = f"tambem entra com: {email}"
            campos["notas"] = f"{notas}; {aviso}" if notas else aviso
        entrada["campos"] = campos
    return entradas


def carregar():
    try:
        with open(_caminho(), "r", encoding="utf-8") as f:
            dados = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        dados = {}
    entradas = dados.get("entradas") if isinstance(dados, dict) else None
    if not isinstance(entradas, list):
        return {"entradas": []}
    return {"entradas": _fundir_email_no_usuario(_fundir_chaves_nas_contas(entradas))}


def _gravar(entradas):
    gravar_json_atomico(_caminho(), {"entradas": entradas})
    return {"entradas": entradas}


def _localizar(entradas, chave):
    alvo = (chave or "").strip().lower()
    if not alvo:
        return None
    for entrada in entradas:
        if entrada.get("id") == alvo or (entrada.get("titulo") or "").strip().lower() == alvo:
            return entrada
    return None


def mascarar_entrada(entrada, detalhe=False):
    """Uma entrada com os valores sensiveis tapados e o que falta dito explicitamente.

    Os campos que a categoria PREVE entram sempre na lista, mesmo sem valor: e o
    que transforma 'esta tudo tapado' em 'falta a senha e o servidor_imap', que e
    a informacao com que se trabalha a seguir. `vazios` e tudo o que esta em
    branco; `faltando` so os SENSIVEIS em branco, que sao os unicos que travam um
    fluxo de facto (sem senha nao ha login) e por isso os unicos que a janela
    precisa de anunciar.
    """
    campos = dict(entrada.get("campos") or {})
    meta = CATEGORIAS.get(entrada.get("categoria")) or {}
    opcionais = meta.get("opcionais") or ()
    for nome in meta.get("campos") or ():
        campos.setdefault(nome, "")
    return {
        "id": entrada.get("id"),
        "titulo": entrada.get("titulo"),
        "categoria": entrada.get("categoria"),
        "atualizado": entrada.get("atualizado"),
        "campos": {
            nome: (mascarar(valor, detalhe) if e_sensivel(nome) else valor)
            for nome, valor in campos.items()
        },
        "vazios": [nome for nome, valor in campos.items() if not valor],
        "faltando": [
            nome for nome, valor in campos.items()
            if not valor and e_sensivel(nome) and nome not in opcionais
        ],
    }


def listar(revelar=False, detalhe=False):
    """Entradas do cofre. Com `revelar=False` (o normal) nenhum segredo sai daqui.

    A lista revelada existe para os OLHOS do utilizador na janela de configuracoes;
    o agente le a mascarada, para o segredo nao entrar no contexto dele nem, por
    arrasto, no log da sessao. `detalhe` mexe so no que a mascara deixa ver: a
    janela recebe sempre os mesmos oito pontos, a ferramenta recebe o comprimento e
    o fim do valor - que e o que lhe permite reconhecer uma colagem truncada.
    """
    entradas = carregar()["entradas"]
    if revelar:
        return entradas
    return [mascarar_entrada(entrada, detalhe) for entrada in entradas]


def _valor_do_campo(campos, campo):
    """Valor de um campo, aceitando ainda o nome antigo quando o atual nao o tem.

    '{{cofre:<id>.email}}' era o campo que existia na conta de site antes da
    fusao com 'usuario'; a referencia antiga continua a resolver, para nao falhar
    em silencio no meio de um gesto de login.
    """
    valor = campos.get(campo)
    if valor:
        return valor
    alternativo = _ALIAS_DE_CAMPO.get(campo)
    return campos.get(alternativo) if alternativo else valor


def obter(chave, revelar=False, campo=""):
    entrada = _localizar(carregar()["entradas"], chave)
    if entrada is None:
        return None
    if not campo:
        return entrada if revelar else mascarar_entrada(entrada)
    valor = _valor_do_campo(entrada.get("campos") or {}, campo)
    if valor is None:
        return None
    return valor if revelar else mascarar(valor)


def definir(dados):
    """Cria ou atualiza uma entrada, juntando os campos em vez de os substituir.

    Campo que chega com a mascara (a janela a mostrar pontos) NAO apaga o valor
    guardado: e o que impede o estrago classico de salvar por cima com o que se
    tinha no ecra em vez do segredo.
    """
    titulo = (dados.get("titulo") or "").strip()
    if not titulo:
        raise ValueError("a entrada precisa de um titulo")
    categoria = (dados.get("categoria") or "site").strip().lower()
    if categoria not in CATEGORIAS:
        raise ValueError(f"categoria desconhecida: {categoria} (use {', '.join(CATEGORIAS)})")

    chave = (dados.get("id") or "").strip().lower() or identificador(titulo)
    entradas = carregar()["entradas"]
    agora = time.strftime("%Y-%m-%d %H:%M:%S")
    entrada = next((e for e in entradas if e.get("id") == chave), None)
    if entrada is None:
        entrada = {"id": chave, "criado": agora, "campos": {}}
        entradas.append(entrada)

    antigos = entrada.get("campos") or {}
    novos = {}
    for nome, valor in (dados.get("campos") or {}).items():
        nome = (nome or "").strip().lower()
        if not nome:
            continue
        valor = "" if valor is None else str(valor)
        if "•" in valor and antigos.get(nome):
            continue
        novos[nome] = valor

    entrada.update({
        "titulo": titulo,
        "categoria": categoria,
        "campos": {**antigos, **novos},
        "atualizado": agora,
    })
    _gravar(entradas)
    return entrada


def remover(chave):
    entradas = carregar()["entradas"]
    restantes = [e for e in entradas if e.get("id") != (chave or "").strip().lower()]
    if len(restantes) == len(entradas):
        return False
    _gravar(restantes)
    return True


def resolver(texto):
    """Troca '{{cofre:<id>.<campo>}}' pelo valor guardado. Devolve (texto, faltantes).

    E o unico caminho pelo qual um segredo chega a um gesto sem passar pelo
    modelo: o texto que o agente escreveu traz a referencia, o backend abre o
    cofre na hora de o escrever no ecra, e o que sobra na conversa e a referencia.
    Referencia que nao resolve fica intacta e nomeada, para o gesto nao sair com
    o placeholder no campo e ninguem perceber por que.
    """
    if not texto or "{{" not in texto:
        return texto, []
    entradas = carregar()["entradas"]
    faltantes = []

    def _troca(alvo):
        entrada = _localizar(entradas, alvo.group(1))
        if entrada is None:
            faltantes.append(alvo.group(0))
            return alvo.group(0)
        campos = entrada.get("campos") or {}
        campo = alvo.group(2)
        if not campo:
            campo = next((n for n in campos if e_sensivel(n) and campos.get(n)), None)
        valor = _valor_do_campo(campos, campo) if campo else None
        if not valor:
            faltantes.append(alvo.group(0))
            return alvo.group(0)
        return str(valor)

    return _PLACEHOLDER.sub(_troca, texto), faltantes


def resolver_ou_erro(texto):
    """(texto_com_os_valores, erro) para quem vai escrever no ecra.

    Referencia que nao resolve tem de PARAR o gesto: escrever '{{cofre:gmail.senha}}'
    literalmente dentro de um campo de palavra-passe e um erro que passa despercebido
    (o campo aceita, o login e que falha depois, a dizer outra coisa).
    """
    resolvido, faltantes = resolver(texto)
    if faltantes:
        nomes = ", ".join(sorted(set(faltantes)))
        return resolvido, (
            f"o cofre nao tem {nomes} - veja o que existe com tool_gerenciar_cofre(acao='listar'). "
            "O campo NAO foi preenchido com a referencia em branco"
        )
    return resolvido, ""


def tem_placeholders(texto):
    return bool(texto) and "{{" in texto and bool(_PLACEHOLDER.search(texto))
