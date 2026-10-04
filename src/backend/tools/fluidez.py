"""Fluidez: mede o ritmo de desenho de uma app Chromium de fora, pela porta de depuracao dela."""

import json
import time

from src.backend.services import cdp
from src.backend.state import emit_event
from src.backend.tools.preview import texto_dos_quadros
from src.backend.tools.registry import register

DURACAO_PADRAO = 2500
DURACAO_MINIMA = 400
DURACAO_MAXIMA = 12000
ESPERA_EXTRA = 8.0
PAUSA_ANTES_DE_MEDIR = 0.15
ESPERA_DA_EXPRESSAO = 45.0

_MEDICAO = """
new Promise((pronto) => {
    const marcas = [];
    const passo = (agora) => {
        marcas.push(agora);
        if (agora - marcas[0] < %d) {
            requestAnimationFrame(passo);
            return;
        }
        const intervalos = [];
        for (let i = 1; i < marcas.length; i += 1) intervalos.push(marcas[i] - marcas[i - 1]);
        const ordenados = intervalos.slice().sort((a, b) => a - b);
        const arredondar = (valor) => Math.round(valor * 10) / 10;
        const em = (fatia) => ordenados[Math.min(ordenados.length - 1, Math.floor(ordenados.length * fatia))] || 0;
        const decorrido = marcas[marcas.length - 1] - marcas[0];
        const soma = ordenados.reduce((total, valor) => total + valor, 0);
        pronto(JSON.stringify({
            quadros: marcas.length,
            ms: Math.round(decorrido),
            fps: arredondar((marcas.length * 1000) / Math.max(decorrido, 1)),
            medio: arredondar(soma / Math.max(ordenados.length, 1)),
            mediano: arredondar(em(0.5)),
            p95: arredondar(em(0.95)),
            pior: arredondar(ordenados[ordenados.length - 1] || 0),
            longos: ordenados.filter((valor) => valor > 32).length
        }));
    };
    requestAnimationFrame(passo);
})
"""


def _texto_dos_alvos(porta, paginas):
    linhas = [f"Porto {porta}: {len(paginas)} pagina(s) ao alcance."]
    for indice, pagina in enumerate(paginas, start=1):
        linhas.append(f"  {indice}. {_onde_estou(pagina)}")
    return "\n".join(linhas)


def _onde_estou(pagina):
    titulo = (pagina.get("title") or "").strip() or "(sem titulo)"
    return f"{titulo} - {pagina.get('url') or ''}"


def _aviso_das_outras_paginas(paginas, escolhida=None):
    if len(paginas) < 2:
        return ""
    onde_escolhi = _onde_estou(escolhida) if escolhida else ""
    outras = [texto for texto in (_onde_estou(pagina) for pagina in paginas) if texto != onde_escolhi]
    if not outras:
        return ""
    nomes = "; ".join(outras[:4])
    resto = f" (+{len(outras) - 4})" if len(outras) > 4 else ""
    return (
        f" Este porto tem {len(paginas)} paginas. As outras ao alcance: {nomes}{resto}"
        " - para medir uma delas, passe 'alvo' com um trecho do titulo."
    )


def _responde_a_cdp(pagina, espera=5.0):
    try:
        teste = cdp.Sessao(pagina["webSocketDebuggerUrl"], espera=espera)
        teste.abrir()
    except Exception:
        return False
    try:
        teste.avaliar("1")
        return True
    except Exception:
        return False
    finally:
        teste.fechar()


def _aviso_de_navegacao(falha):
    texto = str(falha or "").lower()
    sinais = (
        "execution context was destroyed",
        "cannot find context",
        "navigated or closed",
        "target closed",
    )
    if not any(sinal in texto for sinal in sinais):
        return ""
    return (
        " A pagina navegou ou recarregou a meio: a ligacao antiga morreu com ela e o resultado "
        "perdeu-se. Nao e defeito da expressao - repita a medicao agora, que a pagina nova ja "
        "esta no ar."
    )


def _porto_em_falta():
    portos = ", ".join(str(item) for item in cdp.PORTAS_CANDIDATAS)
    return (
        f"ERRO: nenhuma app responde nos portos de depuracao {portos}. Numa janela WebView2 "
        "(Tauri) o porto abre-se com '--remote-debugging-port=<porto>' nos argumentos do browser "
        "(ou pela variavel WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS); no Edge e no Chrome e o mesmo "
        "argumento na linha de comando."
    )


