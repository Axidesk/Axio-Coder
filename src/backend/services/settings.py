import json
import os

from src.backend.config import caminho_data

SETTINGS_PATH = caminho_data("settings.json")

DEFAULT_SETTINGS = {
    "terminal": {"shell": ""},
    "deepseek": {"api_key": "", "enabled": False},
    "gemini": {
        "mode": "studio",
        "studio_api_key": "",
        "vertex_json_name": "",
        "vertex_json": None,
        "project_id": "",
        "location": "global",
        "enabled": False,
    },
    "tavily": {"api_key": "", "enabled": False},
    "projeto": {"ultima_pasta": ""},
    "interface": {"zoom": 1},
}

def _deep_merge(base, extra):
    for chave, valor in (extra or {}).items():
        if isinstance(valor, dict) and isinstance(base.get(chave), dict):
            _deep_merge(base[chave], valor)
        else:
            base[chave] = valor
    return base

def load_settings():
    dados = json.loads(json.dumps(DEFAULT_SETTINGS))
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            persistido = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        persistido = {}
    _deep_merge(dados, persistido)
    return dados

def _gravar_settings(dados):
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    return dados

def atualizar_settings(parcial):
    """Merge parcial no disco SEM resetar os clientes de IA.

    Usar para preferencias que nao mexem em credenciais (ex: shell do
    terminal). Gravar pelo modulo de IA derrubaria os clientes a cada clique."""
    dados = load_settings()
    _deep_merge(dados, parcial or {})
    return _gravar_settings(dados)

def save_settings(dados):
    dados = _deep_merge(load_settings(), dados or {})

    gemini = dados.get("gemini") or {}
    vertex_json = gemini.get("vertex_json")
    if isinstance(vertex_json, dict):
        gemini["project_id"] = vertex_json.get("project_id") or gemini.get("project_id", "")
        if not gemini.get("vertex_json_name"):
            gemini["vertex_json_name"] = (gemini.get("project_id") or "conta_servico") + ".json"

    _gravar_settings(dados)

    from src.backend.ai.deepseek import reset_deepseek_client
    from src.backend.ai.gemini import reset_gemini_client
    reset_deepseek_client()
    reset_gemini_client()

    return dados
