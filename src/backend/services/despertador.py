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
import re
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
_ultimo_ciclo = 0.0

_FORMATOS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M")
_PROCESSO_CONSULTA_LIMITADA = 0x1000
_PROCESSO_AINDA_ATIVO = 259
_ESPERA_MINIMA = 600
_NOVA_TENTATIVA = 15


class _FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]


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


def _numero_do_pid(pid):
    """O pid do sistema por tras do registo: a chave pode ser 'proc_7' e o numero vive no popen."""
    registo = (estado.get("processos") or {}).get(str(pid or "").strip())
    if registo is not None:
        real = getattr(registo.get("popen"), "pid", None)
        if real:
            return int(real)
    try:
        return int(str(pid or "").strip())
    except ValueError:
        return None


def _criacao_do_handle(handle):
    """Instante de criacao do processo (FILETIME). E a identidade: um pid reutilizado tem outro."""
    criacao, saida, kernel, utilizador = _FILETIME(), _FILETIME(), _FILETIME(), _FILETIME()
    try:
        if not ctypes.windll.kernel32.GetProcessTimes(
                handle, ctypes.byref(criacao), ctypes.byref(saida),
                ctypes.byref(kernel), ctypes.byref(utilizador)):
            return None
    except Exception:
        return None
    return (criacao.dwHighDateTime << 32) | criacao.dwLowDateTime


def _vivo_no_sistema(numero, nascimento=None):
    if not numero:
        return False
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(_PROCESSO_CONSULTA_LIMITADA, False, numero)
        if not handle:
            return False
        try:
            codigo = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(codigo)):
                return False
            if codigo.value != _PROCESSO_AINDA_ATIVO:
                return False
            if nascimento:
                criacao = _criacao_do_handle(handle)
                if criacao is None or criacao != int(nascimento):
                    return False
            return True
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return False


def _inicio_do_processo(pid):
    numero = _numero_do_pid(pid)
    if not numero:
        return None
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(_PROCESSO_CONSULTA_LIMITADA, False, numero)
        if not handle:
            return None
        try:
            return _criacao_do_handle(handle)
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return None


def _processo_vivo(pid, nascimento=None):
    """Estar no registo NAO e estar vivo, e o pid sozinho tambem nao basta: o processo que o tem agora pode ser outro."""
    registo = (estado.get("processos") or {}).get(str(pid or "").strip())
    if registo is not None:
        popen = registo.get("popen")
        if popen is not None:
            try:
                if popen.poll() is not None:
                    return False
            except Exception:
                return False
    return _vivo_no_sistema(_numero_do_pid(pid), nascimento)


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
        texto = f"quando o processo {gatilho.get('pid')} terminar"
        if gatilho.get("sinal"):
            texto += f" - ou ANTES disso, se aparecer '{gatilho['sinal']}' na saida"
        if gatilho.get("limite_ts"):
            texto += f" (no maximo {_humano(max(0, gatilho['limite_ts'] - _agora()))})"
        return texto
    if tipo == "ficheiro":
        texto = f"quando {gatilho.get('caminho')} aparecer"
        if gatilho.get("limite_ts"):
            texto += f" (no maximo {_humano(max(0, gatilho['limite_ts'] - _agora()))})"
        return texto
    return "sem gatilho"


def _log_do_processo(pid):
    """(linhas, situacao, tem_registo). Sem registo, a saida perdeu-se com a sessao anterior."""
    registo = (estado.get("processos") or {}).get(str(pid or "").strip())
    if not registo:
        return [], "", False
    situacao = str(registo.get("status") or "")
    if situacao in ("", "rodando"):
        popen = registo.get("popen")
        codigo = getattr(popen, "returncode", None) if popen is not None else None
        if codigo == 0:
            situacao = "ok"
        elif codigo is not None:
            situacao = "erro"
    return list(registo.get("log") or []), situacao, True


def _sinal_no_log(linhas, padrao):
    """A linha mais recente que casa com o padrao, ou '' se nenhuma casar."""
    if not padrao:
        return ""
    try:
        expressao = re.compile(padrao, re.IGNORECASE)
    except re.error:
        expressao = re.compile(re.escape(padrao), re.IGNORECASE)
    for linha in reversed(linhas[-400:]):
        texto = str(linha)
        if expressao.search(texto):
            return texto
    return ""


