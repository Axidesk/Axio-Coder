"""Combate: le um log de combate e mede-o - e compara dois lado a lado."""

import difflib
import math
import os
import re
import statistics

from src.backend.tools.registry import register

_PERCENTIS = (0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0)
_CASAS = {"duração", "dano/s", "cura/s", "líquido/s", "média", "mediana", "máx", "vida mín"}
_LINHA_TEMPO_VIDEO = re.compile(r"^(\d+):(\d+)\.(\d+)$")
_LINHA_TEMPO_SERVIDOR = re.compile(r"^(\d+):(\d+):(\d+)\.(\d+)\s+(.*)$")
_DANO_SERVIDOR = re.compile(r"^dano\s+(.+?)\s+->\s+(.+?)\s+tipo=(\w+)\s+valor=(-?\d+)")
_DEFESA_SERVIDOR = re.compile(r"^defesa\s+(.+?)\s+tipo=(\w+).*?bruto=(\d+)")
_CURA_SERVIDOR = re.compile(r"^cura\s+(.+?)\s+\+(\d+)")
_CAUSADO_VIDEO = re.compile(r"causado\s+(\d+)\s+a\s+(.+)$")
_SOFRIDO_VIDEO = re.compile(r"sofrido\s+(\d+)\s+de\s+(.+)$")


def _caminho_ausente(caminho):
    """Diz que o arquivo nao existe E quais os parecidos que estao na mesma pasta."""
    pasta = os.path.dirname(caminho) or "."
    try:
        vizinhos = [nome for nome in os.listdir(pasta) if os.path.isfile(os.path.join(pasta, nome))]
    except OSError:
        return f"o arquivo '{caminho}' nao existe e a pasta '{pasta}' nao pode ser lida."
    alvo = os.path.basename(caminho)
    parecidos = difflib.get_close_matches(alvo, vizinhos, n=3, cutoff=0.4)
    if not parecidos:
        parecidos = [nome for nome in vizinhos if alvo.split()[0].lower() in nome.lower()][:5]
    if not parecidos:
        return f"o arquivo '{caminho}' nao existe e nao ha nenhum parecido em '{pasta}'."
    return f"o arquivo '{caminho}' nao existe. Parecidos em '{pasta}': " + ", ".join(parecidos) + "."


def _ler_eventos(caminho):
    if not os.path.isfile(caminho):
        raise FileNotFoundError(_caminho_ausente(caminho))
    with open(caminho, encoding="utf-8", errors="replace") as ficheiro:
        linhas = [linha.rstrip("\n") for linha in ficheiro]
    uteis = [linha.strip() for linha in linhas if linha.strip()]
    if not uteis:
        return [], "vazio"
    for linha in uteis:
        if _LINHA_TEMPO_VIDEO.match(linha):
            return _eventos_do_video(uteis)
        if _LINHA_TEMPO_SERVIDOR.match(linha):
            return _eventos_do_servidor(uteis)
    raise ValueError(
        "formato nao reconhecido: esperava 'HH:MM:SS.mmm <mensagem>' (log do servidor) "
        "ou 'MM:SS.cc' numa linha propria (transcricao do TibiaCam). "
        f"O ficheiro tem {len(uteis)} linhas uteis e nenhuma delas e um instante. "
        f"Primeira linha: {uteis[0][:80]!r}"
    )


def _eventos_do_video(uteis):
    eventos, atual = [], None
    for linha in uteis:
        casamento = _LINHA_TEMPO_VIDEO.match(linha)
        if casamento:
            if atual is not None:
                eventos.append(atual)
            segundos = int(casamento.group(1)) * 60 + int(casamento.group(2))
            atual = (segundos + int(casamento.group(3)) / 100, [])
        elif atual is not None and not re.match(r"^\d+%$", linha):
            atual[1].append(linha)
    if atual is not None:
        eventos.append(atual)
    return eventos, "video"


