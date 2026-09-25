import os
import json
import re
import time

from src.backend.services.file_watcher import PASTAS_IGNORADAS, TAMANHO_MAX
from src.backend.services.persistencia import gravar_json_atomico
from src.backend.state import estado, caminho_estado_projeto
def _caminho_checkpoint():
    return caminho_estado_projeto("chats", "checkpoint.json")

CHECKPOINT_TTL_SEGUNDOS = 7 * 24 * 60 * 60

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
        pasta_origem = dados.get("pasta_raiz")
        if pasta_origem and pasta_origem != estado["pasta_raiz"]:
            return None
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

def pasta_session_logs_em(pasta_raiz):
    """Pasta dos logs de sessao para uma raiz explicita.

    Os logs vivem em .axio/logs/session_logs, FORA de .axio/chats. O minerador
    do mempalace varre .axio/chats recursivamente: enquanto os logs estavam la
    dentro, cada sessionlog_*.json (alguns com centenas de MB) era minerado
    como se fosse uma conversa, enchendo o vetor de ruido e gerando dezenas de
    milhares de drawers orfas sempre que o prune apagava o log.
    """
    if not pasta_raiz:
        return ""
    return os.path.join(pasta_raiz, ".axio", "logs", "session_logs")

def pasta_session_logs():
    return pasta_session_logs_em(estado.get("pasta_raiz", ""))

def migrar_session_logs_antigos():
    """Move .axio/chats/session_logs para .axio/logs/session_logs (uma vez).

    A migracao tira os logs do alcance do minerador, que varre .axio/chats.
    Idempotente: sem a pasta antiga nao faz nada. Devolve o numero de ficheiros
    movidos.
    """
    raiz = estado.get("pasta_raiz", "")
    if not raiz:
        return 0
    antiga = os.path.join(raiz, ".axio", "chats", "session_logs")
    nova = pasta_session_logs_em(raiz)
    if not os.path.isdir(antiga) or os.path.abspath(antiga) == os.path.abspath(nova):
        return 0
    try:
        os.makedirs(nova, exist_ok=True)
        movidos = 0
        for nome in os.listdir(antiga):
            origem = os.path.join(antiga, nome)
            destino = os.path.join(nova, nome)
            if not os.path.isfile(origem):
                continue
            try:
                if os.path.exists(destino) and os.path.getsize(destino) >= os.path.getsize(origem):
                    os.unlink(origem)
                    continue
                os.replace(origem, destino)
                movidos += 1
            except OSError as e:
                print(f"[sessao] falha ao migrar {nome}: {e}")
        try:
            os.rmdir(antiga)
        except OSError:
            pass
        if movidos:
            print(f"[sessao] {movidos} logs movidos para .axio/logs/session_logs (fora do alcance do minerador)")
        return movidos
    except OSError as e:
        print(f"[sessao] falha ao migrar session_logs: {e}")
        return 0

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

def reparar_json_truncado(texto, limite):
    """Recupera o maior prefixo de `texto` que ainda forma JSON valido.

    Percorre o texto UMA vez (ate `limite`, a posicao onde o parser desistiu) e
    guarda as ultimas posicoes em que a estrutura estava consistente - o fim de
    um valor ja fechado - com o estado da pilha nesse instante. Depois fecha o
    que ficou aberto. Perde, no maximo, o item onde o ficheiro se corrompeu; o
    resto do log fica utilizavel em vez de um 500.

    Existe porque `raw_decode` nao serve para isto: num objecto de topo
    corrompido a meio ele levanta SEMPRE (so devolve valores completos), que era
    exactamente o caso do sessionlog_1788985169540.json.

    Devolve o objeto lido ou None se nem o inicio servir.
    """
    pilha = []
    dentro_string = False
    escape = False
    ancoras = []
    for i in range(min(limite, len(texto))):
        ch = texto[i]
        if dentro_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                dentro_string = False
            continue
        if ch == '"':
            dentro_string = True
        elif ch in "{[":
            pilha.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if not pilha or pilha.pop() != ch:
                break
            if len(ancoras) >= 4:
                ancoras.pop(0)
            ancoras.append((i + 1, list(pilha)))
    for pos, pilha_ok in reversed(ancoras):
        try:
            return json.loads(texto[:pos] + "".join(reversed(pilha_ok)))
        except ValueError:
            continue
    return None