def _resultado_do_processo(linhas, situacao, tem_registo):
    rotulo = {
        "ok": "terminou SEM erro (codigo 0)",
        "erro": "terminou COM erro",
    }.get(situacao, "terminou (codigo desconhecido)")
    cauda = [str(linha) for linha in linhas[-6:]]
    if cauda:
        return rotulo + ". Ultimas linhas:\n" + "\n".join("  " + linha for linha in cauda)
    if tem_registo:
        return rotulo + ", sem nenhuma linha escrita na saida."
    return rotulo + " e a saida perdeu-se (o processo nao e desta sessao)."


def _verificar(gatilho):
    """Diz se e por que motivo e hora de acordar. motivo: condicao | sinal | prazo."""
    tipo = gatilho.get("tipo")
    teto = float(gatilho.get("limite_ts") or 0)
    if tipo == "tempo":
        if _agora() >= _alvo_de(gatilho):
            return {"acordou": True, "motivo": "condicao", "detalhe": "o instante marcado chegou"}
        return {"acordou": False}
    if tipo == "ficheiro":
        caminho = str(gatilho.get("caminho") or "")
        if os.path.exists(caminho):
            return {"acordou": True, "motivo": "condicao", "detalhe": caminho + " apareceu"}
        if teto and _agora() >= teto:
            return {"acordou": True, "motivo": "prazo", "detalhe": caminho + " AINDA nao apareceu"}
        return {"acordou": False}
    if tipo == "processo":
        pid = gatilho.get("pid")
        linhas, situacao, tem_registo = _log_do_processo(pid)
        achado = _sinal_no_log(linhas, gatilho.get("sinal"))
        vivo = _processo_vivo(pid, gatilho.get("nascimento"))
        if achado and vivo:
            return {"acordou": True, "motivo": "sinal", "detalhe": achado}
        if not vivo:
            return {"acordou": True, "motivo": "condicao",
                    "detalhe": _resultado_do_processo(linhas, situacao, tem_registo)}
        if teto and _agora() >= teto:
            return {"acordou": True, "motivo": "prazo", "detalhe": "o processo " + str(pid) + " ainda corre"}
        return {"acordou": False}
    return {"acordou": False}


def _nota_com_verdade(nota, veredito):
    """Junta a nota escrita ANTES ao que se passou de facto: acordar com a suposicao errada custa uma rodada."""
    motivo = (veredito or {}).get("motivo", "condicao")
    detalhe = str((veredito or {}).get("detalhe") or "").strip()
    if motivo == "sinal":
        cabeca = ("ACORDASTE MAIS CEDO: apareceu na saida do processo o sinal que pediste para vigiar, "
                  "e o processo AINDA CORRE. Nao esperes pelo fim: ve o que se passou e corrige.")
    elif motivo == "prazo":
        cabeca = ("O PRAZO ESGOTOU sem a condicao se cumprir. Nao repitas a mesma espera: "
                  "investiga porque nao aconteceu.")
    else:
        cabeca = "A CONDICAO DO ACORDAR CUMPRIU-SE."
    partes = [nota or "", "", "[O QUE ACONTECEU DE FACTO]", cabeca]
    if detalhe:
        partes.extend(["", detalhe])
    return "\n".join(partes).strip()


def retrato():
    """O que a interface e a ferramenta mostram sobre o agendamento."""
    _garantir_vigia()
    agendamento = _ler()
    if not agendamento:
        return {"armado": False, "estado": "nenhum", "descricao": "", "falta": 0, "nota": ""}
    estado_atual = agendamento.get("estado") or "armado"
    gatilho = agendamento.get("gatilho") or {}
    falta = 0
    if estado_atual == "armado":
        if gatilho.get("tipo") == "tempo":
            falta = max(0, int(_alvo_de(gatilho) - _agora()))
        elif gatilho.get("limite_ts"):
            falta = max(0, int(float(gatilho["limite_ts"]) - _agora()))
    criado = float(agendamento.get("criado_ts") or 0)
    decorrido = max(0, int(_agora() - criado)) if (criado and estado_atual in ("armado", "disparado")) else 0
    return {
        "armado": estado_atual == "armado",
        "estado": estado_atual,
        "id": agendamento.get("id", ""),
        "nota": agendamento.get("nota", ""),
        "descricao": _descricao(gatilho) if estado_atual == "armado" else "",
        "descricao_do_gatilho": _descricao(gatilho),
        "falta": falta,
        "falta_humano": _humano(falta) if falta else "",
        "decorrido": decorrido,
        "decorrido_humano": _humano(decorrido) if decorrido else "",
        "tipo": gatilho.get("tipo", ""),
        "rodada_iniciada": bool(agendamento.get("rodada_iniciada")),
        "quando": gatilho.get("quando", ""),
        "gatilho": gatilho,
        "disparado_em": agendamento.get("disparado_em", ""),
        "cancelado_em": agendamento.get("cancelado_em", ""),
        "motivo": agendamento.get("motivo", ""),
        "motivo_do_disparo": agendamento.get("motivo_do_disparo", ""),
        "detalhe_do_disparo": agendamento.get("detalhe_do_disparo", ""),
    }