def _eventos_do_servidor(uteis):
    eventos = []
    for linha in uteis:
        casamento = _LINHA_TEMPO_SERVIDOR.match(linha)
        if not casamento:
            continue
        segundos = (
            int(casamento.group(1)) * 3600
            + int(casamento.group(2)) * 60
            + int(casamento.group(3))
            + int(casamento.group(4)) / 1000
        )
        eventos.append((segundos, [casamento.group(5)]))
    return eventos, "servidor"


def _alvo_provavel(eventos, formato):
    contagem = {}
    for _, campos in eventos:
        texto = " ".join(campos)
        if formato == "servidor":
            casamento = _DANO_SERVIDOR.match(texto)
            if casamento and casamento.group(3) == "fisico":
                nome = casamento.group(2)
                contagem[nome] = contagem.get(nome, 0) + 2
            continue
        valor = _CAUSADO_VIDEO.search(texto)
        if valor and campos and campos[0] == "melee":
            nome = valor.group(2)
            contagem[nome] = contagem.get(nome, 0) + 2
            continue
        sofrido = _SOFRIDO_VIDEO.search(texto)
        if sofrido and "veneno" not in campos:
            nome = sofrido.group(2).strip()
            contagem[nome] = contagem.get(nome, 0) + 2
    if not contagem:
        return ""
    return max(contagem.items(), key=lambda par: par[1])[0]


def _medir(eventos, alvo, formato, direcao=""):
    puffs, sparks, curas, vidas = 0, 0, [], []
    levados, instantes_levar, atacados, instantes_atacar = [], [], [], []
    for segundos, campos in eventos:
        texto = " ".join(campos)
        if formato == "servidor":
            casamento = _DANO_SERVIDOR.match(texto)
            if casamento and casamento.group(2) == alvo and casamento.group(3) == "fisico":
                valor = int(casamento.group(4))
                if valor > 0:
                    levados.append(valor)
                    instantes_levar.append(segundos)
                if valor <= 0:
                    continue
                vida = re.search(r"hp=(\d+)/", texto)
                if vida:
                    vidas.append(int(vida.group(1)))
                continue
            casamento = _DEFESA_SERVIDOR.match(texto)
            if casamento and casamento.group(1) == alvo:
                if casamento.group(2) == "escudo":
                    puffs += 1
                else:
                    sparks += 1
                instantes_levar.append(segundos)
                continue
            casamento = _CURA_SERVIDOR.match(texto)
            if casamento and casamento.group(1) == alvo:
                curas.append(int(casamento.group(2)))
                vida = re.search(r"hp=(\d+)/", texto)
                if vida:
                    vidas.append(int(vida.group(1)))
            continue

        primeiro = campos[0] if campos else ""
        if primeiro in ("defesa", "bloqueio") and len(campos) > 1 and campos[1] == alvo:
            if primeiro == "defesa":
                puffs += 1
            else:
                sparks += 1
            instantes_levar.append(segundos)
        elif primeiro == "cura" and any(alvo in campo for campo in campos[1:]):
            valor = re.search(r"curou\s+(\d+)", " ".join(campos))
            if valor:
                curas.append(int(valor.group(1)))
        else:
            for campo in campos:
                if "veneno" in campo or "poison" in campo:
                    continue
                valor = _CAUSADO_VIDEO.search(campo)
                if valor and valor.group(2).strip() == alvo:
                    levados.append(int(valor.group(1)))
                    instantes_levar.append(segundos)
                    continue
                sofrido = _SOFRIDO_VIDEO.search(campo)
                if sofrido and sofrido.group(2).strip() == alvo:
                    atacados.append(int(sofrido.group(1)))
                    instantes_atacar.append(segundos)

    if formato == "servidor":
        acertos, instantes, a_atacar = levados, instantes_levar, False
    else:
        quer_atacar = direcao == "atacar" or (not direcao and len(atacados) > len(levados))
        if quer_atacar:
            acertos, instantes, a_atacar = atacados, instantes_atacar, True
        else:
            acertos, instantes, a_atacar = levados, instantes_levar, False
    tentativas = len(acertos) if a_atacar else len(acertos) + puffs + sparks
    duracao = eventos[-1][0] - eventos[0][0] if len(eventos) > 1 else 0
    if not acertos or not tentativas or duracao <= 0:
        return None
    instantes.sort()
    intervalos = [b - a for a, b in zip(instantes, instantes[1:])]
    intervalos = [valor for valor in intervalos if valor < 8]

    def parte(limite, acima):
        total = sum(1 for valor in acertos if (valor >= limite if acima else valor < limite))
        return 100.0 * total / len(acertos)

    ordenados = sorted(acertos)
    dano_total = sum(acertos)
    cura_total = sum(curas)
    taxa_defesa = 0.0 if a_atacar else (puffs + sparks) / tentativas
    margem = 196.0 * math.sqrt(taxa_defesa * (1.0 - taxa_defesa) / tentativas) if tentativas else 0.0
    return {
        "alvo": alvo,
        "direção": "atacar" if a_atacar else "levar",
        "duração": duracao,
        "tentativas": tentativas,
        "por_minuto": 60.0 * tentativas / duracao,
        "acerta": 100.0 if a_atacar else 100.0 * len(acertos) / tentativas,
        "puff": 0.0 if a_atacar else 100.0 * puffs / tentativas,
        "spark": 0.0 if a_atacar else 100.0 * sparks / tentativas,
        "defesa": 100.0 * taxa_defesa,
        "margem": margem,
        "média": dano_total / len(acertos),
        "mediana": statistics.median(acertos),
        "máx": max(acertos),
        "mín": min(acertos),
        "p10": ordenados[int(len(ordenados) * 0.1)],
        "p90": ordenados[min(len(ordenados) - 1, int(len(ordenados) * 0.9))],
        "abaixo50": parte(50, False),
        "acima100": parte(100, True),
        "acima130": parte(130, True),
        "acima150": parte(150, True),
        "curas": len(curas),
        "curas_min": 60.0 * len(curas) / duracao,
        "cura_média": (cura_total / len(curas)) if curas else 0.0,
        "dano_s": dano_total / duracao,
        "cura_s": cura_total / duracao,
        "intervalo": statistics.median(intervalos) if intervalos else 0.0,
        "vida_min": min(vidas) if vidas else None,
        "ritmo_suspeito": formato == "video" and 60.0 * tentativas / duracao > 33,
    }


