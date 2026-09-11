import json
import os

from src.backend.config import caminho_data
from src.backend.services.settings import load_settings

LOCATION_DEFAULT = "global"
_gemini_client = None


def _caminho_credenciais_vertex():
    return caminho_data("vertex_credentials.json")

def _escrever_credenciais_vertex(vertex_json):
    if not isinstance(vertex_json, dict):
        return
    try:
        with open(_caminho_credenciais_vertex(), "w", encoding="utf-8") as f:
            json.dump(vertex_json, f, ensure_ascii=False)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = _caminho_credenciais_vertex()
    except OSError:
        pass

def get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        from google import genai

        s = load_settings()
        gemini = s.get("gemini") or {}
        mode = gemini.get("mode", "studio")

        if mode == "vertex":
            vertex_json = gemini.get("vertex_json")
            _escrever_credenciais_vertex(vertex_json)
            project_id = gemini.get("project_id") or os.getenv("GOOGLE_PROJECT_ID", "")
            location = gemini.get("location") or os.getenv("GOOGLE_LOCATION", LOCATION_DEFAULT)
            _gemini_client = genai.Client(vertexai=True, project=project_id, location=location)
        else:
            api_key = gemini.get("studio_api_key") or os.getenv("GOOGLE_API_KEY", "")
            _gemini_client = genai.Client(api_key=api_key)

    return _gemini_client

def reset_gemini_client():
    global _gemini_client
    _gemini_client = None
