import base64
import json
import logging
import time
from threading import Lock

from src.backend.ai.gemini import get_gemini_client_estudio
from src.backend.state import emit_event

logging.getLogger("google.genai").setLevel(logging.ERROR)

MODELO_COMPUTADOR = "gemini-3.8-flash"
SCREEN_WIDTH = 1440
SCREEN_HEIGHT = 900
TURN_LIMIT_PADRAO = 8

_lock = Lock()

_agente = {
    "playwright": None,
    "browser": None,
    "context": None,
    "page": None,
    "interaction_id": None,
    "objetivo": None,
    "url_atual": "",
    "pendencia": None,
}


def _ferramenta_computador():
    return {
        "type": "computer_use",
        "environment": "browser",
        "enable_prompt_injection_detection": True,
    }


def _chamar_interacoes(entrada, previous_interaction_id=None, max_tentativas=3):
    cliente = get_gemini_client_estudio()
    ultimo_erro = None
    for tentativa in range(max_tentativas):
        try:
            kwargs = {
                "model": MODELO_COMPUTADOR,
                "input": entrada,
                "tools": [_ferramenta_computador()],
            }
            if previous_interaction_id:
                kwargs["previous_interaction_id"] = previous_interaction_id
            return cliente.interactions.create(**kwargs)
        except Exception as e:
            codigo = getattr(e, "status_code", None)
            permanente = codigo is not None and 400 <= codigo < 500 and codigo != 429
            if permanente:
                raise
            ultimo_erro = e
            if tentativa < max_tentativas - 1:
                time.sleep(2 ** (tentativa + 1))
    raise ultimo_erro


def _denormalizar_x(x):
    return int((x or 0) / 1000 * SCREEN_WIDTH)


def _denormalizar_y(y):
    return int((y or 0) / 1000 * SCREEN_HEIGHT)


def _executar_acao(page, fname, args):
    fname = (fname or "").lower()
    if fname in ("open_web_browser", "open_app", "take_screenshot"):
        return {"ok": True}

    if fname in ("click", "click_at"):
        page.mouse.click(_denormalizar_x(args.get("x")), _denormalizar_y(args.get("y")))
    elif fname == "double_click":
        page.mouse.dblclick(_denormalizar_x(args.get("x")), _denormalizar_y(args.get("y")))
    elif fname == "triple_click":
        x, y = _denormalizar_x(args.get("x")), _denormalizar_y(args.get("y"))
        for _ in range(3):
            page.mouse.click(x, y)
    elif fname == "middle_click":
        page.mouse.click(_denormalizar_x(args.get("x")), _denormalizar_y(args.get("y")), button="middle")
    elif fname == "right_click":
        page.mouse.click(_denormalizar_x(args.get("x")), _denormalizar_y(args.get("y")), button="right")
    elif fname == "mouse_down":
        page.mouse.move(_denormalizar_x(args.get("x")), _denormalizar_y(args.get("y")))
        page.mouse.down()
    elif fname == "mouse_up":
        page.mouse.move(_denormalizar_x(args.get("x")), _denormalizar_y(args.get("y")))
        page.mouse.up()
    elif fname in ("move", "hover_at"):
        page.mouse.move(_denormalizar_x(args.get("x")), _denormalizar_y(args.get("y")))
    elif fname == "long_press":
        page.mouse.move(_denormalizar_x(args.get("x")), _denormalizar_y(args.get("y")))
        page.mouse.down()
        time.sleep(args.get("seconds", 2))
        page.mouse.up()
    elif fname in ("type", "type_text_at"):
        texto = args.get("text", "")
        if args.get("x") is not None and args.get("y") is not None:
            page.mouse.click(_denormalizar_x(args.get("x")), _denormalizar_y(args.get("y")))
        if args.get("clear_before_typing", True):
            page.keyboard.press("Control+A")
            page.keyboard.press("Backspace")
        page.keyboard.type(texto)
        if args.get("press_enter"):
            page.keyboard.press("Enter")
    elif fname == "navigate":
        page.goto(args.get("url", ""))
    elif fname == "go_back":
        page.go_back()
    elif fname == "go_forward":
        page.go_forward()
    elif fname == "wait":
        time.sleep(args.get("seconds", 1))
    elif fname == "wait_5_seconds":
        time.sleep(5)
    elif fname == "press_key":
        page.keyboard.press(args.get("key", ""))
    elif fname == "key_down":
        page.keyboard.down(args.get("key", ""))
    elif fname == "key_up":
        page.keyboard.up(args.get("key", ""))
    elif fname in ("shortcut", "tecla de atalho"):
        keys = args.get("keys") or []
        if isinstance(keys, str):
            keys = [keys]
        page.keyboard.press("+".join(keys))
    elif fname == "key_combination":
        page.keyboard.press(args.get("keys", ""))
    elif fname == "drag_and_drop":
        sx = args.get("start_x") if args.get("start_x") is not None else args.get("x")
        sy = args.get("start_y") if args.get("start_y") is not None else args.get("y")
        ex = args.get("end_x") if args.get("end_x") is not None else args.get("destination_x")
        ey = args.get("end_y") if args.get("end_y") is not None else args.get("destination_y")
        page.mouse.move(_denormalizar_x(sx), _denormalizar_y(sy))
        page.mouse.down()
        page.mouse.move(_denormalizar_x(ex), _denormalizar_y(ey))
        page.mouse.up()
    elif fname == "scroll":
        page.mouse.move(_denormalizar_x(args.get("x")), _denormalizar_y(args.get("y")))
        magnitude = args.get("magnitude_in_pixels") or args.get("magnitude") or 300
        direction = args.get("direction", "down")
        dx = dy = 0
        if direction == "down":
            dy = magnitude
        elif direction == "up":
            dy = -magnitude
        elif direction == "right":
            dx = magnitude
        elif direction == "left":
            dx = -magnitude
        page.mouse.wheel(dx, dy)
    elif fname in ("scroll_document", "scroll_at"):
        if fname == "scroll_at":
            page.mouse.move(_denormalizar_x(args.get("x")), _denormalizar_y(args.get("y")))
        magnitude = args.get("magnitude", 800)
        direction = args.get("direction", "down")
        page.mouse.wheel(0, magnitude if direction == "down" else -magnitude)
    else:
        return {"ok": False, "error": f"funcao nao tratada: {fname}"}

    try:
        page.wait_for_load_state(timeout=5000)
    except Exception:
        pass
    return {"ok": True}