def _numero(chave, valor):
    if valor is None:
        return "—"
    if chave in ("acerta", "puff", "spark", "defesa", "abaixo50", "acima100", "acima130", "acima150"):
        return f"{valor:.1f}%"
    if chave == "margem":
        return f"+-{valor:.1f}"
    if chave == "duração":
        return f"{valor:.0f}s"
    if chave in ("tentativas", "curas", "máx", "p10", "p90"):
        return f"{valor:.0f}"
    return f"{valor:.1f}"


_ROTULOS = [
    ("alvo", "alvo"),
    ("duração", "duração"),
    ("tentativas", "tentativas"),
    ("por_minuto", "tentativas/min"),
    ("acerta", "acerta"),
    ("puff", "puff (escudo)"),
    ("spark", "spark (armadura)"),
    ("defesa", "defesa total"),
    ("margem", "margem 95%"),
    ("média", "golpe médio"),
    ("mediana", "golpe mediano"),
    ("máx", "golpe máximo"),
    ("abaixo50", "<50"),
    ("acima100", ">=100"),
    ("acima130", ">=130"),
    ("acima150", ">=150"),
    ("curas", "curas"),
    ("curas_min", "curas/min"),
    ("cura_média", "cura média"),
    ("dano_s", "dano/s"),
    ("cura_s", "cura/s"),
    ("intervalo", "intervalo entre tentativas"),
]


