import os
import json
import re
import time

from src.backend.state import estado, caminho_estado_projeto
def _caminho_checkpoint():
    return caminho_estado_projeto("chats", "checkpoint.json")

CHECKPOINT_TTL_SEGUNDOS = 7 * 24 * 60 * 60  # 7 dias (sobrevive a restarts de fim de semana/feriado)

def carregar_checkpoint():
    """Lê e remove o checkpoint de continuidade (se existir e for recente). Retorna dict ou None."""
    if not estado["pasta_raiz"]:
        return None
    caminho = _caminho_checkpoint()
    if not os.path.exists(caminho):
        return None
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)
        # 1. Evita vazamento entre projetos: checkpoint só vale para a pasta onde foi gravado.
        pasta_origem = dados.get("pasta_raiz")
        if pasta_origem and pasta_origem != estado["pasta_raiz"]:
            return None
        # 2. Evita falso positivo: um checkpoint antigo (de outra tarefa/sessão)
        # não deve ser injetado quando o usuário disser "continue/continua" em frase normal.
        ts = int(dados.get("timestamp", 0) or 0)
        if ts and (time.time() - ts) > CHECKPOINT_TTL_SEGUNDOS:
            os.remove(caminho)
            return None
        os.remove(caminho)
        return dados
    except Exception as e:
        print(f"Erro ao ler checkpoint: {e}")
        return None

def salvar_checkpoint(prompt, use_deepseek, erro, ferramentas_usadas, historico_sessao):
    """Grava o ponto exato de parada quando um erro interrompe o loop."""
    if not estado["pasta_raiz"]:
        return
    try:
        pasta_chats = caminho_estado_projeto("chats")
        os.makedirs(pasta_chats, exist_ok=True)
        caminho = _caminho_checkpoint()

        ultimo_historico = []
        for content in historico_sessao[-8:]:
            textos = []
            for part in getattr(content, "parts", []):
                texto = getattr(part, "text", None)
                if texto:
                    textos.append(texto[:500])
            if textos:
                ultimo_historico.append({
                    "role": getattr(content, "role", "?"),
                    "texto": "\n".join(textos)
                })

        dados = {
            "prompt": prompt,
            "agente": "coder",
            "erro": str(erro),
            "ferramentas_usadas": ferramentas_usadas,
            "ultimo_historico": ultimo_historico,
            "pasta_raiz": estado["pasta_raiz"],
            "timestamp": str(int(time.time()))
        }
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Erro ao salvar checkpoint: {e}")

def formatar_checkpoint(dados):
    """Transforma o checkpoint em um bloco de texto para injetar no contexto."""
    if not dados:
        return ""
    linhas = [
        "Você foi interrompido por um erro antes de terminar a tarefa. Retome exatamente de onde parou.",
        f"- Tarefa original: {dados.get('prompt', '')}",
        f"- Agente: {dados.get('agente', '?')}",
    ]
    ferramentas = dados.get("ferramentas_usadas", [])
    if ferramentas:
        linhas.append("- Ferramentas já usadas:")
        for fer in ferramentas:
            linhas.append(f"    * {fer}")
    linhas.append(f"- Erro que interrompeu: {dados.get('erro', '?')}")
    historico = dados.get("ultimo_historico", [])
    if historico:
        linhas.append("- Últimas mensagens da sessão:")
        for h in historico:
            linhas.append(f"    * [{h.get('role', '?')}]: {h.get('texto', '')}")
    linhas.append("Não repita o que já foi feito. Continue a partir do próximo passo.")
    return "\n".join(linhas)

def pasta_session_logs():
    return caminho_estado_projeto("chats", "session_logs")

def caminho_checkpoint_state():
    """Caminho do arquivo que persiste o checkpoint restaurado atual (por projeto)."""
    pasta_logs = pasta_session_logs()
    if not pasta_logs:
        return ""
    return os.path.join(pasta_logs, "checkpoint_state.json")

def ts_de_arquivo_log(nome):
    try:
        return int(nome.replace("sessionlog_", "").replace(".json", ""))
    except ValueError:
        return 0

def ler_log_sessao(caminho):
    with open(caminho, "r", encoding="utf-8") as f:
        texto = f.read()
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        texto = re.sub(r'\\([^\x00-\x7F])', r'\1', texto)
        return json.loads(texto)