def _textos_da_interacao(interacao):
    textos = []
    for passo in getattr(interacao, "steps", []) or []:
        if getattr(passo, "type", None) == "model_output":
            for bloco in getattr(passo, "content", []) or []:
                if getattr(bloco, "type", None) == "text" and getattr(bloco, "text", None):
                    textos.append(bloco.text)
    return "\n".join(textos).strip()


def _encerrar(silencioso=False):
    try:
        if _agente.get("browser") is not None:
            _agente["browser"].close()
    except Exception:
        pass
    try:
        if _agente.get("playwright") is not None:
            _agente["playwright"].stop()
    except Exception:
        pass
    _agente.update({
        "playwright": None,
        "browser": None,
        "context": None,
        "page": None,
        "interaction_id": None,
        "objetivo": None,
        "url_atual": "",
        "pendencia": None,
    })
    return "" if silencioso else "Sessao de uso do computador encerrada."


def _rodar_loop(interacao):
    for turno in range(1, TURN_LIMIT_PADRAO + 1):
        page = _agente["page"]
        emit_event("status", message=f"Uso do computador: turno {turno}")

        chamadas = [
            passo for passo in getattr(interacao, "steps", []) or []
            if getattr(passo, "type", None) == "function_call"
        ]
        if not chamadas:
            textos = _textos_da_interacao(interacao)
            _encerrar(silencioso=True)
            return "Concluido: " + (textos or "tarefa finalizada.")

        resultados = []
        pendencia = None
        for call in chamadas:
            fname = call.name
            args = dict(call.arguments) if call.arguments else {}
            decisao = (args.get("safety_decision") or {})
            if decisao.get("decision") == "require_confirmation":
                pendencia = {"name": fname, "args": args, "call_id": getattr(call, "id", None)}
                break
            try:
                resultado = _executar_acao(page, fname, args)
            except Exception as e:
                resultado = {"error": str(e)}
            resultados.append((fname, getattr(call, "id", None), resultado))

        if pendencia is not None:
            _agente["pendencia"] = pendencia
            _agente["interaction_id"] = interacao.id
            explicacao = (pendencia["args"].get("safety_decision") or {}).get("explanation", "")
            return (
                "A ACAO REQUER CONFIRMACAO DO USUARIO.\n"
                f"Acao: {pendencia['name']}\n"
                f"Motivo: {explicacao or 'decisao de seguranca do modelo'}\n"
                "Pergunte ao usuario se ele autoriza. Se autorizar, chame tool_computador(acao='continuar', confirmar=True). "
                "Se recusar, chame tool_computador(acao='encerrar')."
            )

        screenshot = page.screenshot(type="png")
        respostas = []
        for fname, call_id, resultado in resultados:
            respostas.append({
                "type": "function_result",
                "name": fname,
                "call_id": call_id,
                "result": [
                    {"type": "text", "text": json.dumps({"url": page.url, **resultado})},
                    {"type": "image", "data": base64.b64encode(screenshot).decode("utf-8"), "mime_type": "image/png"},
                ],
            })

        interacao = _chamar_interacoes(respostas, previous_interaction_id=interacao.id)
        _agente["interaction_id"] = interacao.id
        _agente["url_atual"] = page.url

    _encerrar(silencioso=True)
    return f"Limite de {TURN_LIMIT_PADRAO} turnos atingido. Chame tool_computador(acao='executar') para continuar."