def agendar(quando="", depois_de="", quando_processo="", quando_ficheiro="", nota="",
            sinal="", prazo=""):
    """Arma o despertador e devolve o retrato do que ficou marcado."""
    agora = _agora()
    quando = (quando or "").strip()
    depois_de = (depois_de or "").strip()
    quando_processo = str(quando_processo or "").strip()
    quando_ficheiro = (quando_ficheiro or "").strip()
    sinal = (sinal or "").strip()
    prazo = (prazo or "").strip()

    escolhidos = [nome for nome, valor in (
        ("quando", quando), ("depois_de", depois_de),
        ("quando_processo", quando_processo), ("quando_ficheiro", quando_ficheiro),
    ) if valor]
    if not escolhidos:
        return {"erro": "diga quando acordar: quando='HH:MM', depois_de='30m', quando_processo=<pid> ou quando_ficheiro=<caminho>"}
    if len(escolhidos) > 1:
        return {"erro": f"escolha UM gatilho, recebi {len(escolhidos)}: {', '.join(escolhidos)}"}
    if sinal and not quando_processo:
        return {"erro": "sinal vigia a saida de UM processo: diga tambem quando_processo=<pid>."}

    if depois_de:
        segundos = _duracao_de(depois_de)
        if segundos is None or segundos <= 0:
            return {"erro": f"nao entendi o intervalo '{depois_de}'. Use '90' (minutos), '45s', '30m', '2h' ou '1h30'."}
        if segundos < _ESPERA_MINIMA:
            return {"erro": (f"{_humano(segundos)} e curto demais para dormir: operacao curta (compilar, instalar, "
                             "rodar um teste) resolve-se NA MESMA RODADA, com tool_listar_processos ou "
                             "tool_executar_processo em modo 'aguardar'. O despertador e para operacoes longas - "
                             "30 min ou mais - e para EVENTOS DO MUNDO (esperar um email, ver um anuncio amanha). "
                             "Para o que esta a correr agora, arme em quando_processo=<pid>.")}
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
        nascimento = _inicio_do_processo(quando_processo)
        if nascimento:
            gatilho["nascimento"] = nascimento
    else:
        caminho = os.path.abspath(quando_ficheiro)
        gatilho = {"tipo": "ficheiro", "caminho": caminho}

    if prazo:
        segundos_de_prazo = _duracao_de(prazo)
        if segundos_de_prazo is None or segundos_de_prazo <= 0:
            return {"erro": f"nao entendi o prazo '{prazo}'. Use '45s', '30m', '6h'."}
        if gatilho.get("tipo") == "tempo":
            return {"erro": "prazo nao se aplica a um gatilho de tempo - esse instante ja e o teto."}
        gatilho["limite_ts"] = agora + segundos_de_prazo

    if sinal:
        gatilho["sinal"] = sinal

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
    if sinal and quando_processo not in (estado.get("processos") or {}):
        pronto["aviso"] = (
            f"o pid {quando_processo} nao esta entre os processos desta sessao: o fim continua a ser "
            "detetado, mas o 'sinal' nao tem saida para vigiar."
        )
    emit_event("despertador", estado="armado", descricao=pronto.get("descricao", ""),
               nota=nota, falta=pronto.get("falta", 0),
               decorrido=pronto.get("decorrido", 0), tipo=pronto.get("tipo", ""))
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
            if not agendamento.get("rodada_iniciada"):
                return {"ok": False, "motivo": "a rodada ainda nao arrancou - a nota continua a espera"}
            agendamento["estado"] = "entregue"
            _gravar(agendamento)
    return {"ok": True}


_rodada_a_caminho = False
_ultimo_aviso = 0.0


def _avisar(texto):
    global _ultimo_aviso
    agora = _agora()
    if agora - _ultimo_aviso < 60:
        return
    _ultimo_aviso = agora
    emit_event("status", message=texto)


def _arrancar_rodada(nota, turn_id, tentativa=0):
    from src.backend.routes.chat import _correr_loop  # import-local: evita ciclo routes.chat <-> services

    if not estado.get("pasta_raiz"):
        _avisar("Despertador: acordei, mas ainda nao ha pasta aberta - tento de novo em instantes.")
        return False
    with _trava_turno:
        ocupado = bool(estado.get("turno_ocupado"))
        if not ocupado:
            estado["turno_ocupado"] = True
    if ocupado:
        if tentativa >= 150:
            _avisar("Despertador: o turno anterior ainda esta a correr - tento de novo em instantes.")
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