def ler_log_sessao(caminho):
    """Le o log de sessao completo, tolerante a JSON corrompido.

    Cascata: (1) parse direto; (2) saneamento de escapes unicode invalidos
    (barra invertida seguida de nao-ASCII); (3) parse tolerante (strict=False,
    aceita caracteres de controlo crus); (4) reparo por corte no ultimo item
    intacto, fechando as estruturas abertas. So levanta se nada servir.
    """
    with open(caminho, "r", encoding="utf-8", errors="replace") as f:
        texto = f.read()
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        pass
    saneado = re.sub(r'\\([^\x00-\x7F])', r'\1', texto)
    try:
        return json.loads(saneado)
    except json.JSONDecodeError:
        pass
    try:
        return json.JSONDecoder(strict=False).decode(saneado)
    except ValueError as e:
        ultimo_erro = e
    dados = reparar_json_truncado(saneado, getattr(ultimo_erro, "pos", len(saneado)))
    if dados is not None:
        return dados
    raise ultimo_erro

CABECALHO_LOG_BYTES = 8192

def ler_cabecalho_log_sessao(caminho):
    """Le apenas o INICIO do log: timestamp, datetime e summary.

    Estes tres campos ficam no topo do JSON, mas o historico lia o ficheiro
    inteiro para os obter - cerca de 412 MB de parse a cada abertura (um unico
    sessionlog chegou a 132 MB). Aqui le-se so o prefixo e extraem-se os campos
    por regex, o que tambem torna a leitura imune a um JSON truncado no fim
    (era o que provocava 'Expecting , delimiter' no historico).

    Devolve um dict com os campos encontrados (vazio se nao der para ler).
    """
    try:
        with open(caminho, "r", encoding="utf-8", errors="replace") as f:
            prefixo = f.read(CABECALHO_LOG_BYTES)
    except OSError:
        return {}
    dados = {}
    for campo in ("datetime", "summary"):
        m = re.search(r'"' + campo + r'"\s*:\s*"((?:[^"\\]|\\.)*)"', prefixo)
        if not m:
            continue
        try:
            dados[campo] = json.loads('"' + m.group(1) + '"')
        except ValueError:
            dados[campo] = m.group(1)
    m = re.search(r'"timestamp"\s*:\s*(\d+)', prefixo)
    if m:
        dados["timestamp"] = int(m.group(1))
    return dados

def gravar_log_sessao(caminho, dados):
    """Grava o log de sessao de forma ATOMICA (ficheiro temporario + replace).

    O json.dump diretamente sobre o ficheiro final deixava um JSON truncado
    quando o processo morria a meio da escrita (kill do Electron, crash, fim de
    sessao abrupto). Um log truncado quebra o parse e o card do historico fica
    sem data nem preview. Com tmp + os.replace o ficheiro final tem sempre a
    versao antiga inteira ou a nova inteira - nunca metade.
    """
    return gravar_json_atomico(caminho, dados, fsync=True)

_MARCADORES_DE_PONTO = (
    (b'"salvo"', rb"\s*:\s*true"),
    (b'"commit"', rb'\s*:\s*"[0-9a-f]{7,}'),
)

def _log_tem_ponto(caminho):
    """Deteta, lendo o ficheiro em blocos, se o log tem um ponto de retorno.

    Ponto de retorno e uma tarefa salva (campo dos logs antigos) ou uma tarefa
    commitada no git: o commit passou a ser o ponto pelo qual uma tarefa se
    repoe, e um card com ponto nunca pode sair pela rotacao dos 3 dias.

    Parsear logs de dezenas de MB so para isto custava minutos e muita memoria.
    A procura por blocos e ordens de magnitude mais barata. Em caso de duvida
    (leitura falhada) devolve True: preservar a mais e seguro; apagar uma sessao
    com ponto nao e.
    """
    try:
        with open(caminho, "rb") as f:
            resto = b""
            while True:
                bloco = f.read(1024 * 1024)
                if not bloco:
                    return False
                texto = resto + bloco
                for alvo, padrao in _MARCADORES_DE_PONTO:
                    inicio = 0
                    while True:
                        pos = texto.find(alvo, inicio)
                        if pos == -1:
                            break
                        depois = texto[pos + len(alvo):pos + len(alvo) + 24]
                        if re.match(padrao, depois):
                            return True
                        inicio = pos + len(alvo)
                resto = texto[len(texto) - 32:]
    except OSError:
        return True

