"""Escrita atomica de JSON: o ficheiro final nunca fica a meio.

A mesma sequencia (ficheiro temporario ao lado + os.replace) apareceu em tres
pontos - o glossario, o log de sessao e o radar de atrito - e cada um com um
detalhe diferente. Aqui vive a unica versao; quem grava escolhe so o indent e se
quer fsync.
"""

import json
import os
import tempfile
import threading
import time

_escritas = {}
_escritas_lock = threading.Lock()

_SUFIXOS_TEMPORARIOS = (".json", ".md", ".txt")


def _lock_de(caminho):
    """Lock por caminho: serializa escritas concorrentes do MESMO ficheiro.

    O Flask responde em varias threads (werkzeug threaded). Sem isto, dois saves
    do mesmo log de sessao escreviam ao mesmo tempo e o os.replace publicava
    bytes intercalados - foi assim que um sessionlog de 9 MB ficou com
    'Expecting \",\" delimiter' a meio, a que o historico respondia 500.

    Vive no processo: ha um unico processo Flask. Com mais de um, isto teria de
    passar a lock de ficheiro.
    """
    with _escritas_lock:
        trava = _escritas.get(caminho)
        if trava is None:
            trava = threading.Lock()
            _escritas[caminho] = trava
        return trava


def _gravar_atomico(caminho, escrever, sufixo, fsync):
    """Nucleo comum da escrita atomica: temporario UNICO ao lado + publicacao.

    `escrever` recebe o ficheiro ja aberto e deita la dentro o que for; o lock
    por caminho, o temporario, a limpeza em caso de falha e o os.replace vivem
    so aqui.
    """
    pasta = os.path.dirname(caminho)
    if pasta:
        os.makedirs(pasta, exist_ok=True)
    with _lock_de(os.path.abspath(caminho)):
        fd, temporario = tempfile.mkstemp(prefix=".tmp-", suffix=sufixo, dir=pasta or ".")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                escrever(f)
                if fsync:
                    f.flush()
                    os.fsync(f.fileno())
            _publicar_atomicamente(temporario, caminho)
        except BaseException:
            try:
                os.unlink(temporario)
            except OSError:
                pass
            raise
    return True


def gravar_json_atomico(caminho, dados, indent=2, fsync=False):
    """Grava `dados` em `caminho` sem deixar o ficheiro final truncado.

    Quem le este ficheiro concorrentemente - o Flask, a cada rodada - passa a ver
    sempre a versao antiga inteira ou a nova inteira, nunca metade. Cria a pasta
    se faltar.

    fsync=True forca o conteudo ao disco antes da troca, ao custo de uma descida
    ao disco; e o que salva o log de sessao quando o processo e morto a meio
    (kill do Electron, crash, fim de sessao abrupto). Para ficheiros de estado,
    o False basta.
    """
    return _gravar_atomico(
        caminho,
        lambda f: json.dump(dados, f, ensure_ascii=False, indent=indent),
        ".json",
        fsync,
    )


def _publicar_atomicamente(temporario, caminho):
    """os.replace com retry: no Windows o destino pode estar momentaneamente
    travado por outro processo (Dropbox/antivirus) e falhar com WinError 32.
    """
    ultimo = None
    for tentativa in range(5):
        try:
            os.replace(temporario, caminho)
            return
        except OSError as e:
            ultimo = e
            if getattr(e, "winerror", None) != 32:
                raise
            time.sleep(0.2 * (tentativa + 1))
    raise ultimo


def limpar_temporarios_orfaos(pastas, idade_minima=600):
    """Recolhe os `.tmp-*` que uma escrita morta a meio deixou para tras.

    `gravar_json_atomico` limpa o seu temporario quando falha, mas essa limpeza
    tambem pode falhar: se o Dropbox/antivirus tiver o proprio temporario
    aberto, o `os.unlink` levanta o mesmo WinError 32 e o `except OSError` do
    chamador engole-o - o ficheiro fica para sempre. Ninguem le estes nomes,
    por isso sao lixo puro; sao recolhidos uma vez, no arranque, em vez de
    ficarem a pedir que o utilizador os apague a mao.

    `idade_minima` (10 min) protege uma escrita em curso de ser apanhada.
    """
    agora = time.time()
    apagados = 0
    for pasta in pastas:
        if not pasta or not os.path.isdir(pasta):
            continue
        for nome in os.listdir(pasta):
            if not (nome.startswith(".tmp-") and nome.endswith(_SUFIXOS_TEMPORARIOS)):
                continue
            caminho = os.path.join(pasta, nome)
            try:
                if agora - os.path.getmtime(caminho) < idade_minima:
                    continue
                os.unlink(caminho)
                apagados += 1
            except OSError:
                pass
    return apagados
