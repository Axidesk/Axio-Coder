import os
import shutil
import subprocess
import tempfile

from src.backend.builds import depurar
from src.backend.tools import builds as builds_tools
from src.backend.tools.registry import register


_CENARIOS = [
    {
        "nome": "cadeia",
        "texto": "erro viaja por uma cadeia de imports: c.py, depois b.py, depois a entrada a.py",
        "base": {
            "a.py": "from b import valor\n\nprint(valor())\n",
            "b.py": "from c import numero\n\ndef valor():\n    return numero()\n",
            "c.py": 'def numero():\n    return "dois\n',
        },
        "passos": [
            {"rotulo": "base (erro em c.py)",
             "espera": [("c.py", 2)]},
            {"rotulo": "corrigido o c.py",
             "muda": {"c.py": "def numero():\n    return 2\n",
                      "b.py": "from c import numero\n\ndef valor():\n    return numero(\n"},
             "espera": [("b.py", 4)]},
            {"rotulo": "corrigido o b.py",
             "muda": {"b.py": "from c import numero\n\ndef valor():\n    return numero()\n",
                      "a.py": "from b import valor\n\nprint(valor(\n"},
             "espera": [("a.py", 3)]},
        ],
    },
    {
        "nome": "irmaos",
        "texto": "dois modulos importados pelo mesmo programa, estragados os dois",
        "base": {
            "main.py": "import x\nimport y\n\nprint(x.a, y.b)\n",
            "x.py": 'a = "sem fechar\n',
            "y.py": 'b = "sem fechar\n',
        },
        "passos": [
            {"rotulo": "base (x.py primeiro)",
             "espera": [("x.py", 1)]},
            {"rotulo": "corrigido o x.py",
             "muda": {"x.py": 'a = "limpo"\n'},
             "espera": [("y.py", 1)]},
        ],
    },
    {
        "nome": "queda",
        "texto": "o programa corre e rebenta dentro de um modulo importado",
        "base": {
            "principal.py": "from calc import media\n\nprint(media([1, 0]))\n",
            "calc.py": "def media(v):\n    return v[0] / v[1]\n",
        },
        "passos": [
            {"rotulo": "divisao por zero no calc.py",
             "espera": [("calc.py", 2)]},
        ],
    },
    {
        "nome": "entrada",
        "texto": "o proprio ficheiro de arranque nao compila, com a biblioteca ao lado limpa",
        "base": {
            "turma.py": "from notas import calcular_media\n\nprint(calcular_media(7, 8)\n",
            "notas.py": "def calcular_media(a, b):\n    return (a + b) / 2\n",
        },
        "passos": [
            {"rotulo": "parêntese aberto na entrada",
             "espera": [("turma.py", 3)]},
        ],
    },
    {
        "nome": "inacessivel",
        "texto": "ficheiro estragado que o programa nunca alcanca: por desenho nao ha aviso",
        "base": {
            "main.py": "print('ok')\n",
            "solto.py": 'x = "sem fechar\n',
        },
        "passos": [
            {"rotulo": "programa corre limpo",
             "espera": []},
        ],
    },
]


def _escrever(pasta, ficheiros):
    for nome, texto in ficheiros.items():
        with open(os.path.join(pasta, nome), "w", encoding="utf-8") as ficheiro:
            ficheiro.write(texto)


def _capturar(avisos):
    def capturar(tipo, **campos):
        if tipo == "debug_stop":
            avisos.append((os.path.basename(campos.get("arquivo") or ""), int(campos.get("linha") or 0)))
    return capturar


def _guardar_estado():
    return (dict(depurar.SESSAO), dict(depurar._LEITURA["sobre"]), set(depurar._LEITURA["escritas"]))


def _repor_estado(guardado):
    sessao, sobre, escritas = guardado
    depurar.SESSAO.clear()
    depurar.SESSAO.update(sessao)
    depurar._LEITURA["sobre"] = sobre
    depurar._LEITURA["escritas"] = escritas


