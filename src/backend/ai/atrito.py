"""Radar de atrito: mede o uso das minhas ferramentas e aponta onde elas me obrigaram a repetir trabalho.

Existe porque a regra 26 (auto-melhoria continua) nao pode depender de eu me
lembrar dela. Em vez de esperar que o agente note o proprio desgaste, o backend
conta o que aconteceu na rodada anterior e injeta a medicao no prompt da rodada
seguinte.

O aviso e auto-limitado: mostra-se UMA vez, na rodada imediatamente a seguir a
uma rodada com atrito. Registo antigo nunca reaparece, porque a injecao compara
o numero do registo com o numero da ultima rodada fechada. Rodada limpa nao
escreve nada no disco e nao injeta nada.

Os contadores vivem em RAM (custo zero por chamada de ferramenta) e o disco
recebe no maximo um registo por rodada com atrito. Nada aqui decide o que
melhorar: mede e aponta; julgar se vale uma ferramenta nova continua a ser do
agente.

LIMITE CONHECIDO: `_rodadas["fechadas"]` e RAM. Depois de um restart ele volta a
zero, por isso a primeira rodada seguinte ao boot nao ve o atrito da rodada
anterior (o registo em disco tem um numero que ja nao casa). E deliberado: nao
custa nada e evita mostrar-me atrito de uma sessao antiga como se fosse de agora.

FORA DO AXIO (trabalho num projeto de cliente) a medicao nao para, muda de
destino. As ferramentas que sofrem o atrito moram em APP_ROOT e ficam fora do
alcance de escrita, logo nao ha ali nada para melhorar - prometer melhoria seria
mentira. O atrito vai para um caderno que vive na pasta do proprio Axio
(APP_ROOT/.axio/melhorias_pendentes.json), deduplicado por facto e com contador
de vezes, porque um atrito que reaparece em projetos diferentes e mais grave do
que um que apareceu uma vez. O projeto do cliente nao recebe ficheiro nenhum, e a
nota nao precisa de ser levada a mao para casa: nasce no sitio onde vai ser lida,
e aparece-me uma vez por arranque, na primeira rodada em que a pasta aberta volta
a ser a do Axio.
"""

import json
import os
import threading
import time

from src.backend.config import APP_ROOT
from src.backend.services.persistencia import gravar_json_atomico
from src.backend.state import caminho_estado_projeto, estado, no_diretorio_do_axio

LIMITE_CHAMADAS = 18
LIMITE_REPETICOES = 3
LIMITE_MESMA_FERRAMENTA = 8
LIMITE_REGISTROS = 20
LIMITE_PENDENTES = 40
LIMITE_PENDENTES_MOSTRADAS = 12
NOME_ARQUIVO = "atrito.json"
NOME_PENDENTES = "melhorias_pendentes.json"
PASTA_ESTADO_AXIO = ".axio"

_radar = {"chamadas": [], "lock": threading.Lock()}
_rodadas = {"fechadas": 0, "ultimos_fatos": [], "pendentes_mostradas": False}


def _caminho():
    return caminho_estado_projeto(NOME_ARQUIVO)


def _caminho_pendentes():
    """Caderno de atrito fora do Axio: nasce na pasta do Axio, nunca no projeto aberto."""
    return os.path.join(APP_ROOT, PASTA_ESTADO_AXIO, NOME_PENDENTES)


def _ler_lista(caminho, chave):
    if not caminho or not os.path.exists(caminho):
        return []
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)
    except (OSError, ValueError):
        return []
    itens = dados.get(chave) if isinstance(dados, dict) else None
    return itens if isinstance(itens, list) else []


def _gravar_lista(caminho, chave, itens):
    """Grava de forma ATOMICA: a injecao le este ficheiro de outra thread."""
    if not caminho:
        return
    try:
        gravar_json_atomico(caminho, {chave: itens})
    except OSError:
        pass


def _ler_registros():
    return _ler_lista(_caminho(), "registros")


def _ler_pendentes():
    return _ler_lista(_caminho_pendentes(), "pendentes")


def _gravar_registros(registros):
    _gravar_lista(_caminho(), "registros", registros)