def _gravar_tentativa(agendamento, iniciou):
    with _trava:
        atual = _ler()
        if atual.get("id") != agendamento.get("id"):
            return
        atual["rodada_iniciada"] = bool(iniciou)
        atual["ultima_tentativa"] = _agora()
        _gravar(atual)


def _correr_a_rodada(agendamento, nota, turn_id):
    global _rodada_a_caminho
    iniciou = False
    try:
        iniciou = _arrancar_rodada(nota, turn_id)
    except Exception:
        iniciou = False
    finally:
        try:
            _gravar_tentativa(agendamento, iniciou)
        finally:
            with _trava_turno:
                _rodada_a_caminho = False


def _tentar_rodada(agendamento, nota, turn_id):
    """Arranca a rodada FORA da vigia: um turno ocupado nao pode parar o relogio do despertador."""
    global _rodada_a_caminho
    with _trava_turno:
        if _rodada_a_caminho:
            return
        _rodada_a_caminho = True
    threading.Thread(target=_correr_a_rodada, args=(agendamento, nota, turn_id),
                     daemon=True, name="despertador-arranque").start()


def _retomar_pendente(agendamento):
    veredito = {
        "motivo": agendamento.get("motivo_do_disparo", "condicao"),
        "detalhe": agendamento.get("detalhe_do_disparo", ""),
    }
    nota = _nota_com_verdade(agendamento.get("nota", ""), veredito)
    turn_id = agendamento.get("turn_id") or str(int(time.time() * 1000))
    _tentar_rodada(agendamento, nota, turn_id)


def _disparar(agendamento, veredito=None):
    veredito = veredito or {}
    turn_id = str(int(time.time() * 1000))
    agendamento["estado"] = "disparado"
    agendamento["disparado_em"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    agendamento["motivo_do_disparo"] = veredito.get("motivo", "condicao")
    agendamento["detalhe_do_disparo"] = veredito.get("detalhe", "")
    agendamento["rodada_iniciada"] = False
    agendamento["ultima_tentativa"] = 0
    agendamento["turn_id"] = turn_id
    gatilho = agendamento.get("gatilho") or {}
    nota = _nota_com_verdade(agendamento.get("nota", ""), veredito)
    with _trava:
        _gravar(agendamento)
    detalhe = str(veredito.get("detalhe") or "").strip()
    descricao = detalhe.splitlines()[0] if detalhe else _descricao(gatilho)
    emit_event("despertador", estado="disparado", descricao=descricao,
               nota=nota, falta=0, decorrido=0, tipo=gatilho.get("tipo", ""),
               proximo_turno=turn_id)
    _tentar_rodada(agendamento, nota, turn_id)


def _vigiar():
    global _ultimo_ciclo
    while True:
        time.sleep(_INTERVALO)
        _ultimo_ciclo = _agora()
        try:
            agendamento = _ler()
            if not agendamento:
                continue
            situacao = agendamento.get("estado")
            if situacao == "armado":
                veredito = _verificar(agendamento.get("gatilho") or {})
                if veredito.get("acordou"):
                    _disparar(agendamento, veredito)
                continue
            if situacao == "disparado" and not agendamento.get("rodada_iniciada"):
                if _agora() - float(agendamento.get("ultima_tentativa") or 0) >= _NOVA_TENTATIVA:
                    _retomar_pendente(agendamento)
        except Exception:
            continue


def _garantir_vigia():
    """Sobe a vigia - e sobe OUTRA se a anterior parou de dar sinal: uma thread morta nao avisa."""
    global _vigia_ligada, _ultimo_ciclo
    if _vigia_ligada and (_agora() - _ultimo_ciclo) < 10:
        return
    _vigia_ligada = True
    _ultimo_ciclo = _agora()
    threading.Thread(target=_vigiar, daemon=True, name="despertador-vigia").start()


def iniciar_vigia():
    """Arranca a vigia no arranque do backend e resolve o que ficou pendente com o programa fechado."""
    _garantir_vigia()
    agendamento = _ler()
    situacao = agendamento.get("estado")
    if situacao == "armado":
        veredito = _verificar(agendamento.get("gatilho") or {})
        if veredito.get("acordou"):
            _disparar(agendamento, veredito)
    elif situacao == "disparado" and not agendamento.get("rodada_iniciada"):
        _retomar_pendente(agendamento)
    return True
