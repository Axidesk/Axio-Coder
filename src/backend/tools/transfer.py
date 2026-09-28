"""Copia, movimento e medicao de transferencias de ficheiros e pastas."""

import json
import os
import shutil
import sys
import tempfile
import time

from src.backend.services.file_service import resolver_caminho
from src.backend.services.transferencia import (LIMITE_DE_FICHEIRO_GRANDE, duracao_texto,
                                                limpar_passagem, planear)
from src.backend.state import emit_event, estado, notificar_mudanca_arquivos
from src.backend.tools.process import correr_como_card
from src.backend.tools.registry import register

RAPIDO_S = 15.0
SOZINHO_S = 120.0
LIMITE_DO_CARD_S = 900

_CODIGO_DO_CORREDOR = (
    "import json\n"
    "import sys\n"
    "\n"
    "with open(sys.argv[1], encoding='utf-8') as ficheiro:\n"
    "    plano = json.load(ficheiro)\n"
    "sys.path.insert(0, plano['raiz_do_axio'])\n"
    "from src.backend.services.transferencia import executar\n"
    "executar(plano)\n"
)

@register(
    "tool_transferir",
    "Copia, move (recorta) ou MEDE uma transferencia de ficheiros ou pastas, sempre com o custo MEDIDO "
    "antes de comecar: conta os ficheiros, sonda a velocidade real de leitura na origem e de escrita no "
    "destino e - se o destino estiver dentro de uma pasta sincronizada (Dropbox, OneDrive) - sonda "
    "tambem o caminho por uma area de passagem no mesmo disco, e escolhe por MEDICAO o mais barato. "
    "COMECE POR acao='medir' (e barata e evita a espera cega). Se o previsto passar 2 minutos, a "
    "ferramenta RECUSA copiar sozinha e diz o que fazer a mao (arrastar no Explorador, que copia com "
    "varios fios); com forcar=True corre mesmo assim. A copia aparece como card do terminal, com a "
    "barra de progresso a encher e a falta de tempo escrita linha a linha, e um 'mover' so apaga a "
    "origem depois de a copia inteira ter sido CONFERIDA ficheiro a ficheiro.",
    {
        "origem": {"tipo": "STRING", "obrig": True, "desc": "Ficheiro ou pasta de origem (pode estar fora do projeto).", "padrao": ""},
        "destino": {"tipo": "STRING", "obrig": True, "desc": "Caminho final, dentro do projeto. Se for uma pasta que ja existe, o item entra DENTRO dela com o proprio nome.", "padrao": ""},
        "acao": {"tipo": "STRING", "enum": ["medir", "copiar", "mover"], "desc": "'medir' so mede e diz o tempo previsto; 'copiar' deixa a origem; 'mover' e o recortar (apaga a origem no fim, so depois de conferir o destino).", "padrao": "medir"},
        "forcar": {"tipo": "BOOLEAN", "desc": "Corre mesmo quando o tempo previsto passa o limite (2 min) e a ferramenta recusaria.", "padrao": False},
        "sobrescrever": {"tipo": "BOOLEAN", "desc": "Substitui um FICHEIRO de destino que ja exista. Pastas de destino sao sempre fundidas.", "padrao": False},
    },
    disponivel="edicao",
)
def tool_transferir(origem, destino, acao="medir", forcar=False, sobrescrever=False):
    if estado.get("bloquear_edicao"):
        return "BLOQUEADO (FASE 1): Voce esta em modo semi-automatico e ainda nao recebeu aprovacao para editar. Apresente seu plano e pergunte ao usuario se pode aplicar."
    acao = (acao or "medir").strip().lower()
    if acao not in ("medir", "copiar", "mover"):
        return f"ERRO: acao desconhecida '{acao}'. Use 'medir', 'copiar' ou 'mover' (mover = recortar)."
    forcar = _sim(forcar)
    sobrescrever = _sim(sobrescrever)
    origem_abs, erro = resolver_caminho(origem, permitir_extra=True)
    if erro:
        return erro
    if not os.path.exists(origem_abs):
        return f"ERRO: a origem '{origem}' nao existe."
    destino_abs, erro = resolver_caminho(destino, permitir_extra=False, permitir_escrita=True)
    if erro:
        return (f"ERRO: o destino tem de ficar DENTRO da pasta do projeto ({estado.get('pasta_raiz')}). "
                f"Para levar material para fora, faca-o no Explorador.\n({erro})")
    final, entrou_dentro = _destino_final(origem_abs, destino_abs)
    problema = _problema(origem_abs, final, sobrescrever)
    if problema:
        return problema
    raiz = estado.get("pasta_raiz") or ""
    plano = planear(origem_abs, final, "mover" if acao == "mover" else "copiar", raiz)
    if acao == "medir":
        _limpar_passagem(plano)
        return _texto_medicao(plano, final, entrou_dentro)
    if plano["modo"] != "renomear" and plano["estimativa"] > SOZINHO_S and not forcar:
        _limpar_passagem(plano)
        return _texto_recusa(plano, final)
    emit_event("executing", function=f"{_verbo(acao)} {os.path.basename(origem_abs)} ({plano['ficheiros']} ficheiros)")
    inicio = time.perf_counter()
    resultado = _correr(plano)
    decorrido = time.perf_counter() - inicio
    _limpar_passagem(plano)
    saida = ((getattr(resultado, "stdout", "") or "") + (getattr(resultado, "stderr", "") or "")).strip()
    if getattr(resultado, "returncode", None) is None:
        return ("TRANSFERENCIA INTERROMPIDA (card parado ou limite de tempo). O que ja entrou ficou no "
                f"destino e a origem NAO foi apagada.\n{saida}")
    if resultado.returncode != 0:
        return f"ERRO: a transferencia nao chegou ao fim (exit {resultado.returncode}).\n{saida}"
    notificar_mudanca_arquivos()
    return _texto_feito(plano, final, saida, decorrido)