def _acumular_pendentes(fatos, total_chamadas):
    """Guarda no caderno do Axio o atrito medido num projeto onde nao posso melhorar nada.

    Deduplica por facto e conta as vezes: sem a contagem, o mesmo atrito repetido
    em cinco projetos ficaria com o mesmo peso de um que apareceu uma unica vez, e
    a ordem de trabalho que eu leio no fim seria a do acaso.
    """
    pendentes = _ler_pendentes()
    por_facto = {}
    for p in pendentes:
        por_facto.setdefault(p.get("facto"), p)
    projeto = os.path.basename(os.path.normpath(estado.get("pasta_raiz", ""))) or "?"
    quando = time.strftime("%Y-%m-%d %H:%M:%S")
    for facto in fatos:
        existente = por_facto.get(facto)
        if existente is None:
            registro = {
                "facto": facto,
                "projeto": projeto,
                "quando": quando,
                "vezes": 1,
                "chamadas": total_chamadas,
            }
            pendentes.append(registro)
            por_facto[facto] = registro
        else:
            existente["vezes"] = int(existente.get("vezes") or 1) + 1
            existente["quando"] = quando
            existente["projeto"] = projeto
    _gravar_lista(_caminho_pendentes(), "pendentes", pendentes[-LIMITE_PENDENTES:])


def registrar_uso_ferramenta(nome, args=None):
    """Conta uma chamada de ferramenta na rodada em curso. So RAM, sem IO.

    Chamado no ponto unico por onde passa toda a chamada de ferramenta, por isso
    nao ha caminho que escape a medicao - inclusive fora do Axio, onde o atrito
    nao se perde: vai para o caderno de melhorias adiadas.
    """
    try:
        chave = json.dumps(args or {}, sort_keys=True, ensure_ascii=False, default=str)[:400]
    except (TypeError, ValueError):
        chave = ""
    with _radar["lock"]:
        _radar["chamadas"].append((str(nome), chave))


def _fatos(chamadas):
    """Atrito da rodada, do mais acionavel para o menos. Lista vazia = rodada limpa.

    Tres sinais, todos medidos e nenhum inferido: a chamada IDENTICA repetida (a
    mesma ferramenta com os mesmos argumentos - sinal de que ela nao devolveu o
    que era preciso), a mesma ferramenta muitas vezes na rodada (varredura
    item-a-item, tipico de busca que devia aceitar lote) e o volume total.
    """
    if not chamadas:
        return []
    total = len(chamadas)
    identicas = {}
    por_ferramenta = {}
    for nome, chave in chamadas:
        identicas[(nome, chave)] = identicas.get((nome, chave), 0) + 1
        por_ferramenta[nome] = por_ferramenta.get(nome, 0) + 1

    fatos = []
    repetidas = [(k, n) for k, n in identicas.items() if n >= LIMITE_REPETICOES]
    if repetidas:
        (pior_nome, _), pior_n = max(repetidas, key=lambda kv: kv[1])
        fatos.append(
            f"{len(repetidas)} chamada(s) IDENTICA(s) repetida(s) - a pior: {pior_nome} {pior_n}x com os "
            "mesmos argumentos (a ferramenta nao devolveu o que voce precisava?)"
        )
    for nome, n in sorted(por_ferramenta.items(), key=lambda kv: (-kv[1], kv[0])):
        if n >= LIMITE_MESMA_FERRAMENTA:
            fatos.append(f"{nome} chamada {n}x na mesma rodada (varredura item-a-item: falta busca em lote?)")
    if total >= LIMITE_CHAMADAS:
        fatos.append(f"{total} chamadas de ferramenta na rodada")
    return fatos


def fechar_rodada():
    """Fecha a rodada: mede o atrito, guarda-o onde faz sentido e zera o acumulador.

    Chamada no ponto unico de saida do laco do agente. Dentro do Axio o registo
    fica no projeto e alimenta o aviso da rodada seguinte; fora dele vai para o
    caderno de melhorias adiadas, porque o projeto aberto nao tem o que melhorar.
    Devolve os factos medidos (lista vazia quando a rodada foi limpa).
    """
    with _radar["lock"]:
        chamadas = list(_radar["chamadas"])
        del _radar["chamadas"][:]
    _rodadas["fechadas"] += 1
    fatos = _fatos(chamadas)
    _rodadas["ultimos_fatos"] = fatos
    if not fatos:
        return []
    if not no_diretorio_do_axio():
        _acumular_pendentes(fatos, len(chamadas))
        return fatos
    registros = _ler_registros()
    registros.append({
        "rodada": _rodadas["fechadas"],
        "quando": time.strftime("%Y-%m-%d %H:%M:%S"),
        "chamadas": len(chamadas),
        "fatos": fatos,
    })
    _gravar_registros(registros[-LIMITE_REGISTROS:])
    return fatos


