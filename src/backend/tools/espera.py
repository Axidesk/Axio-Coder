"""Espera por uma confirmacao que depende do utilizador: sonda a evidencia, nao dorme.

Quando um servico interrompe o trabalho para pedir algo a quem esta do outro lado
- um segundo fator, um codigo no email, um consentimento no site - o agente tem
duas maneiras de errar: parar tudo a espera (o utilizador pode nao estar ali) ou
seguir a fingir que passou (e descobrir o engano tres passos depois).

Esta ferramenta e o meio termo. Traz a janela do preview para a frente para o
utilizador poder agir, avisa no ecra o que esta a esperar, e sonda em intervalos
a EVIDENCIA que o proprio trabalho define - o endereco avancou, o painel apareceu,
a saida do processo diz que autenticou. Quando a evidencia chega, devolve o que a
provou; quando o tempo acaba, devolve o que observou e manda seguir com o resto.

Dormir um tempo fixo seria pior por duas razoes: e cego (nao sabe se a confirmacao
chegou) e mentiroso (diria 'esperei' onde o certo e 'aconteceu' ou 'nao aconteceu').
"""

import json
import time

from src.backend.services.ponte_preview import pedir
from src.backend.state import emit_event, estado
from src.backend.tools.registry import register

INTERVALO = 2.0
SEGUNDOS_PADRAO = 180
SEGUNDOS_MAX = 600


def _registro_do_processo(pid):
    for chave, reg in (estado.get("processos") or {}).items():
        if str(chave) == str(pid):
            return reg
    return None


def _processo_vivo(reg):
    popen = (reg or {}).get("popen")
    if popen is None:
        return False
    try:
        return popen.poll() is None
    except Exception:
        return False


def _sonda_url(texto):
    alvo = str(texto).lower()

    def verificar():
        dados, erro = pedir("estado")
        if erro:
            return False, "", erro
        url = (dados or {}).get("url") or ""
        if alvo in url.lower():
            return True, f"o endereco chegou a {url}", ""
        return False, f"o endereco continua em {url or '(sem endereco)'}", ""

    return (f"o endereco conter '{texto}'", verificar)


def _sonda_seletor(seletor, sumir):
    alvo = json.dumps(str(seletor))
    expr = f"!document.querySelector({alvo})" if sumir else f"!!document.querySelector({alvo})"
    chegou = f"'{seletor}' desapareceu da pagina" if sumir else f"'{seletor}' apareceu na pagina"
    falta = f"'{seletor}' continua na pagina" if sumir else f"'{seletor}' ainda nao apareceu"

    def verificar():
        dados, erro = pedir("avaliar", js=expr)
        if erro:
            return False, "", erro
        if bool((dados or {}).get("resultado")):
            return True, chegou, ""
        return False, falta, ""

    return (f"'{seletor}' " + ("sair da pagina" if sumir else "aparecer na pagina"), verificar)


def _sonda_js(js):
    def verificar():
        dados, erro = pedir("avaliar", js=js)
        if erro:
            return False, "", erro
        valor = (dados or {}).get("resultado")
        if valor:
            return True, f"'{js[:80]}' devolveu {json.dumps(valor, default=str)[:80]}", ""
        return False, f"'{js[:80]}' ainda nao e verdadeira", ""

    return (f"'{js[:80]}' ficar verdadeira", verificar)


def _sonda_saida(pid, texto):
    alvo = str(texto).lower()

    def verificar():
        reg = _registro_do_processo(pid)
        if reg is None:
            return False, "", f"nao ha processo '{pid}' nesta sessao (veja tool_listar_processos)"
        linhas = reg.get("log") or []
        achada = next((linha for linha in reversed(linhas) if alvo in (linha or "").lower()), "")
        if achada:
            return True, f"o processo {pid} disse: {achada.strip()[:160]}", ""
        if not _processo_vivo(reg):
            return False, f"o processo {pid} terminou ({reg.get('status')}) sem dizer '{texto}'", ""
        return False, f"a saida do processo {pid} ainda nao tem '{texto}'", ""

    return (f"a saida do processo {pid} conter '{texto}'", verificar)


def _sonda_fim_do_processo(pid):
    def verificar():
        reg = _registro_do_processo(pid)
        if reg is None:
            return False, "", f"nao ha processo '{pid}' nesta sessao (veja tool_listar_processos)"
        if _processo_vivo(reg):
            return False, f"o processo {pid} ainda corre", ""
        return True, f"o processo {pid} terminou com estado '{reg.get('status')}'", ""

    return (f"o processo {pid} terminar", verificar)


def _sondas_do_pedido(pid, saida_contem, url_contem, seletor, sumir, js):
    sondas = []
    if url_contem:
        sondas.append(_sonda_url(url_contem))
    if seletor:
        sondas.append(_sonda_seletor(seletor, sumir))
    if js:
        sondas.append(_sonda_js(js))
    if pid and saida_contem:
        sondas.append(_sonda_saida(pid, saida_contem))
    elif pid:
        sondas.append(_sonda_fim_do_processo(pid))
    return sondas


def _teto(segundos_max):
    try:
        pedido = int(segundos_max or 0)
    except (TypeError, ValueError):
        pedido = 0
    if pedido <= 0:
        return float(SEGUNDOS_PADRAO)
    return float(min(pedido, SEGUNDOS_MAX))


