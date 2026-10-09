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
INTERVALO_PADRAO = 50
INTERVALO_MINIMO = 10
INTERVALO_MAXIMO = 2000
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

_AMOSTRAGEM = """
new Promise((pronto) => {
    const ler = () => {
        try {
            return String(__EXPRESSAO__);
        } catch (erro) {
            return 'rebentou: ' + erro.message;
        }
    };
    const t0 = performance.now();
    const marcas = [];
    let anterior = null;
    const passo = () => {
        const valor = ler();
        if (valor !== anterior) {
            marcas.push([Math.round(performance.now() - t0), valor]);
            anterior = valor;
        }
        if (performance.now() - t0 < __DURACAO__) {
            setTimeout(passo, __PASSO__);
            return;
        }
        pronto(JSON.stringify(marcas));
    };
    passo();
})
"""


_CONSOLA_DA_PAGINA = """
(() => {
    if (!window.__axio_consola) {
        const lista = [];
        const guardar = (tipo, texto) => {
            lista.push({ tipo: tipo, texto: String(texto).slice(0, 300), aos_ms: Math.round(performance.now()) });
            if (lista.length > 200) lista.shift();
        };
        for (const nome of ['error', 'warn']) {
            const original = console[nome].bind(console);
            console[nome] = function () {
                const partes = Array.from(arguments).map((p) => (p && p.message ? p.message : p));
                guardar(nome, partes.join(' '));
                original.apply(null, arguments);
            };
        }
        window.addEventListener('error', (evento) => {
            const alvo = evento.target;
            if (alvo && alvo !== window && alvo.tagName) {
                guardar('recurso', alvo.tagName + ' ' + (alvo.src || alvo.href || ''));
                return;
            }
            guardar('erro', (evento.message || 'sem mensagem') + ' @ ' + (evento.filename || '?') + ':' + (evento.lineno || '?'));
        }, true);
        window.addEventListener('unhandledrejection', (evento) => {
            guardar('promessa', (evento.reason && evento.reason.message) || evento.reason);
        });
        window.__axio_consola = lista;
    }
    const lista = window.__axio_consola;
    return JSON.stringify({
        quantas: lista.length,
        nota: lista.length
            ? ''
            : 'nada apanhado desde que a ferramenta olhou para esta pagina pela primeira vez - a consola so guarda o que acontece depois disso',
        entradas: lista.slice(-40),
    });
})()
"""


_MAPA_DA_JANELA = """
(() => {
    const visivel = (el) => {
        const caixa = el.getBoundingClientRect();
        return caixa.width > 0 && caixa.height > 0 && getComputedStyle(el).visibility !== 'hidden';
    };
    const comoChamar = (el) => {
        if (el.id) return '#' + el.id;
        const partes = [el.tagName.toLowerCase()];
        if (el.className && typeof el.className === 'string') {
            const classe = el.className.trim().split(/\\s+/).slice(0, 2).join('.');
            if (classe) partes.push('.' + classe);
        }
        const pai = el.parentElement;
        if (pai && pai.id) partes.push(' (dentro de #' + pai.id + ')');
        return partes.join('');
    };
    const alvos = [...document.querySelectorAll(
        'button, a[href], input, select, textarea, [role="button"], [role="tab"], [role="checkbox"]'
    )].filter(visivel).slice(0, 60).map((el) => {
        const caixa = el.getBoundingClientRect();
        const rotulo = el.getAttribute('aria-label') || el.value || el.textContent || el.placeholder || '';
        const diz = el.getAttribute('aria-label') ? 'aria-label'
            : el.value ? 'valor'
            : String(el.textContent || '').trim() ? 'texto'
            : el.placeholder ? 'placeholder' : 'sem rotulo';
        const dados = [...el.attributes]
            .filter((a) => a.name.startsWith('data-'))
            .map((a) => a.name + '=' + a.value)
            .join(' ');
        return {
            seletor: comoChamar(el),
            o_que: String(rotulo).replace(/\\s+/g, ' ').trim().slice(0, 50),
            diz,
            dados,
            tipo: el.tagName.toLowerCase() + (el.type ? ':' + el.type : ''),
            ponto: Math.round(caixa.x + caixa.width / 2) + ',' + Math.round(caixa.y + caixa.height / 2),
            cabe_na_janela: caixa.y >= 0 && caixa.y + caixa.height <= innerHeight
        };
    });
    return JSON.stringify({ janela: innerWidth + 'x' + innerHeight, quantos: alvos.length, alvos }, null, 1);
})()
"""


