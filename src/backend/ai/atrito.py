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
mentira. O que fica por fazer vai para um caderno LEGIVEL na pasta do proprio
Axio (APP_ROOT/gerados/coder/auto-melhoria/pendentes.md), uma linha por melhoria,
que eu leio e edito como qualquer ficheiro de texto. La entram duas coisas: o que
eu proprio anoto na resposta com 'AUTO-MELHORIA (adiada): ...' (gravado sozinho no
fim da rodada) e o atrito que o radar resume por ferramenta. O projeto do cliente
nao recebe ficheiro nenhum, e a nota nasce no sitio onde vai ser lida: volta-me
sozinha quando a pasta aberta torna a ser a do Axio.
"""

import json
import os
import re
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
LIMITE_DO_FACTO = 300
NOME_ARQUIVO = "atrito.json"
NOME_PENDENTES = "pendentes.md"
NOME_PENDENTES_ANTIGO = "melhorias_pendentes.json"
PASTA_ESTADO_AXIO = ".axio"
PASTA_PENDENTES = os.path.join("gerados", "coder", "auto-melhoria")
CABECALHO_PENDENTES = (
    "# Melhorias pendentes do Axio Coder\n"
    "\n"
    "O que eu proprio anotei enquanto trabalhava noutros projetos, mais o atrito que\n"
    "o radar resumiu por ferramenta. Uma linha por melhoria; cada linha resolvida sai\n"
    "daqui, e enquanto houver linha o caderno e injetado ao abrir a pasta do Coder.\n"
    "\n"
)

_radar = {"chamadas": [], "lock": threading.Lock()}
_rodadas = {"fechadas": 0, "ultimos_fatos": [], "pendentes_mostradas": False}


def _caminho():
    return caminho_estado_projeto(NOME_ARQUIVO)


def _caminho_pendentes():
    """Caderno de melhorias do Axio: nasce na pasta do Axio, nunca no projeto aberto.

    O caminho e absoluto de proposito: o caderno pertence ao Axio mesmo quando a
    pasta aberta e de outro projeto, logo nao pode depender da pasta da vez.
    """
    return os.path.join(APP_ROOT, PASTA_PENDENTES, NOME_PENDENTES)


def caminho_do_caderno():
    """Onde vive o caderno: a instrucao do sistema e o relatorio citam-no."""
    return _caminho_pendentes()


_LINHA_PENDENTE = re.compile(r"^-\s*\[([^\]]*)\]\s*(?:\(x(\d+)\)\s*)?(.+?)\s*$")
_RE_MESMA_FERRAMENTA = re.compile(r"^(\w+) chamada (\d+)x na mesma rodada")
_RE_IDENTICAS = re.compile(r"^\d+ chamada\(s\) IDENTICA\(s\).*?a pior: (\w+) (\d+)x")
_RE_VOLUME = re.compile(r"^\d+ chamadas de ferramenta na rodada$")
_RE_LOTE_RESUMIDO = re.compile(r"^(\w+): ate (\d+)x numa rodada")
_RE_IDENTICAS_RESUMIDO = re.compile(r"^(\w+): ate (\d+)x com os mesmos argumentos")
_RE_CONTA = re.compile(r"ate (\d+)x")
_RE_MELHORIA_ANOTADA = re.compile(
    r"(?m)^[ \t|>*_#-]*AUTO-MELHORIA\s*\((?:adiada|nao corrigida)\)\s*:[ \t]*(.+?)[ \t|*]*$",
    re.IGNORECASE,
)


def _normalizar_facto(facto):
    """Resume um facto do radar numa linha acionavel: devolve (chave, texto) ou None.

    O radar repete o mesmo defeito a cada rodada ("tool_x chamada 83x", "tool_x
    chamada 51x"), e quarenta linhas dessas nao sao um caderno: sao um contador.
    Ao voltar ao Axio o que interessa e a PIOR contagem por ferramenta, num titulo
    que diga o que fazer. O volume total da rodada nao entra: nao e acionavel.
    """
    texto = str(facto or "").strip()
    if not texto or _RE_VOLUME.match(texto):
        return None
    m = _RE_MESMA_FERRAMENTA.match(texto) or _RE_LOTE_RESUMIDO.match(texto)
    if m:
        return f"ferramenta:{m.group(1)}", f"{m.group(1)}: ate {m.group(2)}x numa rodada (falta lote ou melhor retorno?)"
    m = _RE_IDENTICAS.match(texto) or _RE_IDENTICAS_RESUMIDO.match(texto)
    if m:
        return f"identicas:{m.group(1)}", f"{m.group(1)}: ate {m.group(2)}x com os mesmos argumentos (nao devolveu o que era preciso?)"
    return f"facto:{texto[:120].lower()}", texto[:LIMITE_DO_FACTO]


def _conta_do_facto(texto):
    m = _RE_CONTA.search(str(texto or ""))
    return int(m.group(1)) if m else 0


def _ler_pendentes():
    caminho = _caminho_pendentes()
    if not os.path.exists(caminho):
        _migrar_pendentes_antigos()
    if not os.path.exists(caminho):
        return []
    itens = []
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            for linha in f:
                m = _LINHA_PENDENTE.match(linha.strip())
                if not m:
                    continue
                normal = _normalizar_facto(m.group(3))
                if not normal:
                    continue
                chave, texto = normal
                itens.append({
                    "chave": chave,
                    "projeto": m.group(1),
                    "vezes": int(m.group(2) or 1),
                    "facto": texto,
                })
    except OSError:
        return []
    return itens


def _gravar_pendentes(itens):
    caminho = _caminho_pendentes()
    try:
        os.makedirs(os.path.dirname(caminho), exist_ok=True)
        linhas = [CABECALHO_PENDENTES]
        for p in itens:
            vezes = int(p.get("vezes") or 1)
            contagem = f"(x{vezes}) " if vezes > 1 else ""
            linhas.append(f"- [{p.get('projeto') or '?'}] {contagem}{p.get('facto', '')}\n")
        temporario = caminho + ".tmp"
        with open(temporario, "w", encoding="utf-8") as f:
            f.write("".join(linhas))
        os.replace(temporario, caminho)
    except OSError:
        pass


def _migrar_pendentes_antigos():
    """O caderno era um JSON de contadores em .axio/; vira a lista legivel em gerados/coder/.

    A agregacao acontece na migracao, e nao na leitura, para o ficheiro nascer ja
    no formato que eu vou ler: uma linha por problema, nao uma por rodada.
    """
    antigo = os.path.join(APP_ROOT, PASTA_ESTADO_AXIO, NOME_PENDENTES_ANTIGO)
    if not os.path.exists(antigo):
        return
    itens = []
    por_chave = {}
    for velho in _ler_lista(antigo, "pendentes"):
        normal = _normalizar_facto(velho.get("facto"))
        if not normal:
            continue
        chave, texto = normal
        existente = por_chave.get(chave)
        if existente is None:
            registro = {
                "chave": chave,
                "projeto": velho.get("projeto") or "?",
                "vezes": int(velho.get("vezes") or 1),
                "facto": texto,
            }
            itens.append(registro)
            por_chave[chave] = registro
            continue
        existente["vezes"] += int(velho.get("vezes") or 1)
        if _conta_do_facto(texto) >= _conta_do_facto(existente["facto"]):
            existente["facto"] = texto
            existente["projeto"] = velho.get("projeto") or existente["projeto"]
    _gravar_pendentes(itens[-LIMITE_PENDENTES:])
    try:
        os.remove(antigo)
    except OSError:
        pass


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


def _gravar_registros(registros):
    _gravar_lista(_caminho(), "registros", registros)


def _registar_no_caderno(factos):
    """Acrescenta factos ao caderno, um por PROBLEMA, com o numero de rodadas em que voltou.

    O radar mede por rodada e o caderno guarda por problema: o mesmo defeito que
    reaparece em cinco projetos fica numa linha so, com a pior contagem, e nao em
    cinco linhas iguais que escondem o resto.
    """
    pendentes = _ler_pendentes()
    por_chave = {p["chave"]: p for p in pendentes}
    projeto = os.path.basename(os.path.normpath(estado.get("pasta_raiz", ""))) or "?"
    for facto in factos:
        normal = _normalizar_facto(facto)
        if not normal:
            continue
        chave, texto = normal
        existente = por_chave.get(chave)
        if existente is None:
            registro = {"chave": chave, "projeto": projeto, "vezes": 1, "facto": texto}
            pendentes.append(registro)
            por_chave[chave] = registro
            continue
        existente["vezes"] = int(existente.get("vezes") or 1) + 1
        if _conta_do_facto(texto) >= _conta_do_facto(existente.get("facto")):
            existente["facto"] = texto
            existente["projeto"] = projeto
    _gravar_pendentes(pendentes[-LIMITE_PENDENTES:])


def _anotar_melhorias(texto_final):
    """Passa para o caderno as linhas 'AUTO-MELHORIA (adiada): ...' escritas na resposta.

    E o caminho pelo qual uma melhoria que eu decidi adiar sobrevive sozinha: eu
    escrevo a linha no chat e o fim da rodada grava-a, sem eu ter de abrir o
    ficheiro do caderno a mao enquanto trabalho noutro projeto.
    """
    achadas = []
    for m in _RE_MELHORIA_ANOTADA.finditer(str(texto_final or "")):
        facto = m.group(1).strip().strip("-: ").strip()
        if facto and facto[:LIMITE_DO_FACTO].lower() not in (v.lower() for v in achadas):
            achadas.append(facto[:LIMITE_DO_FACTO])
    if achadas:
        _registar_no_caderno(achadas)


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


def fechar_rodada(texto_final=""):
    """Fecha a rodada: mede o atrito, guarda-o onde faz sentido e zera o acumulador.

    Chamada no ponto unico de saida do laco do agente. Dentro do Axio o registo
    fica no projeto e alimenta o aviso da rodada seguinte; fora dele vai para o
    caderno de melhorias adiadas, porque o projeto aberto nao tem o que melhorar.
    O texto da resposta entra aqui por um motivo so: as linhas 'AUTO-MELHORIA
    (adiada): ...' que eu escrevi sao o que alimenta o caderno.
    Devolve os factos medidos (lista vazia quando a rodada foi limpa).
    """
    with _radar["lock"]:
        chamadas = list(_radar["chamadas"])
        del _radar["chamadas"][:]
    _rodadas["fechadas"] += 1
    fatos = _fatos(chamadas)
    _rodadas["ultimos_fatos"] = fatos
    _anotar_melhorias(texto_final)
    if not fatos:
        return []
    if not no_diretorio_do_axio():
        _registar_no_caderno(fatos)
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


def ao_abrir_projeto():
    """Reabre a janela do caderno quando a pasta aberta muda sem reiniciar o backend.

    Sem isto, quem trabalha num projeto, volta ao Axio e troca outra vez de pasta
    na mesma sessao veria o caderno uma unica vez, na primeira pasta de todas.
    """
    _rodadas["pendentes_mostradas"] = False


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
    """Injeta o caderno de melhorias ao abrir o Axio, e depois mantem-no a vista.

    A lista completa sai uma vez por abertura de pasta (custa contexto); a partir
    dai o lembrete e uma linha, para o trabalho pendente nao desaparecer so porque
    eu ainda nao o acabei. Ao mudar de pasta, a lista volta a sair inteira.
    """
    pendentes = _ler_pendentes()
    if not pendentes:
        return ""
    caminho = _caminho_pendentes()
    if _rodadas["pendentes_mostradas"]:
        return (
            f"=== CADERNO DO AXIO: {len(pendentes)} melhoria(s) pendente(s) ===\n"
            f"Lista em '{caminho}'. Aplique as que faltam depois de atender o pedido do utilizador\n"
            "e apague do ficheiro cada linha resolvida. Nao repita esta lista no chat.\n"
            "==============================\n"
        )
    _rodadas["pendentes_mostradas"] = True
    linhas = []
    for p in pendentes[-LIMITE_PENDENTES_MOSTRADAS:]:
        vezes = int(p.get("vezes") or 1)
        contagem = f" (x{vezes})" if vezes > 1 else ""
        linhas.append(f"- [{p.get('projeto', '?')}]{contagem} {p.get('facto', '')}")
    corpo = "\n".join(linhas)
    return (
        f"=== MELHORIAS PENDENTES DO AXIO ({len(pendentes)} no caderno) ===\n"
        f"{corpo}\n"
        f"Caderno: '{caminho}' (ficheiro de texto, editavel).\n"
        "Isto e o que eu proprio anotei enquanto trabalhava noutros projetos. Fluxo, por esta ordem:\n"
        "1. O pedido do utilizador vem PRIMEIRO; nada disto se faz antes de ele estar atendido.\n"
        "2. No FIM desta resposta, diga em uma linha que ha N melhorias pendentes e que comeca por\n"
        "   elas na rodada seguinte - sem parar o trabalho pedido agora.\n"
        "3. A partir da rodada seguinte, aplique as que renderem mais (com a prova de sempre) e APAGUE\n"
        "   do ficheiro cada linha resolvida (tool_substituir_texto no proprio caderno).\n"
        "4. Linha que ja nao se aplica tambem sai: apague-a em vez de a deixar envelhecer la.\n"
        "==============================\n"
    )