@register(
    "tool_aguardar_confirmacao",
    "Espera, com teto de tempo, que uma CONFIRMACAO que depende do utilizador aconteca - e devolve a "
    "EVIDENCIA de que aconteceu. Use quando o servico interromper o trabalho a pedir algo a ele: segundo "
    "fator (2FA), codigo de confirmacao no email, consentimento/OAuth no site, ou um processo que fica a "
    "espera de autenticacao (ex: firebase login, gcloud auth login). A ferramenta TRAZ A JANELA DO PREVIEW "
    "PARA A FRENTE e avisa no ecra o que se espera, para o utilizador poder agir. Diga o que espera com uma "
    "condicao de evidencia: 'url_contem' (o endereco passa a conter isto - tipico de um login que avanca), "
    "'seletor' (um elemento aparece; com 'sumir'=true, desaparece - tipico do formulario de 2FA a fechar), "
    "'js' (uma expressao que fica verdadeira), ou 'pid' (+'saida_contem' para esperar um texto na saida, ou "
    "sozinho para esperar o processo terminar). Pode combinar condicoes: devolve a PRIMEIRA que chegar, "
    "dizendo qual foi. 'segundos_max' limita a espera (padrao 180s, maximo 600): escolha um valor curto "
    "quando o utilizador estiver a espera de algo que ja pediu. QUANDO O TEMPO ESGOTAR, nao insista nem "
    "repita a espera: siga com todo o trabalho que nao dependa desse passo e reporte no fim o que ficou "
    "pendente. NAO use para esperar um carregamento de pagina seu (para isso, recarregue e leia 'estado').",
    {
        "motivo": {
            "tipo": "STRING", "obrig": False, "padrao": "",
            "desc": "O que se espera, em palavras (ex: 'confirmacao de dois fatores no Google', 'o codigo de confirmacao no email'). Aparece no ecra e no retorno.",
        },
        "url_contem": {
            "tipo": "STRING", "obrig": False, "padrao": "",
            "desc": "Condicao: o endereco do preview passa a conter este texto (ex: 'dashboard', 'accounts.google.com/signin/oauth').",
        },
        "seletor": {
            "tipo": "STRING", "obrig": False, "padrao": "",
            "desc": "Condicao: um seletor CSS aparece na pagina (ex: '#painel'). Com 'sumir'=true espera que ele DESAPARECA (ex: o formulario de 2FA).",
        },
        "sumir": {
            "tipo": "BOOLEAN", "obrig": False, "padrao": False,
            "desc": "Inverte a condicao do 'seletor': espera que ele saia da pagina em vez de aparecer.",
        },
        "js": {
            "tipo": "STRING", "obrig": False, "padrao": "",
            "desc": "Condicao: uma expressao JavaScript na pagina que fica verdadeira (ex: 'document.querySelectorAll(\".erro\").length === 0').",
        },
        "pid": {
            "tipo": "STRING", "obrig": False, "padrao": "",
            "desc": "Condicao de PROCESSO: o pid devolvido por tool_executar_processo(modo='segundo_plano'). Sem 'saida_contem', espera o processo terminar.",
        },
        "saida_contem": {
            "tipo": "STRING", "obrig": False, "padrao": "",
            "desc": "Com 'pid': espera este texto na saida do processo (ex: 'Success! Logged in as', 'Authorized').",
        },
        "segundos_max": {
            "tipo": "INTEGER", "obrig": False, "padrao": 0,
            "desc": "Teto da espera em segundos. 0 = padrao (180). Maximo aceite: 600.",
        },
    },
    disponivel="edicao",
)
def tool_aguardar_confirmacao(motivo="", url_contem="", seletor="", sumir=False, js="", pid="", saida_contem="", segundos_max=0):
    sondas = _sondas_do_pedido(pid, saida_contem, url_contem, seletor, sumir, js)
    if not sondas:
        return (
            "ERRO: diga o que espera com 'url_contem', 'seletor', 'js' ou 'pid' - sem condicao nenhuma "
            "isto seria dormir as cegas, e uma espera cega nao sabe se a confirmacao chegou."
        )
    teto = _teto(segundos_max)
    if url_contem or seletor or js:
        pedir("mostrar")
    rotulo = (motivo or "").strip() or "uma confirmacao sua"
    emit_event("executing", function=f"A esperar {rotulo} (ate {teto:.0f}s) - confirme na janela")
    inicio = time.time()
    observado = ""
    primeira = True
    while True:
        erros = []
        for _, verificar in sondas:
            ok, texto, erro = verificar()
            if erro:
                erros.append(erro)
                continue
            if ok:
                return (
                    f"CONFIRMADO em {time.time() - inicio:.0f}s: {texto}.\n"
                    f"A espera por {rotulo} acabou - siga o trabalho a partir deste ponto."
                )
            if texto:
                observado = texto
        if primeira and len(erros) == len(sondas):
            return "ERRO: nao consegui sondar nenhuma condicao - " + erros[0]
        decorrido = time.time() - inicio
        if decorrido >= teto:
            return (
                f"TEMPO ESGOTADO ({decorrido:.0f}s) a esperar {rotulo}: {observado or 'nenhum sinal'}.\n"
                "O passo NAO foi confirmado. NAO repita a espera: siga com todo o trabalho que nao dependa "
                "dele e diga no fim o que ficou pendente, nomeando o passo e onde ele parou."
            )
        primeira = False
        time.sleep(INTERVALO)