def prune_session_logs(pasta_logs, manter_dias=3):
    """Mantém apenas as sessões de log dos últimos N dias distintos (por data).

    Sessões que contêm um ponto de retorno (tarefa salva ou tarefa commitada no
    git) são preservadas mesmo fora da janela de dias, para que um card com
    ponto nunca seja sobrescrito/removido.

    Devolve a lista dos nomes de arquivo removidos, para quem chamou poder
    limpar do vetor as drawers mineradas desses logs (senao ficariam orfas).
    """
    try:
        arquivos = [f for f in os.listdir(pasta_logs) if f.startswith("sessionlog_") and f.endswith(".json")]
    except OSError:
        return []

    infos = []
    for arq in arquivos:
        ts = ts_de_arquivo_log(arq)
        cabecalho = ler_cabecalho_log_sessao(os.path.join(pasta_logs, arq))
        dia = (cabecalho.get("datetime") or "").split(" ")[0]
        if not dia and ts:
            dia = time.strftime("%d/%m/%Y", time.localtime(ts / 1000))
        infos.append((dia, ts, arq))

    infos.sort(key=lambda x: x[1], reverse=True)

    dias_recentes = []
    for dia, ts, arq in infos:
        if dia and dia not in dias_recentes:
            dias_recentes.append(dia)
        if len(dias_recentes) >= manter_dias:
            break
    dias_recentes = set(dias_recentes)

    removidos = []
    for dia, ts, arq in infos:
        if dia and dia in dias_recentes:
            continue
        caminho = os.path.join(pasta_logs, arq)
        if _log_tem_ponto(caminho):
            continue
        try:
            os.remove(caminho)
            removidos.append(arq)
        except OSError as e:
            print(f"[sessao] falha ao remover log antigo {arq}: {e}")
    return removidos

def criar_sessao_vazia(pasta_raiz, session_id):
    """Cria o arquivo de log vazio da sessão para o card "em andamento" já
    aparecer no histórico assim que a sessão inicia (sem esperar a 1ª edição)."""
    try:
        pasta_logs = pasta_session_logs_em(pasta_raiz)
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
        gravar_log_sessao(caminho, payload)
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

def capturar_arvore(pasta_raiz, referencia=None, teto_bytes=TAMANHO_MAX):
    """Le a arvore do projeto e devolve o que o registo ainda nao conhece.

    `capturar_snapshot` cobre so os arquivos que as FERRAMENTAS tocaram nesta
    sessao: um arquivo criado ou editado a mao nunca entrava no registo, e por
    isso nunca era restaurado nem removido. Aqui a arvore e lida inteira e
    comparada com `referencia` (o snapshot herdado, ja em memoria) - entra o
    caminho que falta e o que tem conteudo diferente. Medido no projeto real:
    136 arquivos / 2,1 MB em 0,033s.

    `PASTAS_IGNORADAS` e a MESMA lista que alimenta o file_watcher, para o
    registo descrever exatamente o que a arvore do editor mostra. Binarios e
    arquivos acima de `teto_bytes` ficam de fora: nao ha versao de texto para
    repor.
    """
    if not pasta_raiz:
        return {}
    referencia = referencia or {}
    capturado = {}
    for dirpath, dirnames, filenames in os.walk(pasta_raiz):
        dirnames[:] = [d for d in dirnames if d not in PASTAS_IGNORADAS]
        for nome in filenames:
            caminho = os.path.join(dirpath, nome)
            try:
                if os.path.getsize(caminho) > teto_bytes:
                    continue
                with open(caminho, "r", encoding="utf-8") as f:
                    conteudo = f.read()
            except (OSError, UnicodeDecodeError):
                continue
            rel = os.path.relpath(caminho, pasta_raiz).replace("\\", "/")
            conhecido = referencia.get(rel)
            if isinstance(conhecido, dict) and conhecido.get("conteudo") == conteudo:
                continue
            capturado[rel] = {"conteudo": conteudo}
    return capturado

