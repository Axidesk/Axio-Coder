"""O que o disco recebeu nos ultimos minutos - onde um programa gravou os ficheiros dele.

Responde a "instalei isto e nao sei onde ficaram os ficheiros", "o que este programa acabou de
escrever" e "o que mudou nesta pasta desde as 20h". Varre as raizes pedidas (a pasta do projeto por
omissao) e devolve, do mais novo para o mais antigo e agrupados pela pasta que os recebeu, os
ficheiros escritos dentro da janela de tempo - com a hora e o tamanho.
"""
import os
import time

from src.backend.services.file_service import resolver_caminho
from src.backend.state import emit_event
from src.backend.tools.registry import register

PASTAS_DE_FORA = frozenset(
    {
        "windows",
        "winsxs",
        "servicing",
        "assembly",
        "driverstore",
        "installer",
        "packages",
        "system volume information",
    }
)
SEGUNDOS_DE_BUSCA = 30
LIMITE_DE_VISITAS = 600000
LIMITE_POR_OMISSAO = 120


def _tamanho(bytes_):
    if bytes_ < 1024:
        return f"{bytes_} B"
    if bytes_ < 1024 * 1024:
        return f"{bytes_ / 1024:.0f} KB"
    return f"{bytes_ / (1024 * 1024):.1f} MB"


def _hora(quando):
    return time.strftime("%d/%m %H:%M:%S", time.localtime(quando))


def _varrer(raiz, desde, filtro, achados, prazo):
    visitas = 0
    pilha = [raiz]
    while pilha:
        if time.monotonic() > prazo or visitas > LIMITE_DE_VISITAS:
            return visitas, False
        try:
            with os.scandir(pilha.pop()) as entradas:
                for entrada in entradas:
                    visitas += 1
                    try:
                        if entrada.is_dir(follow_symlinks=False):
                            if entrada.name.lower() not in PASTAS_DE_FORA:
                                pilha.append(entrada.path)
                            continue
                        if not entrada.is_file(follow_symlinks=False):
                            continue
                        if filtro and filtro.lower() not in entrada.name.lower():
                            continue
                        dados = entrada.stat()
                    except OSError:
                        continue
                    if dados.st_mtime >= desde:
                        achados.append((dados.st_mtime, entrada.path, dados.st_size))
        except OSError:
            visitas += 1
    return visitas, True


@register(
    "tool_arquivos_recentes",
    "Diz O QUE O DISCO RECEBEU nos ultimos minutos: onde um programa gravou os ficheiros dele, o "
    "que um build, uma instalacao ou um export acabaram de escrever, e o que mudou numa pasta "
    "desde uma certa hora. Varre as raizes pedidas (a pasta do projeto por omissao) e devolve os "
    "ficheiros escritos dentro da janela de tempo, do mais novo para o mais antigo e agrupados "
    "pela pasta que os recebeu, com a hora e o tamanho. Use quando a pergunta for 'onde isto foi "
    "parar?' em vez de andar a adivinhar pastas.",
    {
        "raizes": {
            "tipo": "STRING",
            "obrig": False,
            "padrao": "",
            "desc": "Uma pasta por linha (a pasta do projeto quando fica vazio). Aceita caminhos fora do projeto.",
        },
        "minutos": {
            "tipo": "INTEGER",
            "obrig": False,
            "padrao": 30,
            "desc": "A janela de tempo para tras, em minutos.",
        },
        "filtro": {
            "tipo": "STRING",
            "obrig": False,
            "padrao": "",
            "desc": "So os ficheiros cujo nome contenha este trecho (ex: .exe).",
        },
        "limite": {
            "tipo": "INTEGER",
            "obrig": False,
            "padrao": LIMITE_POR_OMISSAO,
            "desc": "Maximo de ficheiros listados.",
        },
    },
)
def tool_arquivos_recentes(raizes="", minutos=30, filtro="", limite=LIMITE_POR_OMISSAO):
    emit_event("executing", function="O que o disco recebeu")
    pedidas = [linha.strip() for linha in str(raizes or "").splitlines() if linha.strip()]
    if not pedidas:
        pedidas = ["."]
    alvos = []
    for pedida in pedidas:
        caminho, erro = resolver_caminho(pedida, permitir_extra=True)
        if erro:
            return erro
        if not os.path.isdir(caminho):
            return f"ERRO: pasta nao encontrada: {pedida}"
        alvos.append(caminho)

    try:
        minutos = max(1, int(minutos))
    except (TypeError, ValueError):
        minutos = 30
    try:
        limite = max(1, int(limite))
    except (TypeError, ValueError):
        limite = LIMITE_POR_OMISSAO

    desde = time.time() - minutos * 60
    prazo = time.monotonic() + SEGUNDOS_DE_BUSCA
    achados = []
    visitas = 0
    varreu_tudo = True
    for alvo in alvos:
        gastas, completa = _varrer(alvo, desde, filtro, achados, prazo)
        visitas += gastas
        varreu_tudo = varreu_tudo and completa

    if not achados:
        return (
            f"nada escrito nos ultimos {minutos} min "
            f"em {', '.join(alvos)} | {visitas} item(ns) visitados"
        )

    achados.sort(key=lambda achado: achado[0], reverse=True)
    por_pasta = {}
    for quando, caminho, tamanho in achados:
        por_pasta.setdefault(os.path.dirname(caminho), []).append(
            (quando, os.path.basename(caminho), tamanho)
        )

    linhas = [
        f"{len(achados)} ficheiro(s) escritos desde {_hora(desde)} (ha {minutos} min) | "
        f"{len(por_pasta)} pasta(s) | {visitas} item(ns) visitados"
    ]
    if not varreu_tudo:
        linhas.append(
            f"a busca parou no teto ({SEGUNDOS_DE_BUSCA}s ou {LIMITE_DE_VISITAS} itens) - "
            "estreite as raizes ou use o filtro"
        )
    mostrados = 0
    for pasta, itens in sorted(
        por_pasta.items(), key=lambda par: max(item[0] for item in par[1]), reverse=True
    ):
        if mostrados >= limite:
            break
        linhas.append("")
        linhas.append(pasta)
        for quando, nome, tamanho in itens:
            if mostrados >= limite:
                linhas.append(
                    f"   ... (+{len(achados) - mostrados} ficheiro(s) - repita com limite maior)"
                )
                break
            linhas.append(f"   {_hora(quando)}  {_tamanho(tamanho):>9}  {nome}")
            mostrados += 1
    return "\n".join(linhas)