def _sim(valor):
    if isinstance(valor, str):
        return valor.strip().lower() in ("1", "true", "sim", "yes", "s")
    return bool(valor)

def _destino_final(origem_abs, destino_abs):
    """(caminho final, se foi preciso entrar para dentro). O destino que ja e' pasta recebe o item
    dentro dele - como um arrastar para cima de uma pasta - e o texto di-lo em voz alta para nao
    haver duvida sobre onde o material foi parar."""
    if os.path.isdir(destino_abs):
        return os.path.join(destino_abs, os.path.basename(origem_abs)), True
    return destino_abs, False

def _problema(origem_abs, final, sobrescrever):
    if os.path.abspath(final).lower() == os.path.abspath(origem_abs).lower():
        return "ERRO: a origem e o destino sao o mesmo caminho."
    if os.path.abspath(final).lower().startswith(os.path.abspath(origem_abs).lower() + os.sep):
        return "ERRO: o destino esta DENTRO da origem - isso copiaria a pasta para dentro dela mesma."
    if os.path.isfile(final) and not sobrescrever:
        return f"ERRO: o destino '{final}' ja existe. Use sobrescrever=True para o substituir."
    return ""

def _correr(plano):
    pasta = tempfile.mkdtemp(prefix="axio_transfer_")
    try:
        ficheiro = os.path.join(pasta, "plano.json")
        with open(ficheiro, "w", encoding="utf-8") as f:
            json.dump(plano, f)
        script = os.path.join(pasta, "correr.py")
        with open(script, "w", encoding="utf-8") as f:
            f.write(_CODIGO_DO_CORREDOR)
        comando = f'"{sys.executable}" "{script}" "{ficheiro}"'
        limite = int(min(LIMITE_DO_CARD_S, max(180, plano["estimativa"] * 3 + 60)))
        return correr_como_card(comando, cwd=plano.get("raiz_do_projeto") or None, timeout=limite)
    finally:
        shutil.rmtree(pasta, ignore_errors=True)

def _limpar_passagem(plano):
    limpar_passagem(plano.get("passagem"))

def _verbo(acao):
    return "Copiando" if acao == "copiar" else "Movendo"

def _grandeza(bytes_):
    valor = float(bytes_ or 0)
    for unidade in ("B", "KB", "MB", "GB"):
        if valor < 1024:
            return f"{valor:.0f} {unidade}" if valor >= 100 or unidade == "B" else f"{valor:.2f} {unidade}"
        valor /= 1024
    return f"{valor:.2f} TB"

def _modo_texto(plano):
    if plano["modo"] == "renomear":
        return "rename (mesmo disco, sem reescrever bytes)"
    if plano["modo"] == "passagem":
        return f"area de passagem em {plano['passagem']} + entrada por rename"
    return "copia direta para o destino"

def _veredito(plano):
    previsto = plano["estimativa"]
    if previsto <= RAPIDO_S:
        return (f"FACO JA - {duracao_texto(previsto)} previstos. Chame acao='copiar' ou acao='mover' "
                "e acompanhe a barra do terminal.")
    if previsto <= SOZINHO_S:
        return (f"FACO - leva {duracao_texto(previsto)}. A barra de progresso mostra o que falta.")
    return (f"NAO FACAO SOZINHO - o previsto ({duracao_texto(previsto)}) passa o limite de "
            f"{duracao_texto(SOZINHO_S)}; veja as alternativas abaixo.")

