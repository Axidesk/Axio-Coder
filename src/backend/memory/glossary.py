import os
import json

from src.backend.config import caminho_data
from src.backend.state import emit_event

def _glossary_path():
    return caminho_data("glossary.json")

def load_glossary():
    caminho = _glossary_path()
    if not os.path.exists(caminho):
        return {"termos": []}
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)
        if not isinstance(dados, dict) or "termos" not in dados:
            return {"termos": []}
        return dados
    except Exception:
        return {"termos": []}

def save_glossary(dados):
    caminho = _glossary_path()
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    return True

def _normalizar(texto):
    if texto is None:
        return ""
    return str(texto).strip().lower()

def _normalizar_lista(aliases):
    if aliases is None:
        return []
    if isinstance(aliases, str):
        raw = [a for a in aliases.split(",") if a.strip()]
    elif isinstance(aliases, (list, tuple)):
        raw = [str(a) for a in aliases]
    else:
        return []
    vistos = []
    for a in raw:
        a = a.strip()
        if a and a.lower() not in vistos:
            vistos.append(a.lower())
    return vistos

def _identificador_concreto(identificador):
    if not identificador or not str(identificador).strip():
        return False
    ident = str(identificador).strip()
    vagos = ("coisa", "jeito", "aquilo", "isso", "algum", "algo", "elemento", "item", "botao", "janela")
    if ident.lower() in vagos:
        return False
    return True

def tool_gerenciar_glossario(acao, termo=None, aliases=None, identificador=None, descricao=None, localizacao_arquivo=None, localizacao_linha=None):
    """Gerencia o glossario de termos leigos -> codigo com filtro critico + dedup.

    FILTRO CRITICO (aplicado no backend, deterministico):
      1. 'termo' e 'identificador' sao obrigatorios.
      2. 'identificador' precisa ser concreto (nao generico como 'coisa'/'jeito'/'botao').
      3. Dedup: se 'termo', algum alias ou o 'identificador' ja existir, atualiza a entrada
         existente em vez de duplicar.
    """
    emit_event("executing", function="Gerenciando glossario")
    dados = load_glossary()
    termos = dados.get("termos", []) if isinstance(dados, dict) else []

    if acao == "listar":
        if not termos:
            return "Glossario vazio."
        linhas = []
        for t in termos:
            aliases_str = ", ".join(t.get("aliases", []))
            loc = t.get("localizacao", {}) or {}
            arquivo = loc.get("arquivo", "")
            linha = loc.get("linha", "")
            onde = f" ({arquivo}:{linha})" if arquivo else ""
            linhas.append(f"- \"{t.get('termo', '')}\" [aliases: {aliases_str}] -> {t.get('identificador', '')}{onde}")
        return "GLOSSARIO ATUAL:\n" + "\n".join(linhas)

    if acao == "remover":
        termo_norm = _normalizar(termo)
        if not termo_norm:
            return "ERRO: informe o 'termo' a remover."
        novas = []
        removidos = 0
        for t in termos:
            t_norm = _normalizar(t.get("termo", ""))
            ident_norm = _normalizar(t.get("identificador", ""))
            if t_norm == termo_norm or ident_norm == termo_norm:
                removidos += 1
                continue
            novas.append(t)
        if removidos == 0:
            return "Nenhum termo encontrado para remover."
        save_glossary({"termos": novas})
        return f"REMOVIDO: {removidos} termo(s) removidos do glossario."

    if acao != "escrever":
        return "ERRO: acao deve ser 'listar', 'escrever' ou 'remover'."

    termo_limpo = str(termo).strip() if termo else ""
    identificador_limpo = str(identificador).strip() if identificador else ""

    if not termo_limpo:
        return "ERRO (FILTRO CRITICO): 'termo' e obrigatorio. Nao salvei nada."
    if not _identificador_concreto(identificador_limpo):
        return "ERRO (FILTRO CRITICO): 'identificador' vazio ou generico ('coisa', 'jeito', 'botao' etc.). Use o identificador real (ex: '#btn-editor', '#editor-host', nome de funcao/classe). Nao salvei nada."

    alias_lista = _normalizar_lista(aliases)
    termo_norm = _normalizar(termo_limpo)
    ident_norm = _normalizar(identificador_limpo)

    alvo = None
    for t in termos:
        t_norm = _normalizar(t.get("termo", ""))
        id_norm = _normalizar(t.get("identificador", ""))
        aliases_existentes = [_normalizar(a) for a in t.get("aliases", [])]
        if (t_norm == termo_norm or ident_norm == id_norm or ident_norm in aliases_existentes
                or termo_norm in aliases_existentes or termo_norm == id_norm):
            alvo = t
            break

    entrada = {
        "termo": termo_limpo,
        "aliases": alias_lista,
        "identificador": identificador_limpo,
        "descricao": str(descricao).strip() if descricao else "",
        "localizacao": {
            "arquivo": str(localizacao_arquivo).strip() if localizacao_arquivo else "",
            "linha": localizacao_linha if localizacao_linha is not None else "",
        },
    }

    if alvo is not None:
        id_alvo = _normalizar(alvo.get("identificador", ""))
        termo_alvo = _normalizar(alvo.get("termo", ""))
        if id_alvo == ident_norm and termo_alvo != termo_norm:
            aliases_atuais = [str(a).strip() for a in alvo.get("aliases", [])]
            lowers = [a.lower() for a in aliases_atuais]
            if termo_limpo.lower() not in lowers and termo_limpo.lower() != str(alvo.get("termo", "")).lower():
                aliases_atuais.append(termo_limpo)
            alvo["aliases"] = aliases_atuais
            if descricao:
                alvo["descricao"] = str(descricao).strip()
            if localizacao_arquivo or localizacao_linha is not None:
                alvo["localizacao"] = entrada["localizacao"]
            acao_feita = "SINONIMO ADICIONADO"
        else:
            alvo.update(entrada)
            acao_feita = "ATUALIZADO"
    else:
        termos.append(entrada)
        acao_feita = "ADICIONADO"

    save_glossary({"termos": termos})
    return f"GLOSSARIO {acao_feita}: \"{termo_limpo}\" -> {identificador_limpo} (total: {len(termos)} termos)."