def _corrida(pasta, avisos):
    avisos.clear()
    script = depurar._entrada_do_projeto(pasta)
    if not script:
        return ""
    depurar.esquecer_sessao()
    depurar.guardar_sessao("auditoria-do-depurador", script)
    vigia = builds_tools._vigia_do_depurador("auditoria-do-depurador")
    processo = subprocess.Popen(depurar.comando_python(script, pasta), cwd=pasta,
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                errors="replace")
    try:
        saida, _ = processo.communicate(input="c\nq\n", timeout=30)
    except subprocess.TimeoutExpired:
        processo.kill()
        saida, _ = processo.communicate()
    for linha in (saida or "").splitlines():
        vigia(linha)
    return os.path.basename(script)


def _correr_cenario(caso, base, linhas, avisos):
    pasta = os.path.join(base, caso["nome"])
    os.makedirs(pasta, exist_ok=True)
    _escrever(pasta, caso["base"])
    linhas.append(f"\n{caso['nome']}: {caso['texto']}")
    falhas = 0
    for passo in caso["passos"]:
        _escrever(pasta, passo.get("muda") or {})
        entrada = _corrida(pasta, avisos)
        esperado = [tuple(item) for item in passo["espera"]]
        certo = list(avisos) == esperado
        falhas += 0 if certo else 1
        linhas.append(f"  {'OK    ' if certo else 'FALHOU'} {passo['rotulo']}: entrada {entrada or '-'}"
                      f" | apontou {avisos or 'nada'} | esperado {esperado or 'nada'}")
    return falhas


@register(
    "tool_auditar_depurador",
    "Prova o depurador de ponta a ponta com o pdb REAL, em pastas temporarias: monta erros "
    "conhecidos (sintaxe numa cadeia de imports, queda a correr dentro de um modulo, ficheiro de "
    "arranque que nao compila, ficheiro que o programa nao alcanca) e confirma, corrida a corrida, "
    "que ficheiro e linha foram apontados. Use depois de mexer no depurador, em vez de confiar na "
    "leitura do codigo. Nao abre cards nem mexe em nenhuma sessao de depuracao aberta.",
    {
        "cenario": {
            "tipo": "STRING",
            "desc": "Nome de um cenario para correr sozinho. Vazio corre todos.",
            "padrao": "",
        },
    },
)
def tool_auditar_depurador(cenario=""):
    escolhidos = [caso for caso in _CENARIOS if not cenario or caso["nome"] == cenario]
    if not escolhidos:
        return ("ERRO: nao ha cenario '"
                + cenario + "'. Ha: " + ", ".join(caso["nome"] for caso in _CENARIOS) + ".")
    guardado = _guardar_estado()
    salvos = (builds_tools.emit_event, builds_tools.registrar_linha_processo,
              builds_tools.parar_processo_reg)
    avisos = []
    builds_tools.emit_event = _capturar(avisos)
    builds_tools.registrar_linha_processo = lambda *_: None
    builds_tools.parar_processo_reg = lambda *_: None
    base = tempfile.mkdtemp(prefix="axio_auditoria_dep_")
    linhas = ["AUDITORIA DO DEPURADOR - pdb real, pastas temporarias, uma corrida por passo"]
    falhas = 0
    try:
        for caso in escolhidos:
            falhas += _correr_cenario(caso, base, linhas, avisos)
    finally:
        (builds_tools.emit_event, builds_tools.registrar_linha_processo,
         builds_tools.parar_processo_reg) = salvos
        _repor_estado(guardado)
        shutil.rmtree(base, ignore_errors=True)
    corridas = sum(len(caso["passos"]) for caso in escolhidos)
    linhas.append(f"\n{'TUDO CERTO' if not falhas else str(falhas) + ' FALHA(S)'} em {corridas} corrida(s).")
    return "\n".join(linhas)