def prune_session_logs(pasta_logs, manter_dias=3):
    """Mantém apenas as sessões de log dos últimos N dias distintos (por data).

    Sessões que contêm tarefas salvas (salvo=True) são preservadas mesmo fora
    da janela de dias, para que um card salvo nunca seja sobrescrito/removido.
    """
    try:
        arquivos = [f for f in os.listdir(pasta_logs) if f.startswith("sessionlog_") and f.endswith(".json")]
    except OSError:
        return

    infos = []
    arquivos_com_salvos = set()
    for arq in arquivos:
        ts = ts_de_arquivo_log(arq)
        dia = ""
        caminho = os.path.join(pasta_logs, arq)
        try:
            dados = ler_log_sessao(caminho)
            dia = (dados.get("datetime") or "").split(" ")[0]
            if any(g.get("salvo") for g in dados.get("logs", [])):
                arquivos_com_salvos.add(arq)
        except Exception:
            dia = ""
        if not dia and ts:
            dia = time.strftime("%d/%m/%Y", time.localtime(ts / 1000))
        infos.append((dia, ts, arq))

    infos.sort(key=lambda x: x[1], reverse=True)

    # Descobre os N dias distintos mais recentes.
    dias_recentes = []
    for dia, ts, arq in infos:
        if dia and dia not in dias_recentes:
            dias_recentes.append(dia)
        if len(dias_recentes) >= manter_dias:
            break
    dias_recentes = set(dias_recentes)

    for dia, ts, arq in infos:
        if dia and dia in dias_recentes:
            continue
        if arq in arquivos_com_salvos:
            continue
        try:
            os.remove(os.path.join(pasta_logs, arq))
        except OSError:
            pass

def criar_sessao_vazia(pasta_raiz, session_id):
    """Cria o arquivo de log vazio da sessão para o card "em andamento" já
    aparecer no histórico assim que a sessão inicia (sem esperar a 1ª edição)."""
    try:
        pasta_logs = os.path.join(pasta_raiz, ".axio", "chats", "session_logs")
        os.makedirs(pasta_logs, exist_ok=True)
        caminho = os.path.join(pasta_logs, f"sessionlog_{session_id}.json")
        if os.path.exists(caminho):
            return
        ts = int(session_id)
        payload = {
            "timestamp": ts,
            "datetime": time.strftime("%d/%m/%Y %H:%M:%S", time.localtime(ts / 1000)),
            "summary": "",
            "logs": [],
            "snapshot": {},
        }
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except (OSError, ValueError) as e:
        print(f"Erro ao criar sessão vazia {session_id}: {e}")

def summary_de_logs(logs):
    """Gera um resumo simples a partir dos nomes de arquivos editados na sessão."""
    nomes = []
    for grupo in logs:
        for f in grupo.get("files", []):
            nome = f.get("name", "")
            if nome and nome not in nomes:
                nomes.append(nome)
    resumo = ", ".join(nomes[:3])
    return resumo[:160]

def _iter_snapshot_caminhos(pasta_raiz, snapshot):
    """Itera (rel, meta, caminho) de um snapshot, ignorando metas nao-dict."""
    for rel, meta in (snapshot or {}).items():
        if not isinstance(meta, dict):
            continue
        caminho = os.path.join(pasta_raiz, rel.replace("/", os.sep)) if pasta_raiz else rel.replace("/", os.sep)
        yield rel, meta, caminho

def reconciliar_snapshot_com_disco(snapshot):
    """Reconcilia um snapshot herdado com o estado real do disco.

    Ao abrir uma nova sessão, `arquivos_tocados` é zerado e as mudanças feitas
    manualmente fora do sistema (arquivos apagados/editados enquanto o programa
    estava fechado) não seriam detectadas — o checkpoint antigo "ressuscitaria"
    arquivos que não existem mais. Aqui cada caminho é conferido contra o disco:
    - inexistente -> `conteudo: None` (a restauração deve remover);
    - existente  -> relê o conteúdo atual (captura edições manuais).
    """
    pasta_raiz = estado.get("pasta_raiz", "")
    reconciliado = {}
    for rel, meta, caminho in _iter_snapshot_caminhos(pasta_raiz, snapshot):
        if not os.path.exists(caminho):
            novo = dict(meta)
            novo["conteudo"] = None
            reconciliado[rel] = novo
            continue
        try:
            with open(caminho, "r", encoding="utf-8") as f:
                novo = dict(meta)
                novo["conteudo"] = f.read()
                reconciliado[rel] = novo
        except (OSError, UnicodeDecodeError):
            reconciliado[rel] = meta
    return reconciliado

def marcar_delecoes_manuais(snapshot):
    """Marca `conteudo: None` para caminhos do snapshot que sumiram do disco.

    Complementa reconciliar_snapshot_com_disco: enquanto a interface está aberta,
    um arquivo herdado de sessão anterior pode ser apagado manualmente (fora do
    sistema). capturar_snapshot cobre apenas arquivos tocados NESTA sessão; aqui
    os herdados também são conferidos a cada save, checando apenas a existência
    (custo baixo), para não "ressuscitar" o arquivo na restauração.
    """
    pasta_raiz = estado.get("pasta_raiz", "")
    resultado = {}
    for rel, meta, caminho in _iter_snapshot_caminhos(pasta_raiz, snapshot):
        if not os.path.exists(caminho):
            novo = dict(meta)
            novo["conteudo"] = None
            resultado[rel] = novo
        else:
            resultado[rel] = meta
    return resultado

