"""Despertador do agente: encerra a rodada e volta sozinho quando a condicao se cumprir.

Existe porque esperar por uma operacao longa (um download de 20 GB, um treino, um
build) obrigava a sondar o estado em chamadas repetidas - e cada chamada reenvia o
contexto inteiro. Aqui a intencao fica gravada em disco e a rodada retoma sozinha,
com a nota do agente como primeira mensagem.

Quatro gatilhos, um de cada vez: um instante, um intervalo, o fim de um processo ou o
aparecimento de um ficheiro. O agendamento sobrevive a fechar o Axio: ao arrancar, o
que estava armado continua a contar a partir do relogio, e o que ja venceu enquanto
o programa estava fechado dispara no primeiro ciclo.
"""

import ctypes
import json
import os
import threading
import time
from ctypes import wintypes
from datetime import datetime

from src.backend.config import caminho_data
from src.backend.services.persistencia import gravar_json_atomico
from src.backend.state import estado, emit_event

NOME_ARQUIVO = "despertador.json"
_INTERVALO = 2.0
_trava = threading.Lock()
_trava_turno = threading.Lock()
_vigia_ligada = False

_FORMATOS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M")
_PROCESSO_CONSULTA_LIMITADA = 0x1000
_PROCESSO_AINDA_ATIVO = 259


def _caminho():
    return caminho_data(NOME_ARQUIVO)


def _agora():
    return time.time()