_GEOMETRIA = """
(() => {
    const alvos = __ALVOS__;
    const ver = (seletor) => {
        let elemento = null;
        try {
            elemento = document.querySelector(seletor);
        } catch (erro) {
            return { seletor, erro: 'seletor invalido' };
        }
        if (!elemento) return { seletor, achado: false };
        const caixa = elemento.getBoundingClientRect();
        const estilo = getComputedStyle(elemento);
        return {
            seletor,
            achado: true,
            tag: elemento.tagName.toLowerCase(),
            texto: String(elemento.textContent || '').trim().split('\\n').join(' ').slice(0, 60),
            x: Math.round(caixa.left),
            y: Math.round(caixa.top),
            largura: Math.round(caixa.width),
            altura: Math.round(caixa.height),
            pintado: elemento.getClientRects().length > 0 && caixa.width > 0 && caixa.height > 0,
            fonte: estilo.fontSize,
            cor: estilo.color,
            fundo: estilo.backgroundColor
        };
    };
    return JSON.stringify(alvos.map(ver));
})()
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
    onde = f"em {onde_escolhi}" if onde_escolhi else "numa delas"
    return (
        f"ATENCAO: o porto tem {len(paginas)} paginas e nenhuma foi pinada, logo escolhi eu - "
        f"tudo o que esta chamada fez (inclusive o que a expressao possa ter mudado) foi {onde}. "
        f"As outras ao alcance: {nomes}{resto}. Se era a outra, repita com 'alvo' com um trecho "
        "do titulo: sem 'alvo' a escolha sai pela ordem da lista e muda de chamada para chamada."
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


def _porque_nao_veio(sessao, pagina, expressao):
    curta = " ".join(str(expressao).split())
    if len(curta) > 80:
        curta = curta[:77] + "..."
    if pagina is not None and not _responde_a_cdp(pagina):
        return (
            "nao veio nada, e a pagina nao responde nem a uma expressao trivial: o motor esta "
            "suspenso, congelado ou morto. Em segundo plano o Chromium congela paginas, e uma "
            "recarga a meio deixa-o assim - traga a janela para a frente (ou recarregue-a) e "
            "repita"
        )
    return f"nao veio nada em {sessao.espera:.0f} s (promessa por resolver? '{curta}')"


def _inspecionar(sessao, onde, js, depois, aviso="", pagina=None, seletores=""):
    linhas = [f"Em {onde}:"]
    if aviso.strip():
        linhas.append(aviso.strip())
    lidos = 0
    for expressao, rotulo in ((js, "O que a expressao devolveu"), (depois, "O estado")):
        if not expressao.strip():
            continue
        lidos += 1
        try:
            resultado = sessao.avaliar(expressao)
        except cdp.SemResposta:
            linhas.append(f"{rotulo}: {_porque_nao_veio(sessao, pagina, expressao)}")
        except RuntimeError as falha:
            linhas.append(f"{rotulo}: rebentou ({falha})")
        else:
            linhas.append(f"{rotulo}: {json.dumps(resultado, ensure_ascii=False, default=str)}")
    if seletores.strip():
        lidos += 1
        linhas.append(_geometria(sessao, seletores))
    if not lidos:
        linhas.append("Nao pediu nada para ler: passe 'js', 'depois' e/ou 'seletores'.")
    return "\n".join(linhas)


def _geometria(sessao, seletores):
    alvos = [linha.strip() for linha in str(seletores).splitlines() if linha.strip()]
    if not alvos:
        return ""
    guiao = _GEOMETRIA.replace("__ALVOS__", json.dumps(alvos, ensure_ascii=False))
    try:
        bruto = sessao.avaliar(guiao)
    except cdp.SemResposta:
        return "A geometria nao devolveu nada (promessa por resolver?)."
    except RuntimeError as falha:
        return f"A geometria rebentou ({falha})."
    try:
        itens = json.loads(bruto)
    except (TypeError, ValueError):
        return f"A geometria devolveu um formato inesperado ({str(bruto)[:200]})."

    linhas = [f"Geometria de {len(itens)} seletor(es):"]
    for item in itens:
        if item.get("erro"):
            linhas.append(f"  {item['seletor']}: {item['erro']}")
            continue
        if not item.get("achado"):
            linhas.append(f"  {item['seletor']}: nao existe na pagina")
            continue
        linhas.append(
            f"  {item['seletor']}: <{item['tag']}> x={item['x']} y={item['y']} "
            f"{item['largura']}x{item['altura']} fonte={item['fonte']} cor={item['cor']} "
            f"fundo={item['fundo']} | {item['texto']}"
        )
        if not item.get("pintado"):
            linhas.append(
                "    ATENCAO: ocupa 0x0 - esta oculto (display none, aba fechada ou fora do "
                "desenho), logo a medida nao vale"
            )
    return "\n".join(linhas)


def _amostrar(sessao, onde, expressao, durante, passo):
    guiao = (
        _AMOSTRAGEM.replace("__EXPRESSAO__", expressao)
        .replace("__DURACAO__", str(durante))
        .replace("__PASSO__", str(passo))
    )
    try:
        bruto = sessao.avaliar(guiao)
    except cdp.SemResposta:
        return (
            f"Em {onde}: a amostragem nao devolveu nada em {sessao.espera:.0f} s "
            "(promessa por resolver?)."
        )
    except RuntimeError as falha:
        return f"Em {onde}: a amostragem rebentou ({falha})."
    try:
        marcas = json.loads(bruto)
    except (TypeError, ValueError):
        return f"Em {onde}: a amostragem devolveu um formato inesperado ({str(bruto)[:200]})."
    linhas = [
        f"Em {onde}: {len(marcas)} mudanca(s) em {durante} ms, lendo a expressao a cada {passo} ms:"
    ]
    if not marcas:
        linhas.append("  (a expressao devolveu sempre o mesmo neste tempo)")
    for instante, valor in marcas:
        linhas.append(f"  {instante} ms: {valor}")
    return "\n".join(linhas)


_PRINT_DO_ALVO = """
(() => {
    const alvo = document.querySelector(%s);
    if (!alvo) return '';
    const caixa = alvo.getBoundingClientRect();
    return JSON.stringify({
        x: caixa.left + window.scrollX,
        y: caixa.top + window.scrollY,
        width: caixa.width,
        height: caixa.height
    });
})()
"""


def _recorte_pedido(sessao, pedido):
    texto = pedido.strip()
    if texto.lower() in ("tudo", "ecra", "tela"):
        return None
    partes = texto.split(",")
    if len(partes) == 4:
        try:
            x, y, largura, altura = (float(valor) for valor in partes)
        except ValueError:
            raise ValueError(
                "a regiao tem de ser 'x,y,largura,altura' em numeros, um seletor CSS ou 'tudo'"
            )
        if largura < 1 or altura < 1:
            raise ValueError("a regiao precisa de largura e altura maiores que zero")
        return {"x": x, "y": y, "width": largura, "height": altura, "scale": 1}
    try:
        caixa = sessao.avaliar(_PRINT_DO_ALVO % json.dumps(texto))
    except RuntimeError as falha:
        raise ValueError(f"o seletor '{texto}' nao serve nesta pagina ({falha})") from falha
    if not caixa:
        raise ValueError(f"nao encontrei nenhum elemento que responda a '{texto}' nesta pagina")
    recorte = json.loads(caixa)
    if recorte["width"] < 1 or recorte["height"] < 1:
        raise ValueError(
            f"'{texto}' esta escondido ou sem tamanho (0x0): so da para fotografar o que esta "
            "desenhado - abra a seccao que o esconde e repita"
        )
    return {**recorte, "scale": 1}


def _pedir_o_print(sessao, recorte):
    pedido = {"format": "png", "captureBeyondViewport": True}
    if recorte:
        pedido["clip"] = recorte
    try:
        return sessao.falar("Page.captureScreenshot", **pedido)
    except RuntimeError:
        sessao.falar("Page.enable")
        return sessao.falar("Page.captureScreenshot", **pedido)


def _aviso_do_quadro(sessao):
    try:
        estado = sessao.avaliar("({ visivel: document.visibilityState, foco: document.hasFocus() })")
    except (RuntimeError, cdp.SemResposta):
        return ""
    if not isinstance(estado, dict):
        return ""
    if estado.get("visivel") == "visible" and estado.get("foco"):
        return ""
    escondida = estado.get("visivel") != "visible"
    return (
        " ATENCAO: a janela nao esta a frente"
        + (" e o motor considera-a escondida" if escondida else "")
        + ": o motor pode devolver o ULTIMO quadro desenhado, logo esta imagem pode mostrar um "
        "estado antigo. Traga a janela para a frente e repita - ou leia o que o DOM devolve."
    )


def _print_da_pagina(sessao, onde, pedido, extra=""):
    extra = _aviso_do_quadro(sessao) + (f" {extra.strip()}" if extra.strip() else "")
    try:
        recorte = _recorte_pedido(sessao, pedido)
    except ValueError as falha:
        return f"ERRO: {falha}.{extra}"
    try:
        resposta = _pedir_o_print(sessao, recorte)
    except RuntimeError as falha:
        return f"ERRO: a pagina recusou o print ({falha}).{extra}"
    dados = resposta.get("data")
    if not dados:
        return f"ERRO: a pagina respondeu ao print sem imagem nenhuma.{extra}"
    medida = (
        f"{round(recorte['width'])}x{round(recorte['height'])} px"
        if recorte
        else "a janela inteira da pagina"
    )
    return {
        "texto": (
            (f"{extra.strip()} " if extra.strip() else "")
            + f"Print de {onde} ({medida}), tirado pelo proprio motor da pagina e nao pela janela: "
            "vem sem moldura, sem deslocamento e sem depender de a janela estar a vista. A imagem "
            "segue com esta resposta - olhe para ela antes de concluir."
        ),
        "imagem": {"base64": dados, "mime": "image/png", "rotulo": f"[Print da pagina: {onde}]"},
    }


def _antes_do_print(sessao, pagina, expressao):
    if not expressao.strip():
        return ""
    try:
        resultado = sessao.avaliar(expressao)
    except cdp.SemResposta:
        return f" Antes da fotografia: {_porque_nao_veio(sessao, pagina, expressao)}."
    except RuntimeError as falha:
        return (
            f" Antes da fotografia a expressao rebentou ({falha}): a imagem pode nao mostrar o "
            "efeito pedido."
        )
    return (
        " Antes da fotografia, o que a expressao devolveu: "
        f"{json.dumps(resultado, ensure_ascii=False, default=str)}"
    )


_TOKENS_DO_TEMA = """
(() => {
    const raiz = getComputedStyle(document.documentElement);
    const nomes = new Set();
    const recolher = (regras) => {
        for (const regra of regras) {
            if (regra.style && regra.selectorText && /^(:root|html|\\*)$/.test(regra.selectorText.trim())) {
                for (const nome of regra.style) if (nome.startsWith('--')) nomes.add(nome);
            }
            if (regra.cssRules) recolher(regra.cssRules);
        }
    };
    for (const folha of document.styleSheets) {
        try { recolher(folha.cssRules); } catch (erro) { }
    }
    const tokens = [...nomes].sort().map(nome => [nome, raiz.getPropertyValue(nome).trim()]);
    return JSON.stringify({ total: tokens.length, tokens });
})()
"""


_CLICAR_PELO_TEXTO = """
(() => {
    const procurado = __ALVO__;
    const limpo = (t) => (t || '').replace(/\\s+/g, ' ').trim().toLowerCase();
    const alvo = limpo(procurado);
    const folhas = Array.from(document.querySelectorAll('*')).filter(
        (e) => e.children.length === 0 && limpo(e.textContent) === alvo
    );
    if (!folhas.length) {
        const parecidos = Array.from(document.querySelectorAll('*'))
            .filter((e) => e.children.length === 0 && limpo(e.textContent).includes(alvo))
            .map((e) => limpo(e.textContent).slice(0, 40));
        return JSON.stringify({
            clicou: false,
            porque: 'nao achei um elemento com esse texto',
            parecidos: [...new Set(parecidos)].slice(0, 8),
        });
    }
    const elemento = folhas[0];
    const clicavel = (e) => e && e.matches && e.matches('button, a, [role=button], summary, label, [tabindex]');
    let onde = elemento;
    while (onde && onde !== document.body && !clicavel(onde)) {
        const pai = onde.parentElement;
        const irmao = pai ? Array.from(pai.children).find((x) => clicavel(x) && !x.contains(onde)) : null;
        if (irmao) {
            onde = irmao;
            break;
        }
        onde = pai;
    }
    if (!onde || onde === document.body || !clicavel(onde)) {
        const caixa = elemento.closest('li, tr, section, div');
        if (!caixa || !caixa.click) {
            return JSON.stringify({ clicou: false, porque: 'esse texto nao tem nada clicavel a volta' });
        }
        caixa.click();
        return JSON.stringify({ clicou: true, onde: caixa.tagName + '.' + String(caixa.className).split(' ')[0] });
    }
    onde.click();
    return JSON.stringify({
        clicou: true,
        onde: onde.tagName + (onde.className ? '.' + String(onde.className).split(' ')[0] : ''),
        agora: onde.getAttribute ? onde.getAttribute('aria-expanded') : null,
    });
})()
"""


def _clicar_pelo_texto(procurado):
    return _CLICAR_PELO_TEXTO.replace("__ALVO__", json.dumps(procurado, ensure_ascii=False))


def _atalho(expressao):
    texto = expressao.strip()
    if texto == "@mapa":
        return _MAPA_DA_JANELA
    if texto == "@consola":
        return _CONSOLA_DA_PAGINA
    if texto == "@tokens":
        return _TOKENS_DO_TEMA
    if texto.lower().startswith("@clicar:"):
        procurado = texto.split(":", 1)[1].strip()
        if procurado:
            return _clicar_pelo_texto(procurado)
    return expressao


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
    "para INSPECIONAR uma app de fora (um Tauri, um Electron, um Chrome) sem lhe roubar o foco. "
    "Com 'captura' FOTOGRAFA a pagina pelo motor dela e entrega a imagem (regiao em coordenadas "
    "da pagina, seletor CSS ou 'tudo'), e com 'js' a expressao corre ANTES da fotografia (abrir um "
    "grupo, mudar de aba, arrumar a cena) e o valor dela vem no texto. Com 'amostrar' SEGUE uma "
    "expressao ao "
    "longo do tempo e devolve so as mudancas, com o instante de cada uma - e o caminho para ver uma "
    "transicao, uma animacao ou um carregamento A ACONTECER, sem escrever um amostrador a mao. "
    "Com 'seletores' (um seletor CSS por linha) devolve a geometria e o estilo de cada um - x, y, "
    "largura, altura, fonte, cor, fundo - e AVISA quando o elemento ocupa 0x0, que e o caso do "
    "que esta oculto e cuja medida nao vale. Em 'js' valem ATALHOS prontos, para nao escrever "
    "codigo a mao: '@mapa' devolve o indice da pagina - cada botao, ligacao e campo, com o seletor, "
    "o que diz, DE ONDE vem esse rotulo ('diz': aria-label, texto, valor ou placeholder) e os "
    "atributos 'data-*' do elemento em 'dados' (ex: data-aba=site), que sao a forma estavel de o "
    "achar por codigo em vez de o procurar pelo texto; '@tokens' devolve os tokens de tema; "
    "'@consola' devolve os erros, avisos, recursos falhados e promessas rebentadas que a pagina "
    "deitou fora (tipo, texto e instante) desde a primeira vez que a ferramenta olhou para ela - a "
    "resposta para 'porque e que este botao nao faz nada' sem andar a adivinhar pelo DOM; e "
    "'@clicar:<texto>' clica no elemento que responde por esse texto, subindo do rotulo ao elemento "
    "clicavel; e '@consola' devolve os erros e avisos que a pagina deitou fora desde a primeira vez "
    "que esta ferramenta olhou para ela - o erro de JavaScript, o pedido ou a imagem que falharam e a "
    "promessa que rebentou sem ninguem a apanhar, com o tipo e o instante de cada um, que e o caminho "
    "para saber PORQUE um botao nao responde ou uma imagem nao aparece sem andar a adivinhar pelo DOM.",
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
            "desc": "Expressao a correr dentro da app ANTES de medir, para o efeito estar a acontecer (ex: clicar no botao que abre a seccao). Vazio so mede. Pode usar async/await: uma promessa devolvida e esperada e o que sai e o valor resolvido. Quatro atalhos: '@mapa' corre o indice da pagina - botoes, campos e ligacoes com o texto, o seletor e a coordenada; '@tokens' devolve as variaveis de tema da app (--cor: valor), sem ter de cacar o ficheiro do tema a mao; '@consola' devolve os erros, avisos, recursos falhados e promessas rebentadas que a pagina deitou fora (tipo, texto e instante) desde a primeira vez que a ferramenta olhou para ela - e a resposta a 'porque e que este botao nao faz nada' sem andar a adivinhar pelo DOM; e '@clicar:<texto>' clica no que responde por esse texto, subindo do rotulo ao botao ou ao irmao clicavel dele (o caso de um titulo de seccao cujo botao esta ao lado) - devolve onde clicou e, se a peca o tiver, o aria-expanded que ficou.",
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
        "captura": {
            "tipo": "STRING",
            "desc": "Fotografa a pagina de fora e entrega a imagem, pelo proprio motor dela: aceita 'x,y,largura,altura' em coordenadas DA PAGINA (nao da janela), um seletor CSS (fotografa o elemento, mesmo fora do ecra) ou 'tudo'. E o caminho para OLHAR para uma app Chromium de fora sem adivinhar o deslocamento da moldura da janela, sem depender de a janela estar a vista e sem as outras janelas por cima. Vazio nao fotografa nada.",
            "padrao": "",
        },
        "amostrar": {
            "tipo": "STRING",
            "desc": "Expressao a SEGUIR ao longo do tempo (ex: 'getComputedStyle(document.getElementById(\"x\")).opacity'). Devolve so as amostras em que o valor MUDOU, cada uma com o instante em ms - e o caminho para ver uma transicao, uma barra a encher ou um estado a virar acontecerem, numa chamada so. Funciona com 'js' (para disparar o efeito) e tanto serve com 'medir' ligado como desligado; substitui o amostrador escrito a mao que se repetia em cada medicao.",
            "padrao": "",
        },
        "intervalo": {
            "tipo": "INTEGER",
            "desc": f"De quantos em quantos milissegundos ler a expressao de 'amostrar' ({INTERVALO_MINIMO} a {INTERVALO_MAXIMO}).",
            "padrao": INTERVALO_PADRAO,
        },
        "seletores": {
            "tipo": "STRING",
            "desc": "Um seletor CSS por linha: devolve a geometria e o estilo real de cada um (x, y, largura, altura, fonte, cor, fundo) e AVISA quando o elemento ocupa 0x0 - oculto, numa aba fechada ou fora do desenho - porque nesse caso a medida nao vale. Substitui o getBoundingClientRect escrito a mao em cada medicao; corre com 'medir'=False e aceita vir junto de 'js' (para abrir o que se vai medir).",
            "padrao": "",
        },
    },
)
def tool_medir_fluidez(
    porta=0, alvo="", durante=DURACAO_PADRAO, js="", listar=False, depois="", medir=True,
    captura="", amostrar="", intervalo=INTERVALO_PADRAO, seletores=""
):
    js = _atalho(js)
    depois = _atalho(depois)
    amostrar = _atalho(amostrar)
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
    aviso_das_outras = "" if alvo.strip() else _aviso_das_outras_paginas(paginas, pagina)

    total = min(max(int(durante or DURACAO_PADRAO), DURACAO_MINIMA), DURACAO_MAXIMA)
    passo = min(max(int(intervalo or INTERVALO_PADRAO), INTERVALO_MINIMO), INTERVALO_MAXIMO)
    espera = (total / 1000.0) + ESPERA_EXTRA
    if js.strip():
        espera = max(espera, ESPERA_DA_EXPRESSAO)
    if captura.strip():
        emit_event("executing", function="A fotografar a pagina de fora")
    elif amostrar.strip():
        emit_event("executing", function=f"A seguir a pagina de fora por {total} ms")
    elif medir and not seletores.strip():
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
        if captura.strip():
            extra = _antes_do_print(sessao, pagina, js) + aviso_das_outras
            return _print_da_pagina(sessao, _onde_estou(pagina), captura, extra)
        if not amostrar.strip() and (not medir or seletores.strip()):
            return _inspecionar(
                sessao, _onde_estou(pagina), js, depois, aviso_das_outras, pagina, seletores
            )
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
        if amostrar.strip():
            linhas = [_amostrar(sessao, _onde_estou(pagina), amostrar, total, passo)]
            if ecos:
                linhas.insert(0, f"O que a expressao devolveu antes: {'; '.join(ecos)}")
            if aviso_das_outras:
                linhas.insert(0, aviso_das_outras.strip())
            return "\n".join(linhas)
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
            f"vista? Em segundo plano o Chromium nao desenha.\n{aviso_das_outras.strip()}"
        )
    linhas = [f"No porto {escolhido}, {_onde_estou(pagina)}:"]
    if aviso_das_outras:
        linhas.append(aviso_das_outras.strip())
    if ecos:
        linhas.append(f"O que a expressao devolveu: {'; '.join(ecos)}")
    if finais:
        linhas.append(f"O estado no fim da medicao: {'; '.join(finais)}")
    linhas.append(texto_dos_quadros(dados))
    return "\n".join(linhas)