def snapshot_sessao_anterior(pasta_logs, ignorar_session_id, antes_de=0):
    """Carrega o checkpoint final da sessão mais recente (exceto a atual) na pasta.

    Mantém o snapshot cumulativo entre sessões: arquivos editados numa sessão
    anterior continuam presentes no checkpoint das sessões seguintes, mesmo que
    não sejam editados novamente.

    Um log de sessão VAZIO (o esqueleto de 124 B que cada arranque do programa
    grava, com `snapshot: {}`) não é um ponto de herança válido: escolhido pelo
    timestamp, apagava a memória de uma sessão inteira — foi assim que o
    checkpoint de uma tarefa recente ficou com 5 chaves onde devia ter 47, e
    restaurá-lo deixou 42 ficheiros na era de uma restauração anterior. Quando o
    log mais recente não tem snapshot, a busca continua no anterior (ler 124 B é
    instantâneo). `antes_de` limita a escolha a logs anteriores a esse timestamp,
    para recompor a herança de um ponto antigo.
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
        if not ts or (antes_de and ts >= antes_de):
            continue
        if ts > melhor_ts:
            melhor_ts = ts
            melhor_arq = arq
    if not melhor_arq:
        return {}
    try:
        snapshot = ler_log_sessao(os.path.join(pasta_logs, melhor_arq)).get("snapshot") or {}
    except Exception:
        return {}
    if not snapshot:
        return snapshot_sessao_anterior(pasta_logs, ignorar_session_id, melhor_ts)
    return snapshot

_TAMANHO_LOG_VAZIO = 1024

def snapshot_recomposto(pasta_logs, arq_alvo, teto=8):
    """Soma a cadeia de snapshots anteriores a um log: a herança que ele devia ter.

    O snapshot de um ponto é o cumulativo das sessões até ali, mas ficou gravado
    com o que a gravação conseguiu herdar — e uma sessão que arrancou com um log
    vazio pelo caminho ficou com a herança amputada. Aqui a cadeia é somada de
    novo, do log mais antigo para o mais recente, cada um a sobrepor-se ao
    anterior: o resultado é o último conteúdo conhecido de cada ficheiro, que é o
    que a restauração tem de repor. A leitura (restauro e prévia) recompõe sempre,
    para um checkpoint amputado não deixar ficheiros na era errada; a gravação
    usa-a ao abrir uma sessão, para a amputação não se propagar às seguintes.

    Fica de fora o próprio log alvo: o snapshot de topo dele é o do FIM da sessão
    e arrastaria o futuro para dentro de um ponto do meio. `teto` limita quantos
    logs da cadeia se leem (os vazios, abaixo de `_TAMANHO_LOG_VAZIO`, nem contam)
    e existe para a GRAVAÇÃO, que corre ao abrir uma sessão e não pode pagar uma
    varredura da pasta toda. A RESTAURAÇÃO usa `heranca_do_checkpoint`, sem teto:
    a herança de um ponto antigo pode estar a dezenas de logs de distância.
    """
    ts_alvo = ts_de_arquivo_log(os.path.basename(arq_alvo or ""))
    if not ts_alvo:
        return {}
    try:
        arquivos = os.listdir(pasta_logs)
    except OSError:
        return {}
    candidatos = []
    for arq in arquivos:
        if not (arq.startswith("sessionlog_") and arq.endswith(".json")):
            continue
        ts = ts_de_arquivo_log(arq)
        if not ts or ts >= ts_alvo:
            continue
        try:
            if os.path.getsize(os.path.join(pasta_logs, arq)) < _TAMANHO_LOG_VAZIO:
                continue
        except OSError:
            continue
        candidatos.append((ts, arq))
    candidatos.sort()
    acumulado = {}
    for _ts, arq in candidatos[-teto:]:
        try:
            dados = ler_log_sessao(os.path.join(pasta_logs, arq))
        except Exception:
            continue
        for rel, meta in (dados.get("snapshot") or {}).items():
            if isinstance(meta, dict):
                acumulado[rel] = meta
    return acumulado

def heranca_do_checkpoint(pasta_logs, arq_alvo, varredura=None):
    """A herança COMPLETA de um ponto: a última versão de cada ficheiro antes dele.

    `snapshot_recomposto` lê só os últimos `teto` logs — barato, e é o que a
    GRAVAÇÃO usa ao abrir uma sessão. Aqui a varredura percorre a pasta toda e
    devolve, por ficheiro, a versão do log mais recente ANTERIOR ao alvo: é a
    herança que o checkpoint devia ter e a que a restauração tem de repor. A de
    um ponto antigo pode estar a dezenas de logs de distância (medido em
    13/09/2026: 81 logs, para o `services/session.py` do checkpoint da tarefa 3) e
    com o teto curto esses ficheiros ficavam fora — nem repostos nem removidos,
    ficavam com o código de agora, sem aviso no ecrã.

    `varredura` reaproveita uma varredura já feita na mesma operação: a
    classificação dos rastreados precisa da mesma passagem pelos logs.
    """
    if varredura is None:
        varredura = varredura_dos_logs(pasta_logs, arq_alvo)
    return varredura[1]

def varredura_dos_logs(pasta_logs, arq_alvo=""):
    """UMA passagem pelos logs alimenta as duas leituras da restauração.

    Devolve (aparicoes, versoes) e as duas saem da mesma leitura:

    - `aparicoes`: {rel: ts da primeira aparição} em qualquer log (topo ou rodada).
      Substitui a inferência por diferença de conjuntos: um arquivo só é
      considerado "criado depois do ponto" quando a sua primeira aparição
      registrada é posterior ao timestamp do checkpoint restaurado — o que
      elimina falsos positivos de snapshots incompletos (herança quebrada).
    - `versoes`: {rel: meta} da última versão registada em log ANTERIOR a
      `arq_alvo`. O próprio alvo fica de fora: o snapshot de topo dele é o do FIM
      da sessão e arrastaria o futuro para dentro de um ponto do meio.

    A `versoes` é o que faz a restauração repor TODOS os ficheiros no ponto. O
    snapshot gravado de um checkpoint é o cumulativo da cadeia, e uma sessão que
    arrancou com um log vazio pelo caminho ficou com a herança amputada: os
    ficheiros que saíram da cadeia não eram repostos nem removidos, ficavam com o
    código de agora e a restauração parecia ter "saltado" ficheiros. A herança
    de um ponto antigo pode estar a dezenas de logs de distância (medido em
    13/09/2026: o `services/session.py` do checkpoint da tarefa 3 só aparecia 81
    logs antes dele), por isso a varredura vai até ao fim da pasta.

    Os logs são percorridos do mais antigo para o mais recente para a `versoes`
    ficar com a última versão de cada ficheiro (a sobreposição é a ordem).
    """
    aparicoes = {}
    versoes = {}
    try:
        arquivos = [f for f in os.listdir(pasta_logs) if f.startswith("sessionlog_") and f.endswith(".json")]
    except OSError:
        return aparicoes, versoes
    ts_alvo = ts_de_arquivo_log(os.path.basename(arq_alvo or "")) if arq_alvo else 0
    for arq in sorted(arquivos, key=ts_de_arquivo_log):
        ts = ts_de_arquivo_log(arq)
        if not ts:
            continue
        caminho = os.path.join(pasta_logs, arq)
        try:
            if os.path.getsize(caminho) < _TAMANHO_LOG_VAZIO:
                continue
        except OSError:
            continue
        try:
            dados = ler_log_sessao(caminho)
        except Exception:
            continue
        snap = dados.get("snapshot") or {}
        caminhos = set(snap.keys())
        for grupo in dados.get("logs", []):
            caminhos.update((grupo.get("snapshot") or {}).keys())
        for rel in caminhos:
            atual = aparicoes.get(rel)
            if atual is None or ts < atual:
                aparicoes[rel] = ts
        if ts_alvo and ts < ts_alvo:
            for rel, meta in snap.items():
                if isinstance(meta, dict):
                    versoes[rel] = meta
    return aparicoes, versoes

def primeira_aparicao_por_arquivo(pasta_logs):
    """{rel: ts da primeira aparição} — a classificação dos rastreados.

    Casca da varredura que também produz a herança (`varredura_dos_logs`): quando
    as duas são precisas na mesma operação, quem chama varre uma vez e passa o
    resultado, em vez de ler a pasta de logs duas vezes.
    """
    return varredura_dos_logs(pasta_logs)[0]

def rastreados_fora_do_snapshot(pasta_logs, snapshot, ts_alvo, aparicoes=None):
    """Classifica os rastreados que o snapshot alvo não cobre, em duas listas.

    - `criados_depois`: a primeira aparição é posterior ao ponto -> nasceram
      depois dele e a restauração manda-os para a lixeira;
    - `fora_do_alcance`: já existiam antes do ponto mas não estão no snapshot ->
      a restauração não os conhece: não os repõe nem os remove, ficam no disco
      com o conteúdo de agora. COM A HERANÇA COMPLETA (`heranca_do_checkpoint`)
      esta lista tende a esvaziar-se: um ficheiro que já existia antes do ponto e
      foi registado em algum log entra pelo `versoes`. Sobra o caso sem remédio —
      o ficheiro cuja única versão registada é posterior ao ponto.

    Uma varredura de logs só serve as duas listas — por isso saem juntas e não de
    duas chamadas. `aparicoes` permite reaproveitar uma varredura já feita na
    mesma operação (a restauração corre `varredura_dos_logs` para a herança).
    """
    if not ts_alvo:
        return [], []
    if aparicoes is None:
        aparicoes = primeira_aparicao_por_arquivo(pasta_logs)
    criados = []
    fora = []
    for rel, ts in aparicoes.items():
        if rel in snapshot:
            continue
        (criados if ts > ts_alvo else fora).append(rel)
    return sorted(criados), sorted(fora)

def criados_depois_de(pasta_logs, snapshot, ts_alvo, aparicoes=None):
    """Retorna caminhos rastreados que não estão no snapshot alvo e cuja primeira
    aparição registrada é posterior a ts_alvo (criados depois do ponto)."""
    return rastreados_fora_do_snapshot(pasta_logs, snapshot, ts_alvo, aparicoes)[0]

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
                gravar_log_sessao(caminho, payload)
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

def marcar_commit_no_log(nome_log, turn_id, hash_commit, mensagem=""):
    """Grava o hash do commit do git no turno do log, para o card saber o ponto exato."""
    pasta_logs = pasta_session_logs()
    if not pasta_logs:
        return False
    caminho = os.path.join(pasta_logs, os.path.basename(nome_log or ""))
    if not os.path.isfile(caminho):
        return False
    try:
        payload = ler_log_sessao(caminho)
    except Exception:
        return False
    for grupo in payload.get("logs") or []:
        if str(grupo.get("id")) != str(turn_id):
            continue
        grupo["commit"] = hash_commit or ""
        grupo["commit_nome"] = (mensagem or "").strip()
        if hash_commit:
            registos = grupo.get("commits")
            if not isinstance(registos, list):
                registos = []
            if not any(isinstance(r, dict) and r.get("hash") == hash_commit for r in registos):
                registos.append({"hash": hash_commit, "nome": (mensagem or "").strip()})
            grupo["commits"] = registos
        try:
            gravar_log_sessao(caminho, payload)
        except OSError:
            return False
        return True
    return False

def carregar_snapshot_restauracao(pasta_logs, filename, round_id, varredura=None):
    """Carrega o checkpoint a ser restaurado a partir do arquivo de log.

    Retorna (dados, snapshot, erro). Em caso de erro, dados/snapshot são None e
    erro contém a mensagem amigável. `varredura` reaproveita a passagem pelos
    logs que o chamador já fez (`varredura_dos_logs`) — a mesma que alimenta a
    classificação dos rastreados, para a pasta não ser lida duas vezes.
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

    heranca = heranca_do_checkpoint(pasta_logs, filename, varredura)
    if heranca:
        snapshot = {**heranca, **snapshot}
    return dados, snapshot, None