def _inspecionar(sessao, onde, js, depois):
    linhas = [f"Em {onde}:"]
    for expressao, rotulo in ((js, "O que a expressao devolveu"), (depois, "O estado")):
        if not expressao.strip():
            continue
        try:
            resultado = sessao.avaliar(expressao)
        except cdp.SemResposta:
            linhas.append(f"{rotulo}: nao veio nada (promessa por resolver?)")
        except RuntimeError as falha:
            linhas.append(f"{rotulo}: rebentou ({falha})")
        else:
            linhas.append(f"{rotulo}: {json.dumps(resultado, ensure_ascii=False, default=str)}")
    if len(linhas) == 1:
        linhas.append("Nao pediu nada para ler: passe 'js' e/ou 'depois'.")
    return "\n".join(linhas)


@register(
    "tool_medir_fluidez",
    "Mede o RITMO DE DESENHO (fps, intervalo medio, mediana, p95 e quadros acima de 32 ms) de uma "
    "app Chromium - janela Tauri/WebView2, Electron, Edge ou Chrome - de fora dela, pela porta de "
    "depuracao (CDP) que a app abre ao arrancar com '--remote-debugging-port=N'. E o caminho para "
    "medir a fluidez de uma janela que NAO e do Axio, onde o tool_observar_preview nao chega. "
    "'porta' e onde a app escuta (0 procura nos portos habituais 9222, 9223, 9229 e 9333); 'alvo' "
    "escolhe a pagina quando a app expoe varias; 'js' corre uma expressao ANTES de medir - e assim "
    "que se mede um efeito a acontecer (ex: js=\"document.querySelector('#x').click()\"); "
    "'depois' corre uma expressao no fim da medicao e devolve o estado que ficou; uma promessa "
    "devolvida em 'js' ou em 'depois' e ESPERADA e o que sai e o valor resolvido. "
    "'listar' mostra so o que a app expoe no porto, sem medir. A JANELA TEM DE ESTAR A VISTA: em "
    "segundo plano o Chromium para o requestAnimationFrame e a medicao nao arranca - nesse caso a "
    "ferramenta di-lo em vez de inventar um numero. Com 'medir'=False nao ha contagem nenhuma: "
    "corre 'js' e 'depois' e devolve o que lerem, ate com a janela em segundo plano - e o caminho "
    "para INSPECIONAR uma app de fora (um Tauri, um Electron, um Chrome) sem lhe roubar o foco.",
    {
        "porta": {
            "tipo": "INTEGER",
            "desc": "Porto de depuracao da app (CDP). 0 procura nos portos habituais: 9222, 9223, 9229 e 9333 (o do painel do Tibia74).",
            "padrao": 0,
        },
        "alvo": {
            "tipo": "STRING",
            "desc": "Trecho do endereco ou do titulo que escolhe a pagina quando a app expoe varias; vazio usa a primeira.",
            "padrao": "",
        },
        "durante": {
            "tipo": "INTEGER",
            "desc": f"Quantos milissegundos medir ({DURACAO_MINIMA} a {DURACAO_MAXIMA}). Mais tempo, numero mais estavel.",
            "padrao": DURACAO_PADRAO,
        },
        "js": {
            "tipo": "STRING",
            "desc": "Expressao a correr dentro da app ANTES de medir, para o efeito estar a acontecer (ex: clicar no botao que abre a seccao). Vazio so mede. Pode usar async/await: uma promessa devolvida e esperada e o que sai e o valor resolvido.",
            "padrao": "",
        },
        "depois": {
            "tipo": "STRING",
            "desc": "Expressao a correr DEPOIS de medir, para ler o estado que o efeito deixou (ex: a largura da caixa, o texto do aviso, a classe do body). E o que evita uma segunda chamada so para ver o resultado. Uma promessa devolvida e esperada: da para perguntar a propria app (uma rota dela, o IPC dela) e sair a resposta ja resolvida.",
            "padrao": "",
        },
        "listar": {
            "tipo": "BOOLEAN",
            "desc": "True mostra o que a app expoe no porto (paginas, titulos, enderecos) e nao mede nada.",
            "padrao": False,
        },
        "medir": {
            "tipo": "BOOLEAN",
            "desc": "True (padrao) mede o ritmo de desenho. False conta zero quadros: corre 'js' e 'depois' e devolve o que lerem - para LER o estado de uma janela de fora sem a incomodar.",
            "padrao": True,
        },
    },
)
def tool_medir_fluidez(
    porta=0, alvo="", durante=DURACAO_PADRAO, js="", listar=False, depois="", medir=True
):
    escolhido = int(porta or 0)
    if not escolhido:
        escolhido = cdp.descobrir_porta()
        if not escolhido:
            return _porto_em_falta()
    paginas, motivo = cdp.alvos(escolhido)
    if not paginas:
        return f"ERRO: {motivo}."
    if listar:
        return _texto_dos_alvos(escolhido, paginas)
    pagina = cdp.escolher(paginas, alvo)
    if pagina is None:
        return (
            f"ERRO: nenhuma pagina do porto {escolhido} tem '{alvo}' no endereco ou no titulo.\n"
            + _texto_dos_alvos(escolhido, paginas)
        )

    total = min(max(int(durante or DURACAO_PADRAO), DURACAO_MINIMA), DURACAO_MAXIMA)
    espera = (total / 1000.0) + ESPERA_EXTRA
    if js.strip():
        espera = max(espera, ESPERA_DA_EXPRESSAO)
    if medir:
        emit_event("executing", function=f"A medir o ritmo de desenho por {total} ms")
    else:
        emit_event("executing", function="A ler o estado da janela")
    sessao = cdp.Sessao(pagina["webSocketDebuggerUrl"], espera=espera)
    try:
        sessao.abrir()
    except Exception as falha:
        texto = str(falha)
        dica = ""
        if "403" in texto or "remote-allow-origins" in texto:
            dica = (
                " A app recusou a ligacao pelo Origin: arranque-a com '--remote-allow-origins=*' "
                "nos argumentos do browser."
            )
        return f"ERRO: nao consegui abrir a ligacao com a pagina ({texto}).{dica}"

    ecos = []
    finais = []
    try:
        if not medir:
            return _inspecionar(sessao, _onde_estou(pagina), js, depois)
        if js.strip():
            try:
                resultado = sessao.avaliar(js)
            except cdp.SemResposta:
                if not _responde_a_cdp(pagina):
                    return (
                        f"ERRO: {_onde_estou(pagina)} aceitou a ligacao mas nao responde a nada, "
                        "nem a uma expressao trivial: o motor da pagina esta suspenso ou morreu "
                        "(uma recarga a meio deixa-o assim). Recarregue a janela da app e repete"
                        f".{_aviso_das_outras_paginas(paginas, pagina)}"
                    )
                return (
                    f"ERRO: a expressao a correr antes de medir nao devolveu nada em "
                    f"{sessao.espera:.0f} s, em {_onde_estou(pagina)} - se ela espera por uma "
                    "promessa (um fetch, um convite a app) que demora mais do que isso, parta-a "
                    "em passos."
                )
            except RuntimeError as falha:
                return (
                    f"ERRO: a expressao '{js[:120]}' rebentou dentro da app ({falha}) - correu em"
                    f" {_onde_estou(pagina)}.{_aviso_de_navegacao(falha)}"
                    f"{_aviso_das_outras_paginas(paginas, pagina)}"
                )
            if resultado is not None:
                ecos.append(json.dumps(resultado, ensure_ascii=False, default=str))
            time.sleep(PAUSA_ANTES_DE_MEDIR)
        bruto = sessao.avaliar(_MEDICAO % total)
        if depois.strip():
            try:
                resposta = sessao.avaliar(depois)
            except cdp.SemResposta:
                finais.append(
                    f"(nao devolveu nada em {sessao.espera:.0f} s - promessa por resolver?)"
                )
            except RuntimeError as falha:
                finais.append(f"(rebentou: {falha})")
            else:
                if resposta is not None:
                    finais.append(json.dumps(resposta, ensure_ascii=False, default=str))
    except cdp.SemResposta:
        return (
            f"ERRO: {_onde_estou(pagina)} aceitou a ligacao mas nao desenhou nada em "
            f"{total / 1000.0 + ESPERA_EXTRA:.0f} s. O Chromium para o requestAnimationFrame quando "
            "a janela esta tapada, minimizada ou em segundo plano: traz a janela para a frente e repete."
        )
    except RuntimeError as falha:
        return f"ERRO: {str(falha).strip().rstrip('.')}.{_aviso_de_navegacao(falha)}"
    finally:
        sessao.fechar()

    try:
        dados = json.loads(bruto)
    except (TypeError, ValueError):
        return f"ERRO: a app devolveu a medicao num formato inesperado ({str(bruto)[:200]})."
    if not int(dados.get("quadros") or 0):
        return (
            f"Nenhum quadro desenhado em {total} ms em {_onde_estou(pagina)}: a janela esta mesmo a "
            "vista? Em segundo plano o Chromium nao desenha."
        )
    linhas = [f"No porto {escolhido}, {_onde_estou(pagina)}:"]
    if ecos:
        linhas.append(f"O que a expressao devolveu: {'; '.join(ecos)}")
    if finais:
        linhas.append(f"O estado no fim da medicao: {'; '.join(finais)}")
    linhas.append(texto_dos_quadros(dados))
    return "\n".join(linhas)
