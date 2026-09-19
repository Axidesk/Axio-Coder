import os
import json
import time

from src.backend.state import estado, emit_event, caminho_estado_projeto
from src.backend.tools.registry import register

def _caminho_bootstrap():
    if not estado.get("pasta_raiz"):
        return None
    return caminho_estado_projeto("bootstrap.json")

@register(
    "tool_gerenciar_bootstrap",
    "Gerencia o estado de um bootstrap de projeto (Supabase/Firebase/serviço) para retomada segura. Use acao='gravar' para registrar progresso ou parar aguardando uma credencial, acao='ler' para retomar de onde parou e acao='limpar' ao concluir o bootstrap. Ao concluir definitivamente, chame gravar com concluido=true (ou acao='limpar') para que o estado pare de ser injetado.",
    {
        'acao': {"tipo": "STRING", "enum": ['ler', 'gravar', 'limpar'], "obrig": True, "padrao": "ler"},
        'servico': {"tipo": "STRING", "desc": 'Nome do serviço (ex: supabase, firebase, gcloud)', "padrao": ""},
        'etapa_atual': {"tipo": "STRING", "desc": 'Descrição da etapa atual em andamento', "padrao": ""},
        'etapa_concluida': {"tipo": "STRING", "desc": 'Etapa concluída para adicionar à lista acumulada', "padrao": ""},
        'aguardando': {"tipo": "STRING", "desc": 'O que está aguardando do usuário (ex: credencial/token)', "padrao": ""},
        'concluido': {"tipo": "BOOLEAN", "desc": 'Marque true quando o bootstrap estiver definitivamente concluído, para não ser mais injetado no contexto', "padrao": False},
    },
)
def tool_gerenciar_bootstrap(acao="ler", servico="", etapa_atual="", etapa_concluida="", aguardando="", silencioso=False, concluido=False):
    if not silencioso:
        emit_event("executing", function="Gerenciando bootstrap")
    caminho = _caminho_bootstrap()
    if not caminho:
        return "ERRO: nenhuma pasta de projeto selecionada."
    if acao == "limpar":
        try:
            if os.path.exists(caminho):
                os.remove(caminho)
            return "Estado de bootstrap limpo."
        except OSError as e:
            return f"ERRO ao limpar bootstrap: {e}"
    dados = {}
    existe = os.path.exists(caminho)
    if existe:
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                dados = json.load(f)
        except Exception:
            dados = {}
    if acao == "gravar":
        if not existe:
            emit_event("workspace_activate", motivo="bootstrap")
        if servico:
            dados["servico"] = servico
        if etapa_atual:
            dados["etapa_atual"] = etapa_atual
        if aguardando:
            dados["aguardando"] = aguardando
        if concluido:
            dados["concluido"] = True
        elif "concluido" in dados:
            dados.pop("concluido", None)
        concluidas = dados.setdefault("etapas_concluidas", [])
        if etapa_concluida and etapa_concluida not in concluidas:
            concluidas.append(etapa_concluida)
        dados["timestamp"] = str(int(time.time()))
        try:
            os.makedirs(os.path.dirname(caminho), exist_ok=True)
            with open(caminho, "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False, indent=2)
            return json.dumps(dados, ensure_ascii=False, indent=2)
        except OSError as e:
            return f"ERRO ao gravar bootstrap: {e}"
    if not dados:
        return "Nenhum estado de bootstrap em andamento (.axio/bootstrap.json não existe)."
    if dados.get("concluido"):
        return "Nenhum estado de bootstrap em andamento (concluído)."
    aguardando_val = str(dados.get("aguardando", "")).strip().lower()
    if aguardando_val and any(m in aguardando_val for m in ("conclu", "finaliz", "encerrad")):
        return "Nenhum estado de bootstrap em andamento (concluído)."
    ts = dados.get("timestamp")
    if ts:
        try:
            idade = time.time() - int(ts)
            if idade > 30 * 24 * 3600:
                return "Nenhum estado de bootstrap em andamento (expirado após 30 dias de inatividade)."
        except (TypeError, ValueError):
            pass
    return json.dumps(dados, ensure_ascii=False, indent=2)
