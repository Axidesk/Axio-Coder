"""Auditoria das rotas HTTP da app Flask.

O que faltava as outras auditorias: o `auditar_imports_py` ve imports, o
`auditar_estrutura` ve modularidade e dead code - nenhuma delas ve a aplicacao a
RESPONDER. Esta sobe a app NUM PROCESSO NOVO (codigo do disco, nao o que o Flask
ja tem em memoria) e faz GET nas rotas estaticas, reportando o status.

As rotas que escrevem (POST/PUT/DELETE), as que tem parametro na URL e a de
streaming continuo sao apenas LISTADAS, nunca invocadas: a auditoria nao pode
ter efeitos colaterais nem ficar presa num gerador infinito.
"""
import json
import os
import subprocess
import sys
import tempfile

from src.backend.services.file_service import resolver_caminho
from src.backend.state import estado, emit_event
from src.backend.tools.process import run_com_timeout
from src.backend.tools.registry import register

_ROTAS_STREAM = {"/api/stream"}
_TIMEOUT_GLOBAL = 120
_TIMEOUT_ROTA_MAX = 30

_SCRIPT = '''# -*- coding: utf-8 -*-
"""Gerado por tool_auditar_rotas. Sobe a app e mede as rotas; nao editar."""
import importlib
import json
import os
import sys
import threading

sys.path.insert(0, __PASTA__)
sys.path.insert(0, __BASE__)
os.chdir(__BASE__)

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

app_mod = importlib.import_module(__MODULO__)
flask_app = getattr(app_mod, "app", None)
if flask_app is None:
    print("__AXIO__" + json.dumps({"erro": "o modulo '%s' nao expoe a variavel 'app'" % __MODULO__}))
    sys.exit(0)

cliente = flask_app.test_client()
STREAM = set(__STREAM__)
LIMITE = __LIMITE__


def testar(regra, guarda):
    def correr():
        try:
            resp = cliente.get(regra)
            guarda["status"] = resp.status_code
            if resp.status_code >= 400:
                guarda["detalhe"] = resp.get_data(as_text=True)[:200].replace("\\n", " ")
        except Exception as e:
            guarda["excecao"] = "%s: %s" % (type(e).__name__, e)
    t = threading.Thread(target=correr, daemon=True)
    t.start()
    t.join(LIMITE)
    return not t.is_alive()


rotas = []
for regra in sorted(flask_app.url_map.iter_rules(), key=lambda r: r.rule):
    metodos = sorted(set(regra.methods) - {"HEAD", "OPTIONS"})
    item = {"regra": regra.rule, "metodos": metodos, "endpoint": regra.endpoint}
    if regra.arguments:
        item["estado"] = "dinamica"
    elif regra.rule in STREAM:
        item["estado"] = "stream"
    elif "GET" not in metodos:
        item["estado"] = "nao-lida"
    else:
        guarda = {}
        if not testar(regra.rule, guarda):
            item["estado"] = "pendurada"
        elif "excecao" in guarda:
            item["estado"] = "excecao"
            item["detalhe"] = guarda["excecao"]
        else:
            if guarda["status"] < 400:
                item["estado"] = "ok"
            elif guarda["status"] < 500:
                item["estado"] = "recusa"
            else:
                item["estado"] = "falha"
            item["status"] = guarda["status"]
            item["detalhe"] = guarda.get("detalhe", "")
    rotas.append(item)

print("__AXIO__" + json.dumps({"rotas": rotas}, ensure_ascii=False))
'''

_MARCAS = {"ok": "OK", "falha": "FALHA", "recusa": "RECUSA", "excecao": "EXCECAO",
           "pendurada": "PENDUROU", "dinamica": "DINAMICA", "stream": "STREAM",
           "nao-lida": "ESCREVE"}


def _gerar_script(base, pasta_modulo, modulo, limite):
    return (_SCRIPT.replace("__PASTA__", repr(pasta_modulo))
                   .replace("__BASE__", repr(base))
                   .replace("__MODULO__", repr(modulo))
                   .replace("__STREAM__", repr(sorted(_ROTAS_STREAM)))
                   .replace("__LIMITE__", repr(limite)))


def _extrair(saida):
    for linha in reversed((saida or "").splitlines()):
        if linha.startswith("__AXIO__"):
            try:
                return json.loads(linha[len("__AXIO__"):])
            except json.JSONDecodeError:
                return None
    return None


def _rodar_script(script):
    fd, caminho = tempfile.mkstemp(prefix="axio_rotas_", suffix=".py")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(script)
        return run_com_timeout([sys.executable, caminho], timeout=_TIMEOUT_GLOBAL)
    finally:
        try:
            os.remove(caminho)
        except OSError:
            pass


