"""Cliente da ponte HTTP que o processo principal do Electron abre para o preview.

A pagina do preview vive numa WebContentsView do processo principal, fora do
alcance do Flask. O main.js abre em 127.0.0.1 uma ponte autenticada por token e
passa o endereco ao backend por AXIO_PONTE_PORTA/AXIO_PONTE_TOKEN (injetado no
ambiente do Flask ao spawna-lo). Este modulo e o unico lugar que fala com ela:
as ferramentas do preview e as esperas olham para a MESMA janela, pelo mesmo
caminho, e sem isso cada uma teria a sua copia do protocolo para desalinhar.
"""

import http.client
import json
import os

TEMPO_DA_PONTE = 25.0
TETO_RESPOSTA = 12 * 1024 * 1024
SEM_PONTE = (
    "o preview nao esta ligado a este backend. A ponte entre o servidor e a janela nasce no"
    " arranque do Axio: feche e reabra o programa (Ctrl+Shift+B nao chega, porque nao refaz"
    " o processo principal)"
)


def pedir(acao, **params):
    """(resposta, erro) de um pedido a ponte aberta pelo processo principal do Electron.

    Devolve (None, motivo) em vez de levantar quando a ponte nao existe ou nao
    responde: sem janela nao ha gesto possivel, e quem chama tem de poder dizer
    isso ao utilizador em vez de morrer a meio.
    """
    porta = (os.environ.get("AXIO_PONTE_PORTA") or "").strip()
    if not porta:
        return None, SEM_PONTE
    corpo = json.dumps({"acao": acao, "params": params}, ensure_ascii=False).encode("utf-8")
    cabecalhos = {
        "Content-Type": "application/json; charset=utf-8",
        "Content-Length": str(len(corpo)),
        "X-Axio-Token": os.environ.get("AXIO_PONTE_TOKEN", ""),
    }
    conexao = None
    try:
        conexao = http.client.HTTPConnection("127.0.0.1", int(porta), timeout=TEMPO_DA_PONTE)
        conexao.request("POST", "/preview", body=corpo, headers=cabecalhos)
        resposta = conexao.getresponse()
        dados = resposta.read(TETO_RESPOSTA)
        if resposta.status != 200:
            corpo_erro = dados[:300].decode("utf-8", "replace")
            return None, f"a ponte do preview respondeu {resposta.status}: {corpo_erro}"
        return json.loads(dados.decode("utf-8")), None
    except Exception as exc:
        return None, f"nao foi possivel falar com a janela do Axio ({type(exc).__name__}: {exc})"
    finally:
        if conexao is not None:
            conexao.close()
