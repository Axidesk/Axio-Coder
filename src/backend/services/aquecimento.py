"""Aquecimento em segundo plano depois de o servidor atender: espera que a porta responda e so
entao corre a tarefa. Assim o que e pesado e adiavel nao compete com os imports nem com a
primeira pagina a carregar - a janela abre sem pagar por trabalho que ninguem pediu ainda.
"""
import socket
import threading
import time

_EM_CURSO = {}

_TETO_DA_ESPERA = 120.0
_PASSO_DA_SONDA = 0.2


def esperar_porta(porta, teto=_TETO_DA_ESPERA):
    """True quando alguem atende na porta, False quando o teto de espera se esgota."""
    limite = time.time() + teto
    while time.time() < limite:
        sonda = socket.socket()
        try:
            sonda.settimeout(_PASSO_DA_SONDA)
            sonda.connect(("127.0.0.1", porta))
            sonda.close()
            return True
        except OSError:
            sonda.close()
            time.sleep(_PASSO_DA_SONDA)
    return False


def depois_do_arranque(porta, tarefa, espera=0.0, nome="aquecimento"):
    """Corre a tarefa numa thread daemon, so depois de a porta responder e da espera pedida.
    Devolve a thread, ou None quando ja havia uma em curso com o mesmo nome (o arranque pode
    ser pedido duas vezes e a tarefa nao deve correr duas)."""
    if nome in _EM_CURSO and _EM_CURSO[nome].is_alive():
        return None

    def corrida():
        esperar_porta(porta)
        if espera:
            time.sleep(espera)
        try:
            tarefa()
        except Exception as erro:
            print(f"[{nome}] falhou: {type(erro).__name__}: {erro}")

    thread = threading.Thread(target=corrida, daemon=True, name=nome)
    _EM_CURSO[nome] = thread
    thread.start()
    return thread