def _tabela(nomes, medidas):
    a_atacar = any(medida.get("direção") == "atacar" for medida in medidas)
    saltar = {"acerta", "puff", "spark", "defesa", "margem"} if a_atacar else set()
    largura = max(len(rotulo) for _, rotulo in _ROTULOS) + 1
    colunas = max(len(nome) for nome in nomes) + 2
    cabecalho = " " * largura + "".join(nome.rjust(colunas) for nome in nomes)
    linhas = [cabecalho]
    for chave, rotulo in _ROTULOS:
        if chave in saltar:
            continue
        if chave == "tentativas" and a_atacar:
            rotulo = "golpes que acertam"
        valores = []
        for medida in medidas:
            if chave == "alvo":
                nome = medida.get("alvo", "—")
                if medida.get("direção") == "atacar":
                    nome += " (a atacar)"
                valores.append(nome)
            elif chave in ("tentativas", "curas"):
                valores.append(str(medida.get(chave, 0)))
            elif chave == "duração":
                valores.append(f"{medida.get(chave, 0):.0f}s")
            else:
                valores.append(_numero(chave, medida.get(chave)))
        linhas.append(rotulo.ljust(largura) + "".join(valor.rjust(colunas) for valor in valores))
    if any(medida.get("ritmo_suspeito") for medida in medidas):
        linhas.append("")
        linhas.append("AVISO DE RITMO: mais de 33 tentativas/min (menos de 1,8s entre golpes).")
        linhas.append("O cliente 7.4 ataca de 2 em 2 segundos, logo a contagem esta inflada:")
        linhas.append("'defesa X' e 'bloqueio X' sao ambos X A DEFENDER - nao somar o bloqueio do oponente.")
    return "\n".join(linhas)


def _efeito(medida):
    liquido = medida["dano_s"] - medida["cura_s"]
    if liquido <= 0:
        return (
            "A cura empata ou passa o dano: ele nunca morre sem a sorte o trair "
            f"(dano {medida['dano_s']:.1f}/s menos cura {medida['cura_s']:.1f}/s)."
        )
    return (
        f"Liquido {liquido:.1f} HP/s -> {1000 / liquido:.0f}s para gastar 1000 de vida "
        f"(dano {medida['dano_s']:.1f}/s menos cura {medida['cura_s']:.1f}/s)."
    )


def _curto(caminho):
    base = caminho.replace("\\", "/").rsplit("/", 1)[-1]
    if "." in base:
        base = base.rsplit(".", 1)[0]
    if base.lower().startswith("combate"):
        base = base.replace("combate-", "")
    return base[:17]


@register(
    "tool_analisar_combate",
    "Le um log de combate e mede-o, sem contar nada a mao. Aceita os DOIS formatos: o log do "
    "proprio servidor ('HH:MM:SS.mmm dano/defesa/cura ...') e a transcricao do TibiaCam "
    "('10:45.26 / 91% / melee / causado 83 a banshee'). Devolve o que decide o balanceamento: "
    "duracao, tentativas por minuto, quanto ACERTA, quanto e ANULADO pelo escudo (puff) e pela "
    "armadura (spark), o golpe medio/mediano/maximo, a cauda (<50, >=100, >=130, >=150), as curas "
    "por minuto com o valor medio, e o LIQUIDO em HP/s - dano por segundo menos cura por segundo, "
    "que e o numero que explica por que um combate dura o que dura (dois numeros grandes que se "
    "anulam: quando o liquido fica perto de zero, o bicho so morre por azar). Com 'comparar_com' "
    "poe os dois lado a lado na mesma tabela, ja alinhados - e o caminho para julgar um teste "
    "contra a gravacao de referencia sem escrever um leitor de log em cada rodada. O alvo e "
    "detetado sozinho (a criatura que mais defende), mas pode ser dado em 'alvo'.",
    {
        "caminhos": {
            "tipo": "STRING",
            "desc": "Um ou mais ficheiros a medir, um por linha (log do servidor ou transcricao do TibiaCam). Vários são somados como se fossem um combate só.",
            "obrig": True,
            "padrao": "",
        },
        "alvo": {
            "tipo": "STRING",
            "desc": "Nome da criatura que leva os golpes (ex: 'banshee'). Vazio deteta sozinho pela que mais defende.",
            "padrao": "",
        },
        "comparar_com": {
            "tipo": "STRING",
            "desc": "Um segundo ficheiro (ou vários, um por linha) para a tabela lado a lado. E o caminho para comparar o teste de agora com a gravacao de referencia.",
            "padrao": "",
        },
        "direcao": {
            "tipo": "STRING",
            "desc": "Sentido a medir, quando o alvo aparece nos dois: 'levar' (o alvo leva os golpes - eu a bater no monstro) ou 'atacar' (o alvo e quem bate - o monstro a bater em mim). Vazio decide pelo lado com mais eventos, o que ja trocou comparacoes: diga sempre o sentido.",
            "padrao": "",
        },
    },
)