def bloco_atrito():
    """Bloco de auto-melhoria injetado no prompt. Devolve "" quando nao ha nada a apontar.

    Dois mundos, dois blocos. Dentro do Axio vale a regra do registo unico da
    rodada anterior, mais o caderno de melhorias adiadas uma vez por arranque.
    Fora dele nao ha registo nenhum a ler: os factos da rodada que acabou vivem em
    RAM, sao mostrados uma vez e o que fica por fazer ja esta no caderno.
    """
    return _bloco_casa() if no_diretorio_do_axio() else _bloco_fora()


def _bloco_fora():
    fatos = _rodadas["ultimos_fatos"]
    if not fatos:
        return ""
    linhas = "\n".join(f"- {f}" for f in fatos)
    return (
        "=== ATRITO MEDIDO NA SUA RODADA ANTERIOR (regra 26 suspensa: estou noutro projeto) ===\n"
        f"{linhas}\n"
        "Estas ferramentas moram no Axio e ficam fora deste projeto: eu NAO as posso editar aqui. O facto ja\n"
        "ficou guardado no caderno de melhorias adiadas do Axio. No fim da resposta escreva uma linha curta\n"
        "'AUTO-MELHORIA (adiada): <o que faltou, numa frase>' e siga a tarefa do utilizador.\n"
        "==============================\n"
    )


def _bloco_casa():
    return _bloco_registro_da_rodada() + _bloco_pendentes()


def _bloco_registro_da_rodada():
    registros = _ler_registros()
    if not registros:
        return ""
    ultimo = registros[-1]
    if ultimo.get("rodada") != _rodadas["fechadas"]:
        return ""
    fatos = ultimo.get("fatos") or []
    if not fatos:
        return ""
    linhas = "\n".join(f"- {f}" for f in fatos)
    return (
        "=== ATRITO MEDIDO NA SUA RODADA ANTERIOR (auto-melhoria, regra 26) ===\n"
        f"{linhas}\n"
        "Isto e a medicao do seu proprio uso das ferramentas, nao uma ordem. Se o atrito vier de uma ferramenta\n"
        "que nao responde o que voce precisa, MELHORE-A ou crie a que falta NESTA rodada (depois de cumprir o\n"
        "pedido do usuario) e reporta-a no bloco AUTO-MELHORIA do fim da resposta. Se se explica pela propria tarefa\n"
        "(ex: ler quatro trechos distintos do mesmo ficheiro), nao e atrito: nao escrevas bloco nenhum.\n"
        "==============================\n"
    )


def _bloco_pendentes():
    """Mostra uma vez por arranque o que ficou por melhorar enquanto eu estava fora."""
    if _rodadas["pendentes_mostradas"]:
        return ""
    pendentes = _ler_pendentes()
    if not pendentes:
        return ""
    _rodadas["pendentes_mostradas"] = True
    linhas = []
    for p in pendentes[-LIMITE_PENDENTES_MOSTRADAS:]:
        vezes = int(p.get("vezes") or 1)
        contagem = f" (x{vezes})" if vezes > 1 else ""
        linhas.append(f"- [{p.get('projeto', '?')}] {p.get('facto', '')}{contagem}")
    corpo = "\n".join(linhas)
    return (
        f"=== MELHORIAS ADIADAS DE OUTROS PROJETOS ({len(pendentes)} no caderno) ===\n"
        f"{corpo}\n"
        "Este e o atrito que eu proprio medi enquanto trabalhava fora do Axio, guardado em\n"
        f"'{PASTA_ESTADO_AXIO}/{NOME_PENDENTES}'. Nao e ordem para esta rodada: quando o pedido do utilizador\n"
        "permitir, escolha o que render mais e melhore-o (regra 26); o que resolver, apague do ficheiro.\n"
        "==============================\n"
    )