def _relatorio(caminho_app, rotas, stderr):
    problemas = [r for r in rotas if r["estado"] in ("falha", "excecao", "pendurada")]
    recusas = [r for r in rotas if r["estado"] == "recusa"]
    testadas = [r for r in rotas if r["estado"] in ("ok", "falha", "excecao", "pendurada", "recusa")]
    listadas = [r for r in rotas if r["estado"] in ("dinamica", "stream", "nao-lida")]
    linhas = [f"AUDITORIA DAS ROTAS HTTP - {caminho_app}",
              f"  {len(rotas)} rota(s) registada(s) | invocadas por GET: {len(testadas)} "
              f"| so listadas: {len(listadas)}",
              ""]
    for r in rotas:
        detalhe = ""
        if r.get("status") is not None:
            detalhe = str(r["status"])
        elif r["estado"] == "dinamica":
            detalhe = "parametro na URL"
        elif r["estado"] == "stream":
            detalhe = "streaming continuo"
        elif r["estado"] == "nao-lida":
            detalhe = ",".join(r["metodos"])
        if r.get("detalhe"):
            detalhe = (detalhe + "  " + r["detalhe"]).strip()
        linhas.append(f"  {_MARCAS.get(r['estado'], '?'):8s} {r['regra']:44s} {detalhe}".rstrip())
    linhas.append("")
    linhas.append(f"VEREDITO: {len(testadas) - len(problemas) - len(recusas)} OK, "
                  f"{len(recusas)} recusaram sem parametros, {len(problemas)} com problema, "
                  f"{len(listadas)} so listada(s).")
    for r in problemas:
        linhas.append(f"  !! {r['regra']} ({r['estado']}) l.{r['endpoint']}: {r.get('detalhe', '')[:200]}")
    if stderr and stderr.strip():
        linhas.append("")
        linhas.append("stderr do processo novo: " + stderr.strip().replace("\n", " ")[:300])
    linhas.append("")
    linhas.append("POLITICA: so rotas GET sem parametro na URL sao invocadas. As que escrevem "
                  "(POST/PUT/DELETE), as com parametro e a de streaming ficam listadas sem "
                  "execucao. Um 4xx e a rota a recusar o pedido sem argumentos (nao e avaria); "
                  "um 5xx, uma excecao ou uma rota pendurada sao avaria.")
    return "\n".join(linhas)


@register(
    "tool_auditar_rotas",
    "Prova que a app Flask sobe e responde: corre-a NUM PROCESSO NOVO (codigo do disco, nao o que "
    "ja esta carregado no Flask) e faz GET em cada rota estatica, com o status de cada uma. Nao "
    "invoca rotas que escrevem (POST/PUT/DELETE), com parametro na URL nem a de streaming - essas "
    "apenas lista. Usa-a depois de mexer em routes/ ou no app.py, quando o auditar_imports_* e o "
    "auditar_estrutura ja passaram.",
    {
        'caminho_app': {"tipo": "STRING", "desc": "Ficheiro da app Flask (default app.py na raiz do projeto)", "padrao": "app.py"},
        'timeout': {"tipo": "INTEGER", "desc": "Segundos maximo por rota estatica (default 5)", "padrao": 5},
    },
    disponivel="sempre",
)
def tool_auditar_rotas(caminho_app="app.py", timeout=5):
    base = estado.get("pasta_raiz") or ""
    if not base:
        return "ERRO: nenhuma pasta de projeto selecionada."
    ficheiro, erro = resolver_caminho(caminho_app or "app.py")
    if erro:
        return erro
    if not os.path.isfile(ficheiro):
        return f"ERRO: nao encontrei '{caminho_app}' na pasta do projeto."
    try:
        limite = max(1, min(int(timeout or 5), _TIMEOUT_ROTA_MAX))
    except (TypeError, ValueError):
        limite = 5
    emit_event("executing", function=f"Auditando as rotas de {caminho_app}")
    script = _gerar_script(base, os.path.dirname(ficheiro),
                           os.path.splitext(os.path.basename(ficheiro))[0], limite)
    try:
        proc = _rodar_script(script)
    except subprocess.TimeoutExpired:
        return (f"ERRO: a auditoria passou de {_TIMEOUT_GLOBAL}s e foi abortada. O sinal habitual "
                "e uma rota presa a espera (streaming ou lock) - nada foi alterado.")
    dados = _extrair(proc.stdout)
    if dados is None:
        detalhe = (proc.stderr or "").strip()[:1200]
        return (f"ERRO: a app nao arrancou no processo novo (codigo {proc.returncode}).\n"
                f"{detalhe or '(sem stderr)'}")
    if "erro" in dados:
        return "ERRO: " + dados["erro"]
    return _relatorio(caminho_app, dados["rotas"], proc.stderr)