def tool_analisar_combate(caminhos, alvo="", comparar_com="", direcao=""):
    teste, erro = _medir_lista(caminhos, alvo, direcao)
    if erro:
        return erro
    referencia, erro = _medir_lista(comparar_com, alvo, direcao)
    if erro:
        return erro
    grupos = (teste or []) + (referencia or [])
    if not grupos:
        return "ERRO: nenhum ficheiro indicado."
    corpo = _tabela([medida["nome"] for medida in grupos], grupos)
    detalhe = "\n".join(f"{medida['nome']}: {_efeito(medida)}" for medida in grupos)
    juizo = _veredicto(teste, referencia)
    return f"{corpo}\n\n{detalhe}" + (f"\n\n{juizo}" if juizo else "")


def _veredicto(teste, referencia):
    if not teste or not referencia:
        return ""
    pares = []
    if len(teste) == len(referencia):
        pares = list(zip(teste, referencia))
    else:
        sobra = list(referencia)
        for medida in teste:
            igual = next((r for r in sobra if r.get("alvo", "").lower() == medida.get("alvo", "").lower()), None)
            if igual:
                sobra.remove(igual)
            pares.append((medida, igual))

    linhas = ["VEREDICTO (a diferença só conta se passar da margem):"]
    for medida, par in pares:
        if par is None:
            linhas.append(f"  {medida['nome']}: sem par para comparar.")
            continue
        dif = medida["defesa"] - par["defesa"]
        margem = math.sqrt(medida["margem"] ** 2 + par["margem"] ** 2)
        juiz = "compatível" if abs(dif) <= margem else "DIFERE"
        linhas.append(
            f"  {medida['nome']} vs {par['nome']}: defesa {medida['defesa']:.1f}% contra {par['defesa']:.1f}% "
            f"(dif {dif:+.1f}, margem +-{margem:.1f}) -> {juiz}"
        )
        if medida.get("média") and par.get("média"):
            desvio = 100.0 * (medida["média"] - par["média"]) / par["média"]
            linhas.append(
                f"      golpe médio {medida['média']:.1f} contra {par['média']:.1f} ({desvio:+.0f}%)"
            )
    return "\n".join(linhas)


def _medir_lista(lista, alvo, direcao):
    medidas = []
    for nome in [linha.strip() for linha in (lista or "").splitlines() if linha.strip()]:
        eventos, formato = _ler_eventos(nome)
        if not eventos:
            return None, f"ERRO: {nome} não tem nenhum evento legível."
        escolhido = alvo.strip() or _alvo_provavel(eventos, formato)
        if not escolhido:
            return None, (
                f"ERRO: não consegui descobrir quem leva os golpes em {nome}. "
                "Passe 'alvo' com o nome da criatura."
            )
        medida = _medir(eventos, escolhido, formato, direcao)
        if medida is None:
            return None, f"ERRO: {nome} não tem golpes de '{escolhido}' legíveis o suficiente para medir."
        medida["nome"] = _curto(nome)
        medidas.append(medida)
    return medidas, ""
