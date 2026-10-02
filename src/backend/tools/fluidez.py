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


def _porto_em_falta():
    portos = ", ".join(str(item) for item in cdp.PORTAS_CANDIDATAS)
    return (
        f"ERRO: nenhuma app responde nos portos de depuracao {portos}. Numa janela WebView2 "
        "(Tauri) o porto abre-se com '--remote-debugging-port=<porto>' nos argumentos do browser "
        "(ou pela variavel WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS); no Edge e no Chrome e o mesmo "
        "argumento na linha de comando."
    )


@register(
    "tool_medir_fluidez",
    "Mede o RITMO DE DESENHO (fps, intervalo medio, mediana, p95 e quadros acima de 32 ms) de uma "
    "app Chromium - janela Tauri/WebView2, Electron, Edge ou Chrome - de fora dela, pela porta de "
    "depuracao (CDP) que a app abre ao arrancar com '--remote-debugging-port=N'. E o caminho para "
    "medir a fluidez de uma janela que NAO e do Axio, onde o tool_observar_preview nao chega. "
    "'porta' e onde a app escuta (0 procura nos portos habituais 9222, 9223, 9229 e 9333); 'alvo' "
    "escolhe a pagina quando a app expoe varias; 'js' corre uma expressao ANTES de medir - e assim "
    "que se mede um efeito a acontecer (ex: js=\"document.querySelector('#x').click()\"); "
    "'listar' mostra so o que a app expoe no porto, sem medir. A JANELA TEM DE ESTAR A VISTA: em "
    "segundo plano o Chromium para o requestAnimationFrame e a medicao nao arranca - nesse caso a "
    "ferramenta di-lo em vez de inventar um numero.",
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
            "desc": "Expressao a correr dentro da app ANTES de medir, para o efeito estar a acontecer (ex: clicar no botao que abre a seccao). Vazio so mede.",
            "padrao": "",
        },
        "depois": {
            "tipo": "STRING",
            "desc": "Expressao a correr DEPOIS de medir, para ler o estado que o efeito deixou (ex: a largura da caixa, o texto do aviso, a classe do body). E o que evita uma segunda chamada so para ver o resultado.",
            "padrao": "",
        },
        "listar": {
            "tipo": "BOOLEAN",
            "desc": "True mostra o que a app expoe no porto (paginas, titulos, enderecos) e nao mede nada.",
            "padrao": False,
        },
    },
)
def tool_medir_fluidez(porta=0, alvo="", durante=DURACAO_PADRAO, js="", listar=False, depois=""):
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
    emit_event("executing", function=f"A medir o ritmo de desenho por {total} ms")
    sessao = cdp.Sessao(pagina["webSocketDebuggerUrl"], espera=(total / 1000.0) + ESPERA_EXTRA)
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
        if js.strip():
            try:
                resultado = sessao.avaliar(js, esperar=False)
            except RuntimeError as falha:
                return f"ERRO: a expressao '{js[:120]}' rebentou dentro da app ({falha})."
            if resultado is not None:
                ecos.append(json.dumps(resultado, ensure_ascii=False, default=str))
            time.sleep(PAUSA_ANTES_DE_MEDIR)
        bruto = sessao.avaliar(_MEDICAO % total)
        if depois.strip():
            try:
                resposta = sessao.avaliar(depois, esperar=False)
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
        return f"ERRO: {falha}."
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