def _executar(objetivo, url_inicial):
    _encerrar(silencioso=True)
    get_gemini_client_estudio()
    from playwright.sync_api import sync_playwright

    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context(viewport={"width": SCREEN_WIDTH, "height": SCREEN_HEIGHT})
    page = context.new_page()

    _agente.update({
        "playwright": playwright,
        "browser": browser,
        "context": context,
        "page": page,
        "interaction_id": None,
        "objetivo": objetivo,
        "url_atual": "",
        "pendencia": None,
    })

    if url_inicial:
        page.goto(url_inicial)

    screenshot = page.screenshot(type="png")
    entrada = [
        {"type": "text", "text": objetivo},
        {"type": "image", "data": base64.b64encode(screenshot).decode("utf-8"), "mime_type": "image/png"},
    ]
    interacao = _chamar_interacoes(entrada)
    _agente["interaction_id"] = interacao.id
    _agente["url_atual"] = page.url
    return _rodar_loop(interacao)


def _continuar(confirmar=False):
    page = _agente.get("page")
    pendencia = _agente.get("pendencia")
    if page is None or pendencia is None or _agente.get("interaction_id") is None:
        return "Nenhuma acao pendente de confirmacao. Inicie com tool_computador(acao='executar')."
    if not confirmar:
        return "Confirmacao nao recebida. Para autorizar a acao pendente, use confirmar=True."

    fname = pendencia["name"]
    args = pendencia["args"]
    try:
        resultado = _executar_acao(page, fname, args)
    except Exception as e:
        resultado = {"error": str(e)}
    resultado["safety_acknowledgement"] = True

    screenshot = page.screenshot(type="png")
    respostas = [{
        "type": "function_result",
        "name": fname,
        "call_id": pendencia["call_id"],
        "result": [
            {"type": "text", "text": json.dumps({"url": page.url, **resultado})},
            {"type": "image", "data": base64.b64encode(screenshot).decode("utf-8"), "mime_type": "image/png"},
        ],
    }]
    _agente["pendencia"] = None
    interacao = _chamar_interacoes(respostas, previous_interaction_id=_agente["interaction_id"])
    _agente["interaction_id"] = interacao.id
    _agente["url_atual"] = page.url
    return _rodar_loop(interacao)


def executar_computador(objetivo, acao="executar", url_inicial="", confirmar=False):
    with _lock:
        try:
            if acao == "encerrar":
                return _encerrar()
            if acao == "continuar":
                return _continuar(confirmar=bool(confirmar))
            if not objetivo.strip():
                return "Forneca o 'objetivo' da tarefa de navegacao."
            return _executar(objetivo, url_inicial)
        except Exception as e:
            _encerrar(silencioso=True)
            return f"ERRO no uso do computador: {str(e)}"