def _texto_medicao(plano, final, entrou_dentro=False):
    linhas = [
        "MEDICAO (nada foi copiado).",
        f"  origem  : {plano['origem']}",
        f"  destino : {final}" + ("   <- a pasta indicada ja existia, logo o item entra DENTRO dela"
                                  if entrou_dentro else ""),
        f"  tamanho : {_grandeza(plano['bytes'])} em {plano['ficheiros']} ficheiros"
        + (f" (o maior tem {_grandeza(plano['maior'])})" if plano["ficheiros"] > 1 else ""),
    ]
    if plano["sincronizada"]:
        linhas.append(f"  ATENCAO: o destino esta dentro de uma pasta sincronizada ({plano['sincronizada']}): "
                      "escrever la custa caro POR FICHEIRO, porque o filtro da sincronia e o antivirus "
                      "inspecionam cada ficheiro novo.")
    if plano["modo"] == "renomear":
        linhas.append("  mover no mesmo disco: e um rename, sem reescrever bytes.")
        linhas.append("VEREDITO: INSTANTANEO nesse disco - use acao='mover'.")
        return "\n".join(linhas)
    linhas += [
        f"  sonda REAL: copiei {plano['amostra']} ficheiros desta origem - espalhados pela arvore, "
        f"para o destino e pelo caminho que vou usar - e limpei-os em {plano['segundos_da_sonda']:.2f}s "
        f"({plano['custo_por_ficheiro'] * 1000:.1f} ms por ficheiro).",
    ]
    if plano["s_passagem"] is not None:
        vezes = (plano["s_direto"] / plano["s_passagem"]) if plano["s_passagem"] else 0
        linhas += [
            f"     copiar direto no destino .... {plano['s_direto'] * 1000:.1f} ms/ficheiro",
            f"     copiar fora + rename ........ {plano['s_passagem'] * 1000:.1f} ms/ficheiro ({vezes:.1f}x mais barato)",
        ]
    linhas += [
        f"  caminho escolhido: {_modo_texto(plano)}",
        f"  tempo previsto: {duracao_texto(plano['estimativa'])} para {plano['ficheiros']} ficheiros "
        "(extrapolado da amostra, nao de tabela nenhuma)",
        f"  margem: entre {duracao_texto(plano['estimativa'] / 3)} e {duracao_texto(plano['estimativa'] * 2)} "
        "- o antivirus e a sincronia mudam de hora para hora, logo o que vale e' a ordem de grandeza; "
        "o tempo que falta a serio e' o que a barra mostra durante a copia",
    ]
    if plano["ficheiros"] > 1 and plano["maior"] > LIMITE_DE_FICHEIRO_GRANDE:
        linhas.append(f"  RESSALVA: o maior ficheiro tem {_grandeza(plano['maior'])} e ficou FORA da "
                      "amostra - a estimativa nao o conta; some-lhe o tempo de o ler e escrever.")
    linhas.append(f"VEREDITO: {_veredito(plano)}")
    return "\n".join(linhas)

def _texto_recusa(plano, final):
    origem = plano["origem"]
    pai = os.path.dirname(final)
    linhas = [
        f"NAO VOU FAZER SOZINHO: o previsto e {duracao_texto(plano['estimativa'])} e passa o limite de "
        f"{duracao_texto(SOZINHO_S)}. Ficar aqui a espera é rodada perdida - e o Windows faz isto melhor.",
        "",
        "FACA A MAO (mais rapido - o Explorador copia com varios fios ao mesmo tempo):",
        "  1. abra o Explorador do Windows;",
        f"  2. arraste  {origem}",
        f"     para dentro de  {pai}",
        f"  3. quando acabar, diga-me e eu sigo com o resto.",
    ]
    if plano["modo"] == "passagem" and plano["s_passagem"]:
        linhas += [
            "",
            f"Alternativa so' minha, se preferir: eu copio para {plano['passagem']} e entro com um "
            f"rename, o que aqui sai ~{(plano['s_direto'] / plano['s_passagem']):.1f}x mais barato por "
            "ficheiro - mas a SOMA e' a mesma, logo tambem nao a faco sozinho.",
        ]
    linhas += ["", "Se preferir que eu corra mesmo assim (mesmo tempo, mas com a barra a encher e sem "
                   "o prender), repita com forcar=True."]
    return "\n".join(linhas)

def _texto_feito(plano, final, saida, decorrido):
    previsto = plano["estimativa"]
    linhas = [
        f"{'MOVIDO' if plano['acao'] == 'mover' else 'COPIADO'} em {duracao_texto(decorrido)} reais "
        f"({duracao_texto(previsto)} previstos) - {plano['ficheiros']} ficheiros, {_grandeza(plano['bytes'])}.",
        f"  destino : {final}",
        f"  caminho : {_modo_texto(plano)}",
    ]
    conferido = [linha for linha in saida.splitlines() if "conferido" in linha]
    linhas.append(f"  {conferido[-1].strip() if conferido else 'sem bytes para conferir: o item foi renomeado'}")
    if plano["acao"] == "mover":
        linhas.append(f"  origem apagada: {'sim' if not os.path.exists(plano['origem']) else 'NAO - ainda la esta'}")
    return "\n".join(linhas)
