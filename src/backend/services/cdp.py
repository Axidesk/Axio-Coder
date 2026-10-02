"""Fala com uma app Chromium pela porta de depuracao dela, de fora.

Qualquer app que corra Chromium - Edge/Chrome, uma janela Electron, um WebView2
(Tauri, por exemplo) - abre o Chrome DevTools Protocol num porto local quando
arranca com `--remote-debugging-port=N`. Este modulo liga-se a esse porto, lista o
que a app expoe e corre JavaScript la dentro, que e o caminho para medir o que so
se ve de dentro (o ritmo de desenho, por exemplo) sem instrumentar a app.

A app NAO e nossa: o porto pode nao estar aberto (diz-se isso em vez de falhar em
silencio) e o desenho pode estar parado porque a janela esta em segundo plano -
o Chromium para o requestAnimationFrame em janelas escondidas, e nesse caso a
resposta nao chega: e o erro `SemResposta`, que diz exatamente isso.
"""

import json
import urllib.error
import urllib.request

import websocket

PORTAS_CANDIDATAS = (9222, 9223, 9229, 9333)
TIMEOUT_DA_LISTA = 0.5
ESPERA_PADRAO = 45.0


class SemResposta(RuntimeError):
    """A app aceitou a ligacao mas nao respondeu dentro do tempo dado."""


def _endereco_dos_alvos(porta):
    return f"http://127.0.0.1:{int(porta)}/json/list"


def alvos(porta):
    """As paginas que a app expoe nesse porto. Devolve (lista, motivo da falha)."""
    try:
        with urllib.request.urlopen(_endereco_dos_alvos(porta), timeout=TIMEOUT_DA_LISTA) as resposta:
            conteudo = json.loads(resposta.read().decode("utf-8", "replace"))
    except urllib.error.URLError as falha:
        return [], f"nada responde no porto {int(porta)} ({falha.reason})"
    except Exception as falha:
        return [], f"nada responde no porto {int(porta)} ({falha})"
    if not isinstance(conteudo, list):
        return [], f"o porto {int(porta)} respondeu num formato inesperado"
    paginas = [
        item
        for item in conteudo
        if item.get("type") == "page" and item.get("webSocketDebuggerUrl")
    ]
    if not paginas:
        return [], f"o porto {int(porta)} responde mas nao tem nenhuma pagina para medir"
    return paginas, ""


def descobrir_porta(candidatas=PORTAS_CANDIDATAS):
    """O primeiro porto de depuracao vivo, ou 0."""
    for porta in candidatas:
        paginas, _ = alvos(porta)
        if paginas:
            return porta
    return 0


def escolher(paginas, alvo):
    """A pagina que casa com 'alvo' (trecho do endereco ou do titulo), ou a primeira util."""
    procurado = (alvo or "").strip().lower()
    if not procurado:
        return _primeira_util(paginas)
    for pagina in paginas:
        if procurado in (pagina.get("url") or "").lower() or procurado in (pagina.get("title") or "").lower():
            return pagina
    return None


def _primeira_util(paginas):
    """A primeira pagina que nao seja uma tela interna do proprio browser.

    O browser abre alvos proprios (edge://sync-confirmation-dialog, chrome://...) e eles
    costumam vir ANTES da pagina que interessa: escolher as cegas mede a tela errada.
    """
    for pagina in paginas:
        url = (pagina.get("url") or "").lower()
        if url.startswith(("edge://", "chrome://", "about:", "devtools://", "chrome-untrusted://")):
            continue
        return pagina
    return paginas[0]


class Sessao:
    """Uma conversa com UMA pagina: manda metodo+params, devolve o resultado."""

    def __init__(self, endereco, espera=ESPERA_PADRAO):
        self.endereco = endereco
        self.espera = espera
        self._ws = None
        self._proximo = 0

    def abrir(self):
        # sem cabecalho Origin: o Chromium recusa a ligacao com 403 quando o Origin
        # que o cliente envia nao esta na lista branca dela. MEDIDO com o Edge 154.
        self._ws = websocket.create_connection(self.endereco, timeout=self.espera, suppress_origin=True)
        return self

    def falar(self, metodo, **params):
        if self._ws is None:
            raise RuntimeError("a sessao com a pagina nao esta aberta")
        self._proximo += 1
        meu = self._proximo
        try:
            self._ws.send(json.dumps({"id": meu, "method": metodo, "params": params}))
            while True:
                bruto = self._ws.recv()
                if not bruto:
                    raise RuntimeError("a app fechou a ligacao")
                recado = json.loads(bruto)
                if recado.get("id") != meu:
                    continue
                if recado.get("error"):
                    raise RuntimeError(
                        (recado.get("error") or {}).get("message") or "a app recusou o pedido"
                    )
                return recado.get("result") or {}
        except websocket.WebSocketTimeoutException as falha:
            raise SemResposta(f"sem resposta em {self.espera:.0f} s") from falha

    def avaliar(self, expressao, esperar=True):
        resposta = self.falar(
            "Runtime.evaluate",
            expression=expressao,
            awaitPromise=bool(esperar),
            returnByValue=True,
        )
        falha = resposta.get("exceptionDetails")
        if falha:
            descricao = (falha.get("exception") or {}).get("description") or falha.get("text")
            raise RuntimeError(descricao or "a expressao rebentou dentro da app")
        return (resposta.get("result") or {}).get("value")

    def fechar(self):
        if self._ws is None:
            return
        try:
            self._ws.close()
        except Exception:
            pass
        self._ws = None

    def __enter__(self):
        return self.abrir()

    def __exit__(self, *_):
        self.fechar()