def _ler():
    try:
        with open(_caminho(), "r", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
        return dados if isinstance(dados, dict) else {}
    except (OSError, ValueError):
        return {}


def _gravar(agendamento):
    try:
        gravar_json_atomico(_caminho(), agendamento or {})
    except Exception:
        pass


def _data_de(texto):
    """Le um instante escrito de varias formas. Devolve epoch ou None."""
    texto = (texto or "").strip()
    if not texto:
        return None
    if texto.isdigit():
        return float(texto)
    for formato in _FORMATOS:
        try:
            return datetime.strptime(texto, formato).timestamp()
        except ValueError:
            continue
    return None


def _duracao_de(texto):
    """Le '90' (minutos), '45s', '30m', '2h' ou '1h30'. Devolve segundos ou None."""
    texto = (texto or "").strip().lower().replace(" ", "")
    if not texto:
        return None
    if texto.isdigit():
        return int(texto) * 60
    total = 0
    numero = ""
    viu = False
    for caractere in texto:
        if caractere.isdigit():
            numero += caractere
            continue
        if not numero:
            return None
        valor = int(numero)
        numero = ""
        if caractere == "s":
            total += valor
        elif caractere == "m":
            total += valor * 60
        elif caractere == "h":
            total += valor * 3600
        elif caractere == "d":
            total += valor * 86400
        else:
            return None
        viu = True
    if numero:
        total += int(numero) * 60
        viu = True
    return total if viu else None


def _humano(segundos):
    segundos = max(0, int(segundos or 0))
    if segundos < 60:
        return f"{segundos} s"
    minutos = segundos // 60
    if minutos < 60:
        return f"{minutos} min"
    horas = minutos // 60
    resto = minutos % 60
    if horas < 24:
        return f"{horas} h {resto} min" if resto else f"{horas} h"
    dias = horas // 24
    resto_h = horas % 24
    return f"{dias} d {resto_h} h" if resto_h else f"{dias} d"


def _processo_vivo(pid):
    pid = str(pid or "").strip()
    if not pid:
        return False
    if pid in (estado.get("processos") or {}):
        return True
    try:
        numero = int(pid)
    except ValueError:
        return False
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(_PROCESSO_CONSULTA_LIMITADA, False, numero)
        if not handle:
            return False
        codigo = wintypes.DWORD()
        consultou = kernel32.GetExitCodeProcess(handle, ctypes.byref(codigo))
        kernel32.CloseHandle(handle)
        return bool(consultou) and codigo.value == _PROCESSO_AINDA_ATIVO
    except Exception:
        return False


def _alvo_de(gatilho):
    if gatilho.get("tipo") == "tempo":
        return float(gatilho.get("alvo_ts") or 0)
    return 0.0


def _descricao(gatilho):
    tipo = gatilho.get("tipo")
    if tipo == "tempo":
        restante = _alvo_de(gatilho) - _agora()
        when = datetime.fromtimestamp(_alvo_de(gatilho)).strftime("%H:%M")
        if restante <= 0:
            return "ja venceu"
        return f"daqui a {_humano(restante)} (as {when})"
    if tipo == "processo":
        return f"quando o processo {gatilho.get('pid')} terminar"
    if tipo == "ficheiro":
        return f"quando {gatilho.get('caminho')} aparecer"
    return "sem gatilho"


def _cumprido(gatilho):
    tipo = gatilho.get("tipo")
    if tipo == "tempo":
        return _agora() >= _alvo_de(gatilho)
    if tipo == "processo":
        return not _processo_vivo(gatilho.get("pid"))
    if tipo == "ficheiro":
        return os.path.exists(str(gatilho.get("caminho") or ""))
    return False


def retrato():
    """O que a interface e a ferramenta mostram sobre o agendamento."""
    agendamento = _ler()
    if not agendamento:
        return {"armado": False, "estado": "nenhum", "descricao": "", "falta": 0, "nota": ""}
    estado_atual = agendamento.get("estado") or "armado"
    gatilho = agendamento.get("gatilho") or {}
    falta = 0
    if estado_atual == "armado" and gatilho.get("tipo") == "tempo":
        falta = max(0, int(_alvo_de(gatilho) - _agora()))
    return {
        "armado": estado_atual == "armado",
        "estado": estado_atual,
        "id": agendamento.get("id", ""),
        "nota": agendamento.get("nota", ""),
        "descricao": _descricao(gatilho) if estado_atual == "armado" else "",
        "descricao_do_gatilho": _descricao(gatilho),
        "falta": falta,
        "falta_humano": _humano(falta) if falta else "",
        "quando": gatilho.get("quando", ""),
        "gatilho": gatilho,
        "disparado_em": agendamento.get("disparado_em", ""),
        "cancelado_em": agendamento.get("cancelado_em", ""),
        "motivo": agendamento.get("motivo", ""),
    }


def agendar(quando="", depois_de="", quando_processo="", quando_ficheiro="", nota=""):
    """Arma o despertador e devolve o retrato do que ficou marcado."""
    agora = _agora()
    quando = (quando or "").strip()
    depois_de = (depois_de or "").strip()
    quando_processo = str(quando_processo or "").strip()
    quando_ficheiro = (quando_ficheiro or "").strip()

    escolhidos = [nome for nome, valor in (
        ("quando", quando), ("depois_de", depois_de),
        ("quando_processo", quando_processo), ("quando_ficheiro", quando_ficheiro),
    ) if valor]
    if not escolhidos:
        return {"erro": "diga quando acordar: quando='HH:MM', depois_de='30m', quando_processo=<pid> ou quando_ficheiro=<caminho>"}
    if len(escolhidos) > 1:
        return {"erro": f"escolha UM gatilho, recebi {len(escolhidos)}: {', '.join(escolhidos)}"}

    if depois_de:
        segundos = _duracao_de(depois_de)
        if segundos is None or segundos <= 0:
            return {"erro": f"nao entendi o intervalo '{depois_de}'. Use '90' (minutos), '45s', '30m', '2h' ou '1h30'."}
        gatilho = {"tipo": "tempo", "alvo_ts": agora + segundos}
    elif quando:
        alvo = _data_de(quando)
        if alvo is None:
            return {"erro": f"nao entendi o instante '{quando}'. Use 'HH:MM' ou 'AAAA-MM-DD HH:MM'."}
        if len(quando) <= 5 and alvo < agora:
            alvo += 86400
        if alvo <= agora:
            return {"erro": "esse instante ja passou - escolha um no futuro"}
        gatilho = {"tipo": "tempo", "alvo_ts": alvo}
    elif quando_processo:
        gatilho = {"tipo": "processo", "pid": quando_processo}
    else:
        caminho = os.path.abspath(quando_ficheiro)
        gatilho = {"tipo": "ficheiro", "caminho": caminho}

    if gatilho.get("tipo") == "tempo":
        gatilho["quando"] = datetime.fromtimestamp(gatilho["alvo_ts"]).strftime("%Y-%m-%d %H:%M:%S")

    nota = (nota or "").strip() or "Acorda: o que estava a esperar ja aconteceu. Verifica e continua de onde parou."
    agendamento = {
        "id": "dsp_" + str(int(agora)),
        "criado": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "criado_ts": agora,
        "estado": "armado",
        "nota": nota,
        "gatilho": gatilho,
    }
    with _trava:
        _gravar(agendamento)
    _garantir_vigia()
    pronto = retrato()
    emit_event("despertador", estado="armado", descricao=pronto.get("descricao", ""),
               nota=nota, falta=pronto.get("falta", 0))
    return pronto


def cancelar(motivo=""):
    """Desarma. Devolve o que ficou."""
    with _trava:
        agendamento = _ler()
        if not agendamento:
            return {"cancelado": False, "motivo": "nao havia nada agendado"}
        agendamento["estado"] = "cancelado"
        agendamento["cancelado_em"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        agendamento["motivo"] = (motivo or "cancelado pelo utilizador").strip()
        _gravar(agendamento)
    emit_event("despertador", estado="cancelado", descricao="", nota="")
    return {"cancelado": True, "id": agendamento.get("id", ""), "motivo": agendamento["motivo"]}


def confirmar_entrega():
    """O frontend avisa que mostrou a nota; o agendamento deixa de ser pendente."""
    with _trava:
        agendamento = _ler()
        if agendamento.get("estado") == "disparado":
            agendamento["estado"] = "entregue"
            _gravar(agendamento)
    return {"ok": True}


def _arrancar_rodada(nota, turn_id, tentativa=0):
    from src.backend.routes.chat import _correr_loop  # import-local: evita ciclo routes.chat <-> services

    if not estado.get("pasta_raiz"):
        emit_event("status", message="Despertador: nenhuma pasta aberta - a nota fica guardada.")
        return False
    with _trava_turno:
        ocupado = bool(estado.get("turno_ocupado"))
        if not ocupado:
            estado["turno_ocupado"] = True
    if ocupado:
        if tentativa >= 300:
            emit_event("status", message="Despertador: o turno anterior nunca acabou.")
            return False
        time.sleep(2)
        return _arrancar_rodada(nota, turn_id, tentativa + 1)
    modelo = estado.get("ultimo_modelo") or {}
    try:
        threading.Thread(
            target=_correr_loop,
            args=(nota, "auto", [], bool(modelo.get("use_deepseek")),
                  turn_id, modelo.get("ai_model") or "gemini"),
            daemon=True,
            name="despertador-rodada",
        ).start()
    except Exception:
        estado["turno_ocupado"] = False
        raise
    return True


def _disparar(agendamento):
    agendamento["estado"] = "disparado"
    agendamento["disparado_em"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _trava:
        _gravar(agendamento)
    gatilho = agendamento.get("gatilho") or {}
    turn_id = str(int(time.time() * 1000))
    emit_event("despertador", estado="disparado", descricao=_descricao(gatilho),
               nota=agendamento.get("nota", ""), falta=0, proximo_turno=turn_id)
    _arrancar_rodada(agendamento.get("nota", ""), turn_id)


def _vigiar():
    while True:
        time.sleep(_INTERVALO)
        try:
            agendamento = _ler()
            if not agendamento or agendamento.get("estado") != "armado":
                continue
            if _cumprido(agendamento.get("gatilho") or {}):
                _disparar(agendamento)
        except Exception:
            continue


def _garantir_vigia():
    global _vigia_ligada
    if _vigia_ligada:
        return
    _vigia_ligada = True
    threading.Thread(target=_vigiar, daemon=True, name="despertador-vigia").start()


def iniciar_vigia():
    """Arranca a vigia no arranque do backend e dispara o que venceu com o programa fechado."""
    _garantir_vigia()
    agendamento = _ler()
    if agendamento.get("estado") == "armado" and _cumprido(agendamento.get("gatilho") or {}):
        _disparar(agendamento)
    return True