def snapshot_sessao_anterior(pasta_logs, ignorar_session_id):
    """Carrega o checkpoint final da sessão mais recente (exceto a atual) na pasta.

    Mantém o snapshot cumulativo entre sessões: arquivos editados numa sessão
    anterior continuam presentes no checkpoint das sessões seguintes, mesmo que
    não sejam editados novamente.
    """
    melhor_arq = None
    melhor_ts = -1
    try:
        arquivos = [f for f in os.listdir(pasta_logs) if f.startswith("sessionlog_") and f.endswith(".json")]
    except OSError:
        return {}
    ignorar = f"sessionlog_{ignorar_session_id}.json" if ignorar_session_id else ""
    for arq in arquivos:
        if arq == ignorar:
            continue
        ts = ts_de_arquivo_log(arq)
        if ts > melhor_ts:
            melhor_ts = ts
            melhor_arq = arq
    if not melhor_arq:
        return {}
    try:
        dados = ler_log_sessao(os.path.join(pasta_logs, melhor_arq))
        return dados.get("snapshot") or {}
    except Exception:
        return {}

def primeira_aparicao_por_arquivo(pasta_logs):
    """Mapeia cada arquivo rastreado ao menor timestamp de log em que ele aparece.

    Substitui a inferência por diferença de conjuntos: um arquivo só é considerado
    "criado depois do ponto" quando a sua primeira aparição registrada é posterior
    ao timestamp do checkpoint restaurado. Isso elimina falsos positivos causados
    por snapshots incompletos (herança quebrada entre sessões).
    """
    aparicao = {}
    try:
        arquivos = [f for f in os.listdir(pasta_logs) if f.startswith("sessionlog_") and f.endswith(".json")]
    except OSError:
        return aparicao
    for arq in arquivos:
        ts = ts_de_arquivo_log(arq)
        if not ts:
            continue
        try:
            dados = ler_log_sessao(os.path.join(pasta_logs, arq))
        except Exception:
            continue
        caminhos = set((dados.get("snapshot") or {}).keys())
        for grupo in dados.get("logs", []):
            caminhos.update((grupo.get("snapshot") or {}).keys())
        for rel in caminhos:
            atual = aparicao.get(rel)
            if atual is None or ts < atual:
                aparicao[rel] = ts
    return aparicao

def criados_depois_de(pasta_logs, snapshot, ts_alvo):
    """Retorna caminhos rastreados que não estão no snapshot alvo e cuja primeira
    aparição registrada é posterior a ts_alvo (criados depois do ponto)."""
    if not ts_alvo:
        return []
    aparicoes = primeira_aparicao_por_arquivo(pasta_logs)
    criados = []
    for rel, ts in aparicoes.items():
        if rel in snapshot:
            continue
        if ts > ts_alvo:
            criados.append(rel)
    return criados

def _aplicar_nos_logs(pasta_logs, aplicar):
    """Percorre os logs de sessao da pasta e aplica `aplicar(fd, nome) -> bool`.

    Grava o log novamente se `aplicar` indicar alteracao em algum file.
    """
    if not pasta_logs or not os.path.isdir(pasta_logs):
        return
    for arq in os.listdir(pasta_logs):
        if not (arq.startswith("sessionlog_") and arq.endswith(".json")):
            continue
        caminho = os.path.join(pasta_logs, arq)
        try:
            payload = ler_log_sessao(caminho)
        except Exception:
            continue
        alterado = False
        for grupo in payload.get("logs", []):
            for fd in grupo.get("files", []):
                nome = (fd.get("name") or "").replace(os.sep, "/")
                if aplicar(fd, nome):
                    alterado = True
        if alterado:
            try:
                with open(caminho, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
            except OSError:
                pass

def propagar_rename_logs(antigo, novo):
    """Atualiza as referências ao caminho antigo nos logs persistidos da sessão."""
    antigo = (antigo or "").replace(os.sep, "/")
    novo = (novo or "").replace(os.sep, "/")
    if not antigo or antigo == novo:
        return
    def _aplicar(fd, nome):
        if nome == antigo or nome.startswith(antigo + "/"):
            fd["name"] = novo + nome[len(antigo):]
            return True
        return False
    _aplicar_nos_logs(pasta_session_logs(), _aplicar)

def marcar_deletado_logs(rel):
    """Marca arquivos deletados nos logs para que a interface os exiba riscados."""
    rel = (rel or "").replace(os.sep, "/")
    if not rel:
        return
    def _aplicar(fd, nome):
        if nome == rel or nome.startswith(rel + "/"):
            fd["deleted"] = True
            return True
        return False
    _aplicar_nos_logs(pasta_session_logs(), _aplicar)

def carregar_snapshot_restauracao(pasta_logs, filename, round_id):
    """Carrega o checkpoint a ser restaurado a partir do arquivo de log.

    Retorna (dados, snapshot, erro). Em caso de erro, dados/snapshot são None e
    erro contém a mensagem amigável.
    """
    caminho = os.path.join(pasta_logs, filename)
    if not os.path.exists(caminho):
        return None, None, "Sessão não encontrada"
    try:
        dados = ler_log_sessao(caminho)
    except Exception as e:
        return None, None, str(e)

    round_id = str(round_id or "")
    snapshot = None
    if round_id:
        for grupo in dados.get("logs", []):
            if str(grupo.get("id")) == round_id:
                snapshot = grupo.get("snapshot")
                break
    if snapshot is None:
        snapshot = dados.get("snapshot") or {}
    return dados, snapshot, None
