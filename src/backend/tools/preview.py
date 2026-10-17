"""Ferramentas do preview: ver e operar a pagina que corre dentro do Axio.

A pagina vive no processo principal do Electron (uma WebContentsView) e fala-se com
ela pelo Chrome DevTools Protocol. Estas ferramentas nao tocam no Electron: escrevem
um pedido na ponte HTTP que o main.js abre em 127.0.0.1 no arranque, e cujo endereco
chega por AXIO_PONTE_PORTA/AXIO_PONTE_TOKEN no ambiente do Flask (injetado pelo
proprio main.js ao spawnar). Sem essa ponte as ferramentas dizem isso, em vez de
falharem em silencio.
"""

import base64
import json
import os
import re
import time
from urllib.parse import quote

from src.backend.services import cofre, ponte_preview
from src.backend.services.file_service import resolver_caminho_arquivo
from src.backend.services.imagem import codificar_para_envio, dimensoes_da_imagem, uniformidade_da_imagem
from src.backend.state import emit_event
from src.backend.tools.projeto_comum import caminho_relativo
from src.backend.tools.registry import register

ACOES_DE_OBSERVACAO = ("estado", "consola", "rede", "elemento", "mapa", "avaliar", "estilo", "canvas", "quadros", "print", "carregar", "mostrar")
ACOES_DE_ESPERA = ("esperar",)
CAMPOS_DO_ALVO_NA_LINHA = {
    "clicar": "seletor",
    "escrever": "seletor",
    "teclar": "tecla",
    "carregar": "alvo",
    "ficheiro": "alvo",
    "roda": "ponto",
    "arrastar": "ponto",
}
CARACTERES_DE_LUZ = " .:-=+*#%@"
ACOES_DE_OPERACAO = ("carregar", "mostrar", "clicar", "arrastar", "roda", "escrever", "teclar", "roteiro", "recarregar", "ficheiro")
LIMITE_PASSOS_ROTEIRO = 12
ESPERA_MAX_PASSO = 5000
EXTENSOES_DE_PAGINA = (".html", ".htm")
ROTAS_DO_SERVIDOR = ("/preview/", "/vendor/", "/js/", "/icons/")


def _endereco_local(destino):
    alvo = destino.strip().lower()
    if alvo.startswith("http://") or alvo.startswith("https://"):
        return "127.0.0.1" in alvo or "localhost" in alvo
    return True


def _e_endereco(alvo):
    """Um endereco ja pronto (http://..., localhost:5000/...) nao passa pela resolucao de ficheiro."""
    if "://" in alvo:
        return True
    return bool(re.match(r"^(localhost|127\.0\.0\.1|\d{1,3}(\.\d{1,3}){3}):\d+", alvo, re.I))


def _origem_do_servidor():
    """Endereco do proprio servidor do Axio - o mesmo que a janela usa para servir o preview."""
    try:
        from flask import request
        return request.host_url.rstrip("/")
    except Exception:
        return "http://127.0.0.1:5000"


def _e_rota_do_servidor(alvo):
    """Rota do proprio servidor do Axio (/preview/..., /js/...) - a forma que aparece na barra do preview."""
    if not alvo.startswith("/") or alvo.startswith("//"):
        return False
    return alvo.split("?")[0].split("#")[0].startswith(ROTAS_DO_SERVIDOR)


def _endereco_do_ficheiro(alvo):
    """Endereco que abre um ficheiro DO PROJETO no preview: pagina servida ou viewer.

    Um caminho relativo ('gerados/planta.dxf') e do projeto: quem o traduz no
    endereco certo e esta funcao, e nao quem chama. Ficheiro de pagina vai pela
    rota /preview, que resolve os caminhos do proprio documento contra o servidor
    (por file:// resolvem contra a raiz do disco e a pagina aparece nua); os
    formatos que o Chromium nao desenha (DXF, PDF, IFC) vao para o viewer, que os
    recebe no fragmento #f=<caminho>. Devolve (None, "") quando o alvo nao e um
    ficheiro do projeto - o endereco segue como veio.
    """
    try:
        caminho, _erro = resolver_caminho_arquivo(alvo)
    except Exception:
        caminho = None
    if not caminho or not os.path.isfile(caminho):
        if os.path.isabs(alvo):
            return None, ""
        if "/" in alvo or "\\" in alvo:
            return None, f"ficheiro do projeto nao encontrado: {alvo}"
        return None, ""
    relativo = caminho_relativo(caminho)
    if not relativo or relativo.startswith("..") or os.path.isabs(relativo):
        return None, ""
    origem = _origem_do_servidor()
    if caminho.lower().endswith(EXTENSOES_DE_PAGINA):
        return origem + "/preview/" + "/".join(quote(parte) for parte in relativo.split("/")), None
    return origem + "/vendor/viewer/index.html#f=" + quote(caminho, safe=""), None


class _Ponte:
    def __init__(self, tela="preview"):
        self._tela = tela

    def pedir(self, acao, **params):
        return ponte_preview.pedir(acao, tela=self._tela, **params)


def _renovar_pagina_local(destino, tela="preview"):
    ponte_preview = _Ponte(tela)
    if not _endereco_local(destino):
        return ""
    for _ in range(20):
        vista, falha = ponte_preview.pedir("estado")
        if falha or not vista.get("carregando"):
            break
        time.sleep(0.15)
    _, falha = ponte_preview.pedir("recarregar")
    if falha:
        return f" (AVISO: nao consegui forcar a recarga sem cache: {falha})"
    return " Recarreguei sem cache, para nao servir codigo guardado."


def _ponto_do_texto(ponto):
    """(x, y) de um 'x,y' escrito a mao - o mesmo formato que a ferramenta das regioes."""
    partes = [p.strip() for p in str(ponto or "").split(",")]
    if len(partes) != 2:
        return None, "ponto invalido: escreva 'x,y' (dois numeros, nas coordenadas da janela do preview)"
    try:
        return (int(round(float(partes[0]))), int(round(float(partes[1])))), ""
    except ValueError:
        return None, f"ponto invalido: '{ponto}' nao sao dois numeros"


def _pontos_do_texto(pontos):
    """[(x, y), ...] de 'x1,y1 x2,y2 ...' - o mesmo formato que a ferramenta das janelas nativas."""
    partes = [p for p in str(pontos or "").replace(";", " ").split(" ") if p.strip()]
    if len(partes) < 2:
        return None, (
            "ponto invalido: um arrasto tem dois ou mais pontos separados por espaco, "
            "no formato 'x1,y1 x2,y2' (ex: '300,200 520,260')"
        )
    lista = []
    for parte in partes:
        par = [v.strip() for v in parte.split(",")]
        if len(par) != 2:
            return None, f"ponto invalido: '{parte}' nao e 'x,y'"
        try:
            lista.append((int(round(float(par[0]))), int(round(float(par[1])))))
        except ValueError:
            return None, f"ponto invalido: '{parte}' nao sao dois numeros"
    return lista, ""


def _passos_das_linhas(escrito):
    """Um gesto por linha - o formato que se dita sem pensar: 'clicar #btn-x'.

    A forma natural de escrever um roteiro a mao e uma linha por gesto, e nao uma
    lista JSON. As duas valem, porque a mesma palavra 'roteiro' pede formatos
    diferentes em ferramentas diferentes. O texto de um campo vai depois de '|'.
    """
    linhas = []
    for numero, linha in enumerate(escrito.splitlines(), 1):
        texto = linha.strip()
        if not texto:
            continue
        partes = texto.split("|", 1)
        cabeca = partes[0].strip()
        resto = partes[1].strip() if len(partes) > 1 else ""
        pedacos = cabeca.split(None, 1)
        acao = pedacos[0].strip().lower()
        alvo = pedacos[1].strip() if len(pedacos) > 1 else ""
        if acao in ACOES_DE_ESPERA:
            try:
                milissegundos = int(float(alvo or 0))
            except ValueError:
                return None, (
                    f"na linha {numero}, 'esperar' precisa dos milissegundos (ex: 'esperar 500');"
                    f" '{alvo}' nao e um numero"
                )
            linhas.append({"acao": "esperar", "espera": max(0, min(ESPERA_MAX_PASSO, milissegundos))})
            continue
        if acao not in ACOES_DE_OPERACAO or acao == "roteiro":
            aceitas = [a for a in ACOES_DE_OPERACAO if a != "roteiro"] + list(ACOES_DE_ESPERA)
            return None, (
                f"na linha {numero}, '{pedacos[0]}' nao e uma acao; use uma de: {', '.join(aceitas)}"
            )
        passo = {"acao": acao, "espera": 0}
        if alvo:
            campo = CAMPOS_DO_ALVO_NA_LINHA.get(acao)
            if campo is None:
                return None, (
                    f"na linha {numero}, '{acao}' nao le um alvo; escreva so a acao na linha"
                )
            passo[campo] = alvo
        if resto:
            if acao not in ("escrever", "roda", "carregar"):
                return None, f"na linha {numero}, '{acao}' nao usa texto depois do '|'"
            passo["texto"] = resto
        linhas.append(passo)
    if not linhas:
        return None, "os 'passos' por linhas ficaram vazios"
    return linhas, ""


def _passos_do_roteiro(passos):
    """Lista de gestos validada - cada passo e o mesmo que uma chamada isolada.

    Valida tudo ANTES de tocar na pagina: um roteiro com o passo 3 mal escrito
    nao pode disparar os passos 1 e 2 e so depois descobrir o erro.
    """
    if isinstance(passos, (list, tuple)):
        bruto = list(passos)
    else:
        escrito = str(passos or "").strip()
        if not escrito:
            return None, (
                "indique 'passos' com a lista JSON dos gestos, por exemplo: "
                '[{"acao":"clicar","seletor":"#btn-x"},{"acao":"escrever","seletor":"#campo","texto":"oi"}]'
            )
        if escrito.startswith("[") or escrito.startswith("{"):
            try:
                bruto = json.loads(escrito)
            except Exception as exc:
                return None, (
                    f"'passos' parece uma lista JSON mas nao e valida ({exc}); cada gesto e um objeto"
                    " com 'acao' e os seus argumentos, dentro de uma lista, por exemplo: "
                    '[{"acao":"clicar","seletor":"#btn-x"},{"acao":"escrever","seletor":"#campo","texto":"oi"}]'
                    " - ou escreva um gesto por linha ('clicar #btn-x')."
                )
        else:
            bruto, falha = _passos_das_linhas(escrito)
            if falha:
                return None, falha
    if not isinstance(bruto, list) or not bruto:
        return None, "'passos' tem de ser uma lista com pelo menos um gesto"
    if len(bruto) > LIMITE_PASSOS_ROTEIRO:
        return None, (
            f"'passos' tem {len(bruto)} gestos e o maximo por roteiro e {LIMITE_PASSOS_ROTEIRO}"
            " (cada gesto e uma ida a pagina); divida em dois roteiros"
        )
    limpos = []
    for indice, passo in enumerate(bruto, 1):
        if not isinstance(passo, dict):
            return None, f"o passo {indice} nao e um objeto com 'acao' e os seus argumentos"
        acao = str(passo.get("acao") or "").strip().lower()
        if acao == "roteiro":
            return None, f"o passo {indice} nao pode ser um roteiro dentro de outro roteiro"
        if acao in ACOES_DE_ESPERA:
            try:
                milissegundos = int(float(str(passo.get("espera") or passo.get("texto") or 0)))
            except (TypeError, ValueError):
                return None, (
                    f"o passo {indice} e um 'esperar' sem tempo; escreva os milissegundos em 'espera'"
                    f" (ex: {{\"acao\":\"esperar\",\"espera\":500}})"
                )
            limpos.append({"acao": "esperar", "espera": max(0, min(ESPERA_MAX_PASSO, milissegundos))})
            continue
        if acao not in ACOES_DE_OPERACAO:
            aceitas = [a for a in ACOES_DE_OPERACAO if a != "roteiro"] + list(ACOES_DE_ESPERA)
            return None, (
                f"o passo {indice} tem acao '{passo.get('acao')}'; use uma de: " + ", ".join(aceitas)
            )
        try:
            espera = max(0, min(ESPERA_MAX_PASSO, int(passo.get("espera") or 0)))
        except (TypeError, ValueError):
            return None, (
                f"o passo {indice} tem espera '{passo.get('espera')}'; use milissegundos inteiros"
                f" (0 a {ESPERA_MAX_PASSO})"
            )
        limpos.append(dict(passo, acao=acao, espera=espera))
    return limpos, ""


def _alvo_do_passo(passo):
    """O que identifica o passo no relatorio: o alvo, a tecla ou o endereco."""
    for chave in ("seletor", "tecla", "alvo", "ponto"):
        valor = str(passo.get(chave) or "").strip()
        if valor:
            return valor
    return ""


CAMPOS_LIDOS_POR_ACAO = {
    "carregar": ("alvo", "texto"),
    "mostrar": (),
    "recarregar": (),
    "clicar": ("seletor", "ponto"),
    "arrastar": ("ponto",),
    "roda": ("ponto", "seletor", "texto"),
    "escrever": ("seletor", "texto", "limpar"),
    "teclar": ("tecla", "seletor"),
    "roteiro": ("passos",),
    "ficheiro": ("alvo", "texto", "seletor"),
}


def _argumento_ignorado(pedido, valores):
    """Aponta o argumento preenchido que a acao escolhida nao le - ele seria ignorado em silencio."""
    if pedido not in CAMPOS_LIDOS_POR_ACAO:
        return ""
    lidos = CAMPOS_LIDOS_POR_ACAO[pedido]
    for nome, valor in valores.items():
        if nome in lidos:
            continue
        preenchido = bool(valor) if nome == "limpar" else bool(str(valor or "").strip())
        if not preenchido:
            continue
        esperados = ", ".join(f"'{campo}'" for campo in lidos) or "nenhum campo"
        return (f"ERRO: '{nome}' nao e lido por acao='{pedido}' (essa acao usa {esperados}) - "
                "o valor que passou seria ignorado em silencio.")
    return ""


def _correr_roteiro(passos, tela="preview", medida=None):
    """Corre os gestos em serie pela mesma ferramenta de um gesto isolado.

    Nao ha caminho alternativo: cada passo entra por tool_operar_preview, logo
    leva o mesmo guard (alvo recalculado no instante do gesto, recusa se estiver
    tapado ou fora da janela) e o mesmo relato de efeito. Parar no primeiro erro
    e o que impede a cascata - um passo falhado deixaria os seguintes a agir
    sobre uma pagina que ja nao esta no estado previsto.
    """
    linhas = []
    for indice, passo in enumerate(passos, 1):
        if passo["acao"] == "esperar":
            time.sleep(passo["espera"] / 1000.0)
            linhas.append(f"[{indice}] esperar {passo['espera']} ms")
            continue
        if passo.get("espera"):
            time.sleep(passo["espera"] / 1000.0)
        resultado = tool_operar_preview(
            tela=tela,
            acao=passo["acao"],
            seletor=str(passo.get("seletor") or ""),
            ponto=str(passo.get("ponto") or ""),
            alvo=str(passo.get("alvo") or ""),
            texto=str(passo.get("texto") or ""),
            limpar=bool(passo.get("limpar")),
            tecla=str(passo.get("tecla") or ""),
            largura=int((medida or {}).get("largura") or 0),
            altura=int((medida or {}).get("altura") or 0),
            mobile=bool((medida or {}).get("mobile")),
        )
        alvo = _alvo_do_passo(passo)
        linhas.append(f"[{indice}] {passo['acao']} {alvo}\n    {resultado}")
        if str(resultado).startswith("ERRO:"):
            restantes = len(passos) - indice
            if restantes:
                linhas.append(
                    f"PARADO no passo {indice} do roteiro: os {restantes} gesto(s) seguintes nao"
                    " correram, para nao agirem no sitio errado. Corrija o que falhou e repita."
                )
            else:
                linhas.append(f"PARADO no passo {indice} do roteiro (era o ultimo).")
            break
    return "\n".join(linhas)


def _texto_do_estado(dados):
    if not dados.get("tem_pagina"):
        return "O preview esta aberto mas sem pagina nenhuma. Use tool_operar_preview com acao='carregar'."
    partes = [f"Preview em {dados.get('url') or '(sem endereco)'}"]
    if dados.get("titulo"):
        partes.append(f"titulo '{dados['titulo']}'")
    partes.append("a carregar" if dados.get("carregando") else "carregado")
    partes.append("a vista" if dados.get("visivel") else "escondido (outra vista do editor esta a frente)")
    partes.append("pronto a receber comandos" if dados.get("depurador") else "sem canal para a pagina")
    return " - ".join(partes) + "."


def _resumo_por_nivel(entradas):
    """Contagem 'quantos de cada nivel', do mais frequente para o menos."""
    contagem = {}
    for entrada in entradas:
        nivel = entrada.get("nivel") or "log"
        contagem[nivel] = contagem.get(nivel, 0) + 1
    return ", ".join(f"{q} {n}" for n, q in sorted(contagem.items(), key=lambda par: -par[1]))


def _texto_da_consola(dados):
    entradas = dados.get("entradas") or []
    if not entradas:
        return "Nenhuma mensagem na consola do preview desde que a pagina carregou."
    linhas = [f"Consola do preview: {dados.get('total') or 0} mensagem(ns) desde o carregamento ({_resumo_por_nivel(entradas)})."]
    if dados.get("descartadas"):
        linhas.append(f"({dados['descartadas']} mensagens antigas sairam do buffer.)")
    for entrada in entradas:
        onde = ""
        if entrada.get("ficheiro"):
            onde = f" [{entrada['ficheiro']}:{entrada.get('linha') or 0}]"
        linhas.append(f"[{entrada.get('nivel')}] {entrada.get('origem')}{onde} {entrada.get('texto')}")
    return "\n".join(linhas)


def _texto_da_rede(dados):
    entradas = dados.get("entradas") or []
    if not entradas:
        return "Rede do preview limpa: nenhum pedido falhado desde que a pagina carregou (sem 404, 500 ou ligacao recusada)."
    linhas = [f"Rede do preview: {dados.get('total') or 0} pedido(s) com problema ({_resumo_por_nivel(entradas)})."]
    if dados.get("descartadas"):
        linhas.append(f"({dados['descartadas']} entradas antigas sairam do buffer.)")
    for entrada in entradas:
        estado = entrada.get("status") or 0
        tipo = f" [{entrada['tipo']}]" if entrada.get("tipo") else ""
        motivo = f" - {entrada['motivo']}" if entrada.get("motivo") else ""
        linhas.append(f"[{entrada.get('nivel')}] {estado or 'sem resposta'}{tipo} {entrada.get('url')}{motivo}")
    return "\n".join(linhas)


def _texto_da_conferencia(conferencia):
    """Diz se o campo ACEITOU o texto - um input de data recusa o insertText e fica vazio."""
    if not conferencia:
        return ""
    if conferencia.get("entregue"):
        if conferencia.get("via") == "valor-do-campo":
            return (" O campo recusou o texto pelo teclado; o valor foi posto pelo caminho do "
                    "proprio campo, com o evento de mudanca disparado.")
        return ""
    lido = str(conferencia.get("valor") or "")
    return (" ATENCAO: o campo NAO ficou com o texto (esta " + (repr(lido[:60]) if lido else "vazio")
            + ") - confira o seletor e o formato que o campo exige antes de seguir.")


def _texto_do_efeito(efeito):
    """O que o gesto provocou: se a pagina se mexeu, e os erros e falhas que ele causou."""
    if not efeito:
        return ""
    antes = efeito.get("antes") or {}
    depois = efeito.get("depois") or {}
    if efeito.get("navegou"):
        provas = [f"a pagina navegou para {depois.get('url') or '(vazio)'}"]
    else:
        provas = []
        if antes.get("url") != depois.get("url"):
            provas.append(f"endereco para {depois.get('url') or '(vazio)'}")
        if antes.get("titulo") != depois.get("titulo"):
            provas.append(f"titulo para '{depois.get('titulo') or '(vazio)'}'")
        if antes.get("total") != depois.get("total"):
            provas.append(f"elementos {antes.get('total')} -> {depois.get('total')}")
        if antes.get("sem_caixa") != depois.get("sem_caixa"):
            provas.append(
                f"elementos sem caixa {antes.get('sem_caixa')} -> {depois.get('sem_caixa')}"
            )
        alvo_antes = antes.get("alvo") or {}
        alvo_depois = depois.get("alvo") or {}
        if alvo_antes and not alvo_depois.get("existe"):
            provas.append("o elemento apontado desapareceu da pagina")
        elif alvo_antes and alvo_antes.get("classes") != alvo_depois.get("classes"):
            provas.append(
                f"classes do alvo '{alvo_antes.get('classes')}' -> '{alvo_depois.get('classes')}'"
            )
        if alvo_antes.get("valor") != alvo_depois.get("valor"):
            provas.append(
                f"campo com {alvo_depois.get('valor')} caractere(s) (antes {alvo_antes.get('valor')})"
            )
        detalhe_antes = alvo_antes.get("detalhe") or {}
        detalhe_depois = alvo_depois.get("detalhe") or {}
        if (detalhe_antes.get("aberto") != detalhe_depois.get("aberto")
                and (detalhe_antes.get("aberto") is not None or detalhe_depois.get("aberto") is not None)):
            provas.append(
                f"o alvo passou a aria-expanded='{detalhe_depois.get('aberto')}'"
                f" (era '{detalhe_antes.get('aberto')}')"
            )
        if detalhe_antes.get("escondido") != detalhe_depois.get("escondido"):
            provas.append(
                f"o alvo mudou de {detalhe_antes.get('escondido')} para {detalhe_depois.get('escondido')}"
            )
        if depois.get("altura") and antes.get("altura") != depois.get("altura"):
            provas.append(f"altura da pagina {antes.get('altura')} -> {depois.get('altura')} px")
        irmaos_antes = antes.get("irmaos") or []
        irmaos_depois = depois.get("irmaos") or []
        mudados = 0
        for posicao in range(min(len(irmaos_antes), len(irmaos_depois))):
            um = irmaos_antes[posicao]
            outro = irmaos_depois[posicao]
            if (um.get("classe"), um.get("aberto"), um.get("tamanho"), um.get("escondido")) != (
                outro.get("classe"), outro.get("aberto"), outro.get("tamanho"), outro.get("escondido")
            ):
                mudados += 1
        if mudados:
            provas.append(f"{mudados} irmao(s) do alvo mudaram de estado")
    if provas:
        linha = "A pagina reagiu: " + "; ".join(provas) + "."
    elif not depois:
        linha = (
            "O gesto foi feito, mas nao consegui medir a pagina depois dele (ela pode ter"
            " deixado de responder ou navegado) - nao sei se mudou."
        )
    elif depois:
        valor_alvo = (depois.get("alvo") or {}).get("valor")
        do_campo = (
            f" e o campo continua com {valor_alvo} caractere(s)" if valor_alvo is not None else ""
        )
        linha = (
            "O alvo foi olhado depois do gesto e continua IGUAL - classes, tamanho, valor,"
            " aria-expanded e os irmaos dele, nada mudou"
            f"{do_campo} - logo a pagina nao reagiu ({depois.get('total')} elementos,"
            f" {depois.get('sem_caixa')} sem caixa). Nao repeti o gesto por conta propria:"
            " um clique que grava nao pode ser disparado duas vezes as escuras. Se o botao"
            " trabalha devagar, repita com repetir=true; se nao mudou nada mesmo, veja a"
            " consola e a rede desta resposta."
        )
    else:
        linha = "Nada detetavel mudou na pagina (nao consegui olhar para ela depois do gesto)."
    if efeito.get("repetido"):
        linha += (" O gesto foi repetido a seu pedido (repetir=true) e a segunda tentativa"
                  " mexeu na pagina.")
    novas = efeito.get("consola") or []
    if novas:
        mostra = "; ".join(
            f"[{e.get('nivel')}] {e.get('texto')}"
            + (f" ({e.get('ficheiro')}:{e.get('linha')})" if e.get("ficheiro") else "")
            for e in novas[:3]
        )
        linha += f" Consola: {len(novas)} nova(s) - {mostra}."
    else:
        linha += " Sem erro novo na consola."
    falhas = efeito.get("rede") or []
    if falhas:
        mostra = "; ".join(
            f"{e.get('nivel')} {e.get('status') or 'sem resposta'} {e.get('url')}" for e in falhas[:3]
        )
        linha += f" Rede: {len(falhas)} falha(s) - {mostra}."
    return linha


def _com_efeito(base, dados):
    """A largura emulada, a frase da acao e o efeito que ela provocou na pagina."""
    vista = _texto_do_viewport(dados)
    efeito = _texto_do_efeito(dados.get("efeito"))
    corpo = f"{base} {efeito}" if efeito else base
    return f"{vista}\n{corpo}" if vista else corpo


def _texto_dos_elementos(dados):
    elementos = dados.get("elementos") or []
    pagina = dados.get("pagina") or {}
    rolagem = pagina.get("rolagem") or {}
    contexto = (
        f"Janela do preview com {pagina.get('largura')}x{pagina.get('altura')} px,"
        f" rolagem em {rolagem.get('x', 0)},{rolagem.get('y', 0)}."
        " As coordenadas sao relativas a janela (as mesmas que o clique usa)."
    )
    if not elementos:
        return (
            "Nenhum elemento encontrado. Confira o seletor ou o texto - e confirme com"
            f" acao='estado' que a pagina carregou. {contexto}"
        )
    linhas = [f"{dados.get('total') or 0} elemento(s). {contexto}"]
    for indice, elemento in enumerate(elementos, 1):
        caixa = elemento.get("caixa") or {}
        centro = elemento.get("centro") or {}
        marcas = []
        if not elemento.get("pintado"):
            marcas.append("nao esta pintado")
        if not elemento.get("dentro_da_janela"):
            marcas.append("fora da area visivel, role a pagina")
        if elemento.get("tapado_por"):
            topo = elemento["tapado_por"]
            if topo.get("fora_da_janela"):
                marcas.append("o centro cai fora da janela; nada para clicar ali")
            else:
                quem = f"#{topo.get('id')}" if topo.get("id") else (topo.get("seletor") or topo.get("etiqueta"))
                marcas.append(f"TAPADO por {quem}: o clique iria para esse elemento")
        sufixo = f" ({'; '.join(marcas)})" if marcas else ""
        linhas.append(
            f"{indice}. {elemento.get('seletor')} <{elemento.get('etiqueta')}>"
            f" '{(elemento.get('rotulo') or '')[:80]}'"
            f" - caixa x={caixa.get('x')} y={caixa.get('y')} {caixa.get('largura')}x{caixa.get('altura')}"
            f" - centro ({centro.get('x')},{centro.get('y')}){sufixo}"
        )
    return "\n".join(linhas)


def _texto_do_mapa(dados):
    """Indice dos elementos que respondem ao gesto, por ordem de leitura da pagina.

    E o "dicionario" da pagina numa so chamada: em vez de perguntar elemento a
    elemento, o agente recebe de uma vez tudo o que pode clicar ou preencher. So
    entram os que estao pintados, dentro da janela e sem ninguem por cima - se o
    gesto cairia noutro elemento, ele nao serve e nao vale a pena listar.
    """
    elementos = dados.get("elementos") or []
    pagina = dados.get("pagina") or {}
    resumo = dados.get("resumo") or {}
    janela = pagina.get("janela") or {}
    rolagem = pagina.get("rolagem") or {}
    contexto = (
        f"Janela do preview com {janela.get('largura')}x{janela.get('altura')} px,"
        f" rolagem em {rolagem.get('x', 0)},{rolagem.get('y', 0)}."
        " As coordenadas sao relativas a janela (as mesmas que o clique usa)."
    )
    if not elementos:
        return f"Nenhum elemento interativo visivel nesta pagina. {_porque_sem_mapa(dados)} {contexto}"
    linhas = [
        f"{dados.get('total') or 0} elemento(s) interativo(s) ao alcance de um gesto"
        f" (de {resumo.get('candidatos') or 0} candidato(s) no DOM)."
        f" {contexto} Copie o seletor tal como esta: o alvo e recalculado no instante do gesto."
    ]
    fora = []
    if resumo.get("tapados"):
        fora.append(f"{resumo['tapados']} tapado(s) por outro elemento")
    if resumo.get("fora"):
        fora.append(f"{resumo['fora']} fora da janela ou nao pintado(s)")
    if resumo.get("sem_rotulo"):
        fora.append(f"{resumo['sem_rotulo']} sem texto nem nome")
    if fora:
        linhas.append(f"(Sem interesse para o gesto: {', '.join(fora)}.)")
    for indice, elemento in enumerate(elementos, 1):
        centro = elemento.get("centro") or {}
        caixa = elemento.get("caixa") or {}
        nome = f"#{elemento['id']}" if elemento.get("id") else elemento.get("seletor")
        linhas.append(
            f"{indice}. {nome} <{elemento.get('etiqueta')}>"
            f" '{(elemento.get('rotulo') or '')[:60]}'"
            f" - centro ({centro.get('x')},{centro.get('y')}) {caixa.get('largura')}x{caixa.get('altura')}"
        )
    return "\n".join(linhas)


def _porque_sem_mapa(dados):
    """Distingue a pagina que ainda esta a montar-se da pagina mesmo sem nada ao alcance."""
    diagnostico = dados.get("diagnostico") or {}
    if diagnostico.get("corpo_escondido"):
        return (
            "O corpo da pagina esta escondido (display:none): ela ainda esta a montar-se ou depende"
            " de um script que nao correu - repita o mapa daqui a instantes."
        )
    pronto = diagnostico.get("pronto") or ""
    if pronto and pronto != "complete":
        return f"A pagina ainda esta a carregar (readyState={pronto}) - repita o mapa daqui a instantes."
    if diagnostico:
        return (
            f"A pagina tem {diagnostico.get('nos') or 0} elemento(s) no DOM e nenhum clicavel ao alcance"
            " (fora da janela, escondidos ou tapados)."
        )
    return "Confirme com acao='estado' que a pagina carregou."


def _caracteristicas(dados):
    """As propriedades que definem o desenho de UM elemento, so as que existem.

    Nao e um despejo de CSS: sai o que o browser usa para o pintar e nada mais -
    um elemento sem borda nao aparece com 'borda none', porque o que nao existe
    nao ajuda a replicar.
    """
    linhas = []
    caixa = dados.get("caixa") or {}
    espaco = dados.get("espacamento") or {}
    linhas.append(f"caixa {caixa.get('largura')}x{caixa.get('altura')} em ({caixa.get('x')},{caixa.get('y')})")
    layout = dados.get("layout") or ""
    if dados.get("alinhamento"):
        layout = f"{layout} - {dados['alinhamento']}"
    if layout:
        linhas.append(f"layout {layout}")
    if espaco.get("padding"):
        linhas.append(f"padding {espaco['padding']}")
    if espaco.get("gap") and espaco["gap"] != "normal":
        linhas.append(f"gap {espaco['gap']}")
    if dados.get("arredondamento") and dados["arredondamento"] != "0px":
        linhas.append(f"radius {dados['arredondamento']}")
    if dados.get("fundo"):
        linhas.append(f"fundo {dados['fundo']}")
    if dados.get("fundo_imagem"):
        linhas.append(f"imagem de fundo {dados['fundo_imagem']}")
    if dados.get("cor"):
        linhas.append(f"cor {dados['cor']}")
    if dados.get("borda"):
        linhas.append(f"borda {dados['borda']}")
    if dados.get("sombra"):
        linhas.append(f"sombra {dados['sombra']}")
    if dados.get("fonte"):
        linhas.append(f"fonte {dados['fonte']}")
    if dados.get("transicao"):
        linhas.append(f"transicao {dados['transicao']}")
    try:
        propria = float(dados.get("opacidade") or 1)
    except (TypeError, ValueError):
        propria = 1.0
    efetiva = dados.get("opacidade_efetiva")
    if isinstance(efetiva, (int, float)) and efetiva < 1:
        if propria < 1 and abs(propria - efetiva) <= 0.01:
            linhas.append(f"opacidade {propria}")
        elif propria < 1:
            linhas.append(f"opacidade {propria}, mas so {efetiva} efetiva - o resto vem dos ancestrais")
        else:
            linhas.append(f"opacidade efetiva {efetiva} - vem de um ancestral, este elemento e opaco")
    return linhas


def _contagens(titulo, itens):
    if not itens:
        return ""
    pares = ", ".join(f"{i.get('valor')} (x{i.get('vezes')})" for i in itens)
    return f"{titulo}: {pares}"


def _texto_dos_tokens(dados):
    janela = dados.get("janela") or {}
    linhas = [
        f"Desenho da pagina '{dados.get('titulo')}' - janela de {janela.get('largura')}x{janela.get('altura')} px,"
        f" {dados.get('total_de_elementos')} elementos no DOM."
    ]
    for titulo, chave in (
        ("Cores de fundo mais usadas", "cores_de_fundo"),
        ("Arredondamentos", "arredondamentos"),
        ("Fontes", "fontes"),
    ):
        resumo = _contagens(titulo, dados.get(chave) or [])
        if resumo:
            linhas.append(resumo)
    principais = dados.get("principais") or []
    if principais:
        linhas.append(f"Os {len(principais)} blocos com mais area (o esqueleto da pagina):")
        for bloco in principais:
            linhas.append(f"- {bloco.get('seletor')}: " + ", ".join(_caracteristicas(bloco)[:4]))
    return "\n".join(linhas)


def _texto_do_estilo(dados):
    """Raio-x do desenho: o que o browser PINTA num elemento, no pai e nos filhos.

    Nasceu do pedido de replicar o layout de uma pagina noutra. Em vez de ler o HTML
    e o CSS a mao, o agente recebe as medidas e as cores ja computadas - as mesmas que
    o browser usa - com o pai ao lado (o contexto que o elemento herda) e os filhos
    (a estrutura de dentro). Sem 'seletor' devolve o desenho da pagina inteira: as
    cores, os arredondamentos e as fontes por frequencia, mais os blocos com mais area.
    """
    if dados.get("sem_seletor"):
        return _texto_dos_tokens(dados)
    elemento = dados.get("elemento") or {}
    linhas = [f"Desenho de {elemento.get('seletor')}:"]
    linhas.extend(f"- {linha}" for linha in _caracteristicas(elemento))
    if elemento.get("classes"):
        linhas.append(f"- classes {elemento['classes']}")
    pai = dados.get("pai")
    if pai:
        linhas.append(f"No pai {pai.get('seletor')}:")
        linhas.extend(f"- {linha}" for linha in _caracteristicas(pai))
    filhos = dados.get("filhos") or []
    if filhos:
        linhas.append(f"Dentro dele, {len(filhos)} filho(s) diretos:")
        for filho in filhos:
            linhas.append(f"- {filho.get('seletor')}: " + ", ".join(_caracteristicas(filho)[:3]))
    return "\n".join(linhas)


def _simbolo_de_luz(valor, escala):
    """A luz de uma celula num caracter: do vazio ao cheio, na escada de CARACTERES_DE_LUZ."""
    nivel = int(round(float(valor) / escala * (len(CARACTERES_DE_LUZ) - 1)))
    return CARACTERES_DE_LUZ[max(0, min(nivel, len(CARACTERES_DE_LUZ) - 1))]


def _texto_do_canvas(dados):
    """O quadro de um canvas em numeros e em grelha de caracteres: a luz de cada zona, lida do pixel."""
    valores = dados.get("valores") or []
    if not valores:
        return "ERRO: o canvas nao devolveu quadro nenhum."
    caixa = dados.get("caixa") or {}
    cor = dados.get("cor") or {}
    maximo = float(dados.get("maximo") or 0)
    escala = maximo if maximo > 0 else 1
    linhas = [
        f"Canvas {dados.get('elemento') or '?'}: {dados.get('largura')}x{dados.get('altura')} px de "
        f"desenho, {caixa.get('largura')}x{caixa.get('altura')} px no ecra, motor {dados.get('motor')}, "
        f"quadro lido por {dados.get('via')}.",
        f"Luz media {dados.get('media')} (0 a 1), maior celula {maximo}, "
        f"{round(float(dados.get('fracao_acesa') or 0) * 100, 1)}% da grelha acesa. Cor media ja "
        f"pesada pela opacidade: rgb({cor.get('r')}, {cor.get('g')}, {cor.get('b')}) com alfa "
        f"{cor.get('a')} de 255.",
        f"Grelha {dados.get('colunas')}x{dados.get('linhas')} - '{CARACTERES_DE_LUZ[0]}' e vazio e "
        f"'{CARACTERES_DE_LUZ[-1]}' e cheio:",
    ]
    for linha in valores:
        linhas.append("  " + "".join(_simbolo_de_luz(valor, escala) for valor in linha))
    if dados.get("zerado"):
        linhas.append(
            "AVISO: o quadro veio TODO vazio - o buffer do desenho ja tinha sido descartado quando o "
            "li. Isto e o que acontece a um canvas WebGL cuja vista esta escondida (o Chromium suspende "
            "o desenho) ou cuja aplicacao usa preserveDrawingBuffer falso. Traga a vista a frente com "
            "acao='mostrar' e repita antes de concluir que o canvas esta em branco."
        )
    return "\n".join(linhas)


def _aviso_de_vista_escondida(tela="preview"):
    """Avisa que a serie esta a correr numa vista escondida, onde o Chromium congela animacoes."""
    ponte_preview = _Ponte(tela)
    dados, erro = ponte_preview.pedir("estado")
    if erro or not isinstance(dados, dict) or not dados.get("tem_pagina"):
        return ""
    if dados.get("visivel", True):
        return ""
    onde = "a janela do Axio" if tela == "janela" else "a vista do preview"
    return (
        f"AVISO: {onde} esta escondida ou minimizada - o Chromium congela animacoes e transicoes "
        "numa vista escondida, logo esta serie pode mostrar patamares que no ecra nao existem. "
        "Traga-a a frente antes de medir."
    )


def _texto_das_amostras(js, total, amostras):
    """A serie em linhas 'ms: valor'.

    O que se mede AO LONGO DO TEMPO - uma transicao a acontecer, um carregamento a
    subir, um contador a avancar - nao se le num JSON aninhado: em linhas, uma por
    amostra, a RAMPA fica a vista e o defeito salta.
    """
    linhas = [f"Amostras de '{js[:90]}' durante {total} ms ({len(amostras)} leituras):"]
    for item in amostras:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            linhas.append(f"  {item[0]}ms: {json.dumps(item[1], ensure_ascii=False, default=str)}")
        else:
            linhas.append(f"  {json.dumps(item, ensure_ascii=False, default=str)}")
    return "\n".join(linhas)


def texto_dos_quadros(dados):
    """O ritmo de desenho em numeros: media, mediana, p95 e quadros acima de 32 ms."""
    linhas = [
        f"Quadros desenhados: {dados.get('quadros')} em {dados.get('ms')} ms"
        f" ({dados.get('fps')} por segundo).",
        f"Intervalo entre quadros: medio {dados.get('medio')} ms, mediano {dados.get('mediano')} ms,"
        f" p95 {dados.get('p95')} ms, pior {dados.get('pior')} ms.",
    ]
    quadros = max(1, int(dados.get("quadros") or 1))
    longos = int(dados.get("longos") or 0)
    if longos:
        linhas.append(
            f"{longos} quadro(s) acima de 32 ms ({100.0 * longos / quadros:.0f}% do total): e nesses"
            " que o olho ve o travamento."
        )
    else:
        linhas.append("Nenhum quadro acima de 32 ms - o desenho acompanhou o ecra o tempo todo.")
    return "\n".join(linhas)


def _print_do_preview(seletor, regiao, tela="preview", largura=0, altura=0, mobile=False):
    ponte_preview = _Ponte(tela)
    nome = "da janela do Axio" if tela == "janela" else "do preview"
    dados, erro = ponte_preview.pedir(
        "print", seletor=seletor, regiao=regiao, largura=largura, altura=altura, mobile=mobile
    )
    if erro:
        return f"ERRO: {erro}."
    if not dados.get("ok"):
        return f"ERRO: {dados.get('erro') or 'a pagina nao devolveu imagem'}."
    bruto = base64.b64decode(dados.get("base64") or "")
    if not bruto:
        return "ERRO: a pagina devolveu uma imagem vazia."
    base64_img, mime, entregue = codificar_para_envio(bruto)
    dimensoes = dimensoes_da_imagem(bruto) or (0, 0)
    alvo = f" de {dados['onde']}" if dados.get("onde") else ""
    aviso = ""
    if entregue and tuple(entregue) != tuple(dimensoes):
        aviso = f" A API reduz a imagem a ~800x800 equivalentes, por isso chegou com {entregue[0]}x{entregue[1]} px."
    uniforme = uniformidade_da_imagem(bruto)
    if uniforme and uniforme.get("uniforme"):
        cor = uniforme.get("cor") or [0, 0, 0]
        fatia = round(100 * float(uniforme.get("fatia") or 0), 1)
        aviso += (
            f" AVISO: a captura saiu QUASE TODA da mesma cor - {fatia}% dos pixeis sao"
            f" rgb({cor[0]},{cor[1]},{cor[2]}). Se aquela regiao tinha conteudo, isto e o instrumento"
            " a falhar, e nao um resultado: vista em segundo plano, regiao fora do que foi pintado,"
            " ou a pagina ainda a pintar. Confirme com acao='estado', traga a vista a frente com"
            " acao='mostrar' e repita - ou fotografe o ecra do sistema com tool_capturar_print."
        )
    referencia = dados.get("referencia")
    onde_conta = ""
    if referencia == "pagina":
        onde_conta = " A regiao foi contada pela PAGINA inteira, e nao pelo que esta no ecra."
    nota = str(dados.get("nota") or "").strip()
    return {
        "texto": _com_alvo(
            f"Print {nome}{alvo}: {dimensoes[0]}x{dimensoes[1]} px.{onde_conta}"
            " A imagem segue com esta resposta - olhe para ela antes de concluir."
            f"{aviso}"
            + (f" {nota}" if nota else ""),
            dados,
            print_em_segundo_plano=True,
        ),
        "imagem": {"base64": base64_img, "mime": mime, "rotulo": f"[Print {nome}{alvo}]"},
    }


def _identidade_do_preview(dados):
    """A aba que respondeu, em texto.

    Com mais de uma vista aberta, o 'estado' e o 'avaliar' podem cair em vistas diferentes -
    sem dizer QUAL respondeu, o relatorio mistura duas paginas e nao se percebe onde esta o
    defeito. A identidade vem da ponte (aba, id, url e se estava a vista).
    """
    alvo = (dados or {}).get("alvo") or {}
    if not alvo:
        return ""
    partes = [f"aba '{alvo.get('aba') or '?'}' (id {alvo.get('id')})",
              alvo.get("url") or "(sem endereco)"]
    if alvo.get("visivel") is False:
        partes.append("vista ESCONDIDA nesta chamada")
    return "Aba que respondeu: " + " - ".join(partes) + "."


def _texto_do_viewport(dados):
    """A largura em que a medicao foi feita - nunca deixar confundir com a janela real."""
    medida = (dados or {}).get("viewport") or {}
    if not medida.get("largura"):
        return ""
    como = (
        "emulacao de telemovel (o viewport meta da pagina e respeitado)"
        if medida.get("mobile")
        else "disposicao forcada a essa largura (e o que faz as media queries dispararem)"
    )
    linha = (
        f"MEDIDO A {medida.get('largura')}x{medida.get('altura')} px - {como}."
        " A janela do preview continua no tamanho normal: as medidas sao as desta largura."
    )
    pedida = int(medida.get("pedida") or 0)
    if pedida and pedida != int(medida.get("largura") or 0):
        return (
            f"ATENCAO: pedi {pedida} px de largura e a pagina ficou com"
            f" {medida.get('largura')} px - ela nao declara o viewport meta, logo o layout"
            " NAO esta na largura pedida.\n" + linha
        )
    return linha


def _com_alvo(texto, dados, print_em_segundo_plano=False):
    """Antepoe a identidade da aba, a largura emulada e os avisos que so fazem sentido com ela.

    As mentiras que isto mata: ler uma ABA MORTA (chrome-error://) a pensar que e a
    pagina carregada, concluir de um print PRETO tirado a uma vista em segundo plano (o
    Chromium estrangula o desenho de uma vista escondida), e tomar uma medicao a 390 px
    por uma medicao da janela.
    """
    alvo = (dados or {}).get("alvo") or {}
    linhas = []
    identidade = _identidade_do_preview(dados)
    if identidade:
        linhas.append(identidade)
    vista = _texto_do_viewport(dados)
    if vista:
        linhas.append(vista)
    avisos = []
    if str(alvo.get("url") or "").startswith("chrome-error"):
        avisos.append(
            "AVISO: esta aba esta numa PAGINA DE ERRO do Chromium (chrome-error://) - o alvo que"
            " voce carregou nao esta la, e o que se le aqui NAO e o que voce pediu. Recarregue o"
            " alvo antes de concluir."
        )
    elif print_em_segundo_plano and alvo.get("visivel") is False:
        avisos.append(
            "AVISO: a aba estava em SEGUNDO PLANO nesta captura - o Chromium estrangula o desenho"
            " de uma vista escondida, logo um canvas/WebGL pode sair PRETO. Se a imagem vier preta,"
            " traga a vista a frente com acao='mostrar' e repita."
        )
    aviso = str((dados or {}).get("aviso") or "").strip()
    if aviso:
        avisos.append(aviso)
    return "\n".join(linhas + avisos + [texto])


def _seletores_em_lote(seletores):
    """Uma linha por seletor, sem repetir e sem vazios."""
    vistos = []
    for linha in str(seletores or "").splitlines():
        limpo = linha.strip()
        if limpo and limpo not in vistos:
            vistos.append(limpo)
    return vistos


def _em_lote(pedido, alvos, limite, medida):
    """O mesmo pedido a varios seletores, um bloco por alvo, numa so chamada."""
    blocos = []
    primeiro = {}
    for indice, alvo in enumerate(alvos, 1):
        dados, erro = ponte_preview.pedir(pedido, seletor=alvo, limite=limite, **medida)
        if erro:
            blocos.append(f"[{indice}] {alvo}\n  ERRO: {erro}.")
            continue
        if not dados.get("ok"):
            blocos.append(f"[{indice}] {alvo}\n  ERRO: {dados.get('erro') or 'a pagina nao respondeu'}.")
            continue
        if not primeiro:
            primeiro = dados
        texto = _texto_do_estilo(dados) if pedido == "estilo" else _texto_dos_elementos(dados)
        blocos.append(f"[{indice}] {alvo}\n" + texto)
    cabeca = f"{len(alvos)} alvos numa so chamada ('{pedido}'), um bloco por seletor."
    return _com_alvo(cabeca + "\n\n" + "\n\n".join(blocos), primeiro)


@register(
    "tool_observar_preview",
    "Olha para uma pagina do Axio e devolve o que ela diz de si propria, sem depender dos olhos "
    "do utilizador e sem capturar o ecra. O alvo e o preview (por omissao) ou a PROPRIA JANELA "
    "do Axio, com 'tela'='janela' - e nessa que se mede a fluidez dos efeitos (acao='quadros', "
    "devolve fps, mediana, p95 e quantos quadros passaram dos 32 ms) e se le a consola de JS da "
    "interface. acao="
    "'mapa' e o INDICE DA PAGINA: devolve de uma so vez todos os botoes, ligacoes e campos ao "
    "alcance de um gesto, com o seletor, o que dizem e a coordenada - comece por aqui, em vez "
    "de perguntar elemento a elemento; 'estado' diz o que esta carregado; 'consola' devolve os erros e avisos da pagina com "
    "ficheiro e linha (e a primeira coisa a ver quando um botao nao responde); 'rede' devolve "
    "os pedidos que falharam (404/500/ligacao recusada, com a URL e o tipo) - e o que explica "
    "uma pagina que aparece sem estilo ou sem os scripts; 'elemento' "
    "localiza um botao/campo por seletor CSS ou pelo texto visivel e devolve a coordenada "
    "exata, se esta pintado e se esta dentro da janela; 'avaliar' corre uma expressao "
    "JavaScript na pagina e devolve o resultado - com 'durante' devolve a SERIE de amostras desse "
    "valor ao longo do tempo, que e como se ve uma transicao ou um carregamento a acontecer; "
    "'estilo' devolve o RAI-X DO DESENHO - medidas, "
    "cores, arredondamentos, fontes e transicoes ja computados pelo browser - de um elemento (com o pai "
    "e os filhos) ou da pagina inteira (os blocos com mais area e os tokens por frequencia), e e o "
    "caminho para replicar um layout noutra pagina sem ler o HTML e o CSS a mao; 'canvas' le o QUADRO "
    "de um canvas (2D ou WebGL) pixel a pixel e devolve-o em NUMEROS e em grelha de luz, mais uma "
    "miniatura - e o unico caminho para julgar o que esta desenhado num canvas, onde o DOM nao chega "
    "(holograma, jogo, grafico, WebGL), e forca a leitura dentro de um frame para nao trazer o buffer "
    "ja descartado; 'print' entrega uma imagem da regiao pedida "
    "(do seletor ou de um retangulo x,y,largura,altura). PREFIRA 'mapa', 'elemento' e 'consola' ao "
    "'print': o DOM responde com precisao e a imagem serve para confirmar. NAO confundir com "
    "tool_capturar_print, que tira um print do ecra do sistema e nao sabe nada do DOM.",
    {
        "acao": {
            "tipo": "STRING", "obrig": True, "padrao": "estado",
            "enum": list(ACOES_DE_OBSERVACAO),
            "desc": "'mapa' (indice de tudo o que responde a um gesto, com rotulo e coordenada - comece por aqui), 'estado' (o que esta carregado), 'consola' (erros e avisos da pagina), 'rede' (pedidos que falharam: 404, 500, ligacao recusada), 'elemento' (localizar por seletor ou texto), 'avaliar' (correr JS na pagina; com 'durante' devolve a serie de amostras ao longo do tempo), 'estilo' (o desenho de um elemento ou da pagina: medidas, cores, fontes, transicoes - para replicar um layout), 'canvas' (o quadro de um canvas em numeros e grelha de luz: a unica forma de julgar o que esta desenhado onde o DOM nao chega - 2D ou WebGL, com a vista a frente ou escondida), 'print' (imagem de uma regiao).",
        },
        "seletor": {
            "tipo": "STRING", "obrig": False, "padrao": "",
            "desc": "Seletor CSS do alvo ('#btn-send', '.editor-tab'). Em 'elemento' devolve todos os que casam; em 'print' recorta a imagem ao primeiro; em 'estilo' devolve o desenho dele (com o pai e os filhos) - vazio devolve o desenho da pagina inteira; em 'canvas' escolhe o canvas (vazio le o maior da pagina).",
        },
        "seletores": {
            "tipo": "STRING", "obrig": False, "padrao": "",
            "desc": "VARIOS seletores numa so chamada, um por linha, em 'estilo' e 'elemento': devolve um bloco por alvo em vez de uma chamada por elemento - o caminho para medir uma lista de pecas (as linhas de uma tabela, os campos de um formulario) sem gastar uma chamada por peca. Ignorado nas outras acoes.",
        },
        "texto": {
            "tipo": "STRING", "obrig": False, "padrao": "",
            "desc": "Em 'elemento': o que esta escrito no elemento (texto visivel, value, aria-label, placeholder ou title). Alternativa ao seletor quando nao conhece a estrutura da pagina.",
        },
        "regiao": {
            "tipo": "STRING", "obrig": False, "padrao": "",
            "desc": "Em 'print': retangulo 'x,y,largura,altura' em pixeis da janela do preview. Vazio imprime a janela inteira. Regioes pequenas chegam nitidas ao modelo.",
        },
        "grelha": {
            "tipo": "INTEGER", "obrig": False, "padrao": 0,
            "desc": "Em 'canvas': colunas da grelha de luz (padrao 48, teto 160). O numero de linhas sai da proporcao do canvas; 48x26 chega para ver onde esta a luz e onde esta o vazio.",
        },
        "js": {
            "tipo": "STRING", "obrig": False, "padrao": "",
            "desc": "Em 'avaliar': a expressao JavaScript a correr na pagina. Use 'document.querySelectorAll(...).length' ou 'document.title' para perguntas curtas. Com 'durante', tem de ser uma EXPRESSAO cujo valor se amostra (ex: 'document.querySelector(\".x\").getBoundingClientRect().height').",
        },
        "durante": {
            "tipo": "INTEGER", "obrig": False, "padrao": 0,
            "desc": "Em 'avaliar': amostra o valor de 'js' ao longo deste tempo, em ms (0 = uma leitura unica, o normal). E o caminho para VER O QUE SE MEXE: uma transicao a acontecer, um carregamento a subir, um contador a avancar - 800 a 3000 apanha qualquer um. Teto de 8000.",
        },
        "intervalo": {
            "tipo": "INTEGER", "obrig": False, "padrao": 0,
            "desc": "Em 'avaliar' com 'durante': ms entre amostras (padrao 50, minimo 10). 40 e o suficiente para uma transicao de 0.4s sair com 8 a 10 pontos.",
        },
        "nivel": {
            "tipo": "STRING", "obrig": False, "padrao": "",
            "desc": "Em 'consola' e 'rede': filtra por 'erro', 'aviso', 'log' ou 'depuracao'. Vazio devolve tudo.",
        },
        "limite": {
            "tipo": "INTEGER", "obrig": False, "padrao": 0,
            "desc": "Maximo de elementos a listar em 'elemento' (padrao 20) e em 'mapa' (padrao 120). Aumente se a pagina for densa e faltarem botoes no retorno.",
        },
        "tela": {
            "tipo": "STRING", "obrig": False, "padrao": "preview",
            "enum": ["preview", "janela"],
            "desc": "ONDE olhar: 'preview' (a pagina aberta no visualizador, por omissao) ou 'janela' (a propria interface do Axio - o mesmo mapa, consola, JS, estilo e print, mas no Chromium que desenha a aplicacao). Use 'janela' para medir a fluidez dos efeitos, ler os erros de JS do proprio Axio ou conferir um elemento do ecra.",
        },
        "largura": {
            "tipo": "INTEGER", "obrig": False, "padrao": 0,
            "desc": "LARGURA EM PIXEIS em que a pagina e disposta antes de medir (emulacao de viewport pelo CDP) - e o caminho para provar o CSS de telemovel: 390 para um telefone moderno, 360 para um pequeno, 768 para um tablet. Sem isto mede-se a largura real da janela. Vale em 'elemento', 'mapa', 'estilo', 'avaliar', 'canvas', 'quadros', 'print' e nos gestos. A medicao e desfeita no fim do pedido (a janela volta ao tamanho normal).",
        },
        "altura": {
            "tipo": "INTEGER", "obrig": False, "padrao": 0,
            "desc": "Altura em pixeis da emulacao de viewport (por omissao 844, a de um telefone). So tem efeito com 'largura'.",
        },
        "mobile": {
            "tipo": "BOOLEAN", "obrig": False, "padrao": False,
            "desc": "Com 'largura': true emula um TELEMOVEL a serio (respeita o viewport meta da pagina - uma pagina sem meta fica com 980 px de layout, como num telefone). false (por omissao) forca a disposicao exatamente na largura pedida, que e o que faz disparar as media queries.",
        },
        "espera": {
            "tipo": "INTEGER", "obrig": False, "padrao": 0,
            "desc": "Em 'avaliar': milissegundos a aguardar ANTES de correr a expressao (ate 10000). Use quando a pagina acabou de ser carregada ou de reagir a um clique e o elemento ainda nao existe.",
        },
        "tempo": {
            "tipo": "INTEGER", "obrig": False, "padrao": 0,
            "desc": "Em 'avaliar': segundos de paciencia antes de desistir (por omissao 8, teto 45). Suba-o para uma expressao que percorre uma pagina grande ou espera pedidos; quando estoura, a resposta diz o que a pagina estava a fazer, em vez de culpar um leitor que nao existe.",
        },
        "alvo": {
            "tipo": "STRING", "obrig": False, "padrao": "",
            "desc": "Em 'carregar': o endereco a abrir no preview (http://..., localhost:8099, ou um caminho do projeto). Em 'mostrar': nada. Estas duas acoes existem aqui e em tool_operar_preview - sao as mesmas.",
        },
    },
)
def tool_observar_preview(acao="estado", seletor="", texto="", regiao="", js="", durante=0, intervalo=0, nivel="", limite=0, grelha=0, tela="preview", largura=0, altura=0, mobile=False, espera=0, tempo=0, alvo="", seletores=""):
    ponte_preview = _Ponte(tela)
    pedido = str(acao or "estado").strip().lower()
    if pedido not in ACOES_DE_OBSERVACAO:
        return f"ERRO: acao desconhecida '{acao}'. Use uma de: {', '.join(ACOES_DE_OBSERVACAO)}."
    medida = {"largura": int(largura or 0), "altura": int(altura or 0), "mobile": bool(mobile)}
    if pedido in ("carregar", "mostrar"):
        return tool_operar_preview(acao=pedido, alvo=alvo or texto, tela=tela)
    if pedido == "print" and medida["largura"]:
        emit_event("executing", function=f"Imprimindo o preview a {medida['largura']} px de largura")
    if pedido == "consola":
        emit_event("executing", function="Lendo a consola do preview")
    elif pedido == "rede":
        emit_event("executing", function="Lendo a rede do preview")
    elif pedido == "mapa":
        emit_event("executing", function="Mapeando a pagina do preview")
    elif pedido == "estilo":
        emit_event("executing", function="Lendo o desenho da pagina do preview")
    elif pedido == "canvas":
        emit_event("executing", function="Lendo o quadro do canvas do preview")
    elif pedido == "quadros":
        emit_event("executing", function="Medindo o ritmo de desenho")
    elif pedido == "print":
        emit_event("executing", function="Imprimindo o preview")

    if pedido == "estado":
        dados, erro = ponte_preview.pedir("estado")
        if erro:
            return f"ERRO: {erro}."
        return _com_alvo(_texto_do_estado(dados), dados)

    if pedido == "consola":
        dados, erro = ponte_preview.pedir("consola", nivel=nivel, limite=80)
        if erro:
            return f"ERRO: {erro}."
        return _com_alvo(_texto_da_consola(dados), dados)

    if pedido == "rede":
        dados, erro = ponte_preview.pedir("rede", nivel=nivel, limite=80)
        if erro:
            return f"ERRO: {erro}."
        return _com_alvo(_texto_da_rede(dados), dados)

    alvos = _seletores_em_lote(seletores)
    if alvos and pedido in ("estilo", "elemento"):
        return _em_lote(pedido, alvos, limite, medida)

    if pedido == "elemento":
        if not (seletor.strip() or texto.strip()):
            return "ERRO: indique 'seletor' (CSS) ou 'texto' (o que esta escrito no elemento)."
        dados, erro = ponte_preview.pedir(
            "elemento", seletor=seletor, texto=texto, limite=limite, **medida
        )
        if erro:
            return f"ERRO: {erro}."
        if not dados.get("ok"):
            return f"ERRO: {dados.get('erro') or 'a pagina nao respondeu'}."
        return _com_alvo(_texto_dos_elementos(dados), dados)

    if pedido == "mapa":
        dados, erro = ponte_preview.pedir("mapa", limite=limite, **medida)
        if erro:
            return f"ERRO: {erro}."
        if not dados.get("ok"):
            return f"ERRO: {dados.get('erro') or 'a pagina nao respondeu'}."
        return _com_alvo(_texto_do_mapa(dados), dados)

    if pedido == "estilo":
        dados, erro = ponte_preview.pedir("estilo", seletor=seletor, limite=limite, **medida)
        if erro:
            return f"ERRO: {erro}."
        if not dados.get("ok"):
            return f"ERRO: {dados.get('erro') or 'a pagina nao respondeu'}."
        return _com_alvo(_texto_do_estilo(dados), dados)

    if pedido == "avaliar":
        if not js.strip():
            return "ERRO: indique 'js' com a expressao a correr na pagina."
        total = max(0, min(int(durante or 0), 8000))
        if total:
            emit_event("executing", function=f"Amostrando a pagina por {total} ms")
        dados, erro = ponte_preview.pedir(
            "avaliar", js=js, durante=total, intervalo=intervalo,
            espera=max(0, min(int(espera or 0), 10000)), tempo=int(tempo or 0), **medida
        )
        if erro:
            return f"ERRO: {erro}."
        if not dados.get("ok"):
            partes = [f"ERRO: {dados.get('erro') or 'a expressao falhou'}."]
            aviso = str(dados.get("aviso") or "").strip()
            if aviso:
                partes.append(aviso)
            return "\n".join(partes)
        resultado = dados.get("resultado")
        if total and isinstance(resultado, list):
            texto = _texto_das_amostras(js, total, resultado)
            aviso = _aviso_de_vista_escondida(tela)
            return _com_alvo(f"{aviso}\n{texto}" if aviso else texto, dados)
        if resultado is None:
            return _com_alvo(
                f"A expressao '{js[:120]}' nao devolveu valor (undefined ou null).", dados
            )
        texto_resultado = json.dumps(resultado, ensure_ascii=False, indent=2, default=str)
        return _com_alvo(
            f"Resultado de '{js[:120]}' (tipo {dados.get('tipo')}):\n{texto_resultado}", dados
        )

    if pedido == "canvas":
        dados, erro = ponte_preview.pedir("canvas", seletor=seletor, grelha=grelha, **medida)
        if erro:
            return f"ERRO: {erro}."
        if not dados.get("ok"):
            return f"ERRO: {dados.get('erro') or 'a pagina nao respondeu'}."
        return _quadro_do_canvas(dados)

    if pedido == "quadros":
        dados, erro = ponte_preview.pedir("quadros", durante=int(durante or 0), **medida)
        if erro:
            return f"ERRO: {erro}."
        if not dados.get("ok"):
            return f"ERRO: {dados.get('erro') or 'a pagina nao desenhou nada'}."
        return _com_alvo(texto_dos_quadros(dados), dados)

    return _print_do_preview(seletor, regiao, tela, largura, altura, mobile)


def _quadro_do_canvas(dados):
    """O texto do quadro e, quando ha, a miniatura da luz como imagem."""
    texto = _texto_do_canvas(dados)
    mini = dados.get("mini")
    if not mini:
        return _com_alvo(texto, dados)
    try:
        bruto = base64.b64decode(mini)
        base64_img, mime, _entregue = codificar_para_envio(bruto)
    except Exception:
        return _com_alvo(
            texto + "\nA miniatura do quadro veio ilegivel e nao pode ser entregue como imagem.",
            dados,
        )
    if not bruto:
        return _com_alvo(texto, dados)
    rotulo = f"[Quadro do canvas {dados.get('elemento') or ''}]"
    return {
        "texto": _com_alvo(texto + "\nA miniatura do quadro segue com esta resposta.", dados),
        "imagem": {"base64": base64_img, "mime": mime, "rotulo": rotulo},
    }


@register(
    "tool_operar_preview",
    "Age numa pagina do Axio com eventos a serio, nao simulados por JavaScript - no preview "
    "(por omissao) ou, com 'tela'='janela', na propria interface do Axio, com a mesma mecanica "
    "e o mesmo relato de efeito. O clique e um evento de rato do Chromium e o texto entra pelo caminho de "
    "insercao do browser, por isso funciona com React, Vue e ouvintes nativos. Use "
    "tool_observar_preview primeiro para saber ONDE esta o elemento (la, acao='mapa' devolve o "
    "indice da pagina inteira de uma so vez). acao='clicar' (por "
    "'seletor' ou pelo 'ponto' x,y), 'escrever' (texto num campo; limpar=true substitui o que "
    "la esta e, sem 'texto', esvazia-o), 'teclar' (Enter, Tab, Escape, setas), 'roteiro' (a lista "
    "dos gestos que ja sabe de antemao, numa so chamada - e a via rapida: dez gestos seguidos "
    "custam uma chamada em vez de dez, e para no primeiro que falhar), 'carregar' (abre um "
    "endereco ou um ficheiro no preview), 'recarregar' (recarrega a pagina IGNORANDO a cache, para ver codigo "
    "recem-editado sem testar uma versao velha), 'mostrar' (traz a janela do preview para a "
    "frente, para o utilizador ver o que esta a ser feito) e 'ficheiro' (poe um ficheiro do disco "
    "num campo de ficheiro da pagina - envio de imagem, anexo - SEM abrir a janela do Windows: o "
    "campo recebe o ficheiro e o evento de mudanca, e a pagina reage como se o utilizador o tivesse escolhido). "
    "'arrastar' cobre o gesto que um canvas exige e que um clique nao substitui: press no "
    "primeiro ponto, movimentos e release no ultimo, com o botao premido todo o caminho "
    "(desenhar, panoramizar, arrastar um objeto); 'roda' e a roda do rato por cima de um ponto "
    "(o zoom de um mapa ou de um desenho). 'clicar', 'escrever', 'teclar', 'arrastar' e 'roda' "
    "devolvem ja o EFEITO do gesto - se a pagina mudou, se o campo guardou mesmo o texto e os "
    "erros ou pedidos falhados que ele causou - por isso nao precisa de uma segunda chamada "
    "so para saber o que aconteceu.",
    {
        "acao": {
            "tipo": "STRING", "obrig": True, "padrao": "",
            "enum": list(ACOES_DE_OPERACAO),
            "desc": "'clicar', 'escrever', 'teclar', 'arrastar' (traco continuo do rato entre pontos - desenhar, panoramizar, puxar um objeto), 'roda' (roda do rato por cima de um ponto: o zoom de um mapa ou de um desenho), 'roteiro' (varios gestos numa so chamada), 'carregar' (abrir endereco ou ficheiro), 'recarregar' (recarregar ignorando a cache), 'mostrar' (trazer o preview para a frente) ou 'ficheiro' (colocar um ficheiro do disco num campo de ficheiro da pagina, sem abrir a janela do Windows).",
        },
        "seletor": {
            "tipo": "STRING", "obrig": False, "padrao": "",
            "desc": "Seletor CSS do alvo a clicar ou do campo onde escrever. Prefira-o ao 'ponto': o alvo e recalculado no instante do gesto, mesmo que a pagina se tenha mexido, e o estado dele (classes e tamanho do valor) entra no relato do efeito.",
        },
        "ponto": {
            "tipo": "STRING", "obrig": False, "padrao": "",
            "desc": "Em 'clicar' e 'roda': 'x,y' em pixeis da janela do preview, como devolvido por tool_observar_preview. Em 'arrastar': o caminho do traco, com dois ou mais pontos separados por espaco ('x1,y1 x2,y2 ...'), o mesmo formato da ferramenta das janelas nativas.",
        },
        "alvo": {
            "tipo": "STRING", "obrig": False, "padrao": "",
            "desc": "Em 'carregar': o endereco (localhost:5000, http://..., uma letra de unidade ou um caminho a partir da raiz do projeto). Em 'ficheiro': o caminho do ficheiro a colocar no campo de ficheiro da pagina (relativo a raiz do projeto, ou absoluto).",
        },
        "texto": {
            "tipo": "STRING", "obrig": False, "padrao": "",
            "desc": "Em 'escrever': o texto a inserir no campo. Em 'roda': quantos pixeis rolar (negativo aproxima, positivo afasta; por omissao -240).",
        },
        "limpar": {
            "tipo": "BOOLEAN", "obrig": False, "padrao": False,
            "desc": "Em 'escrever': true substitui o que ja esta no campo (seleciona tudo antes de inserir); sem 'texto', esvazia o campo.",
        },
        "tecla": {
            "tipo": "STRING", "obrig": False, "padrao": "",
            "desc": "Em 'teclar': a tecla a premir (Enter, Tab, Escape, Backspace, Delete, Space, Home, End, PageUp, PageDown, ArrowUp, ArrowDown, ArrowLeft, ArrowRight).",
        },
        "passos": {
            "tipo": "STRING", "obrig": False, "padrao": "",
            "desc": "Em 'roteiro': os gestos, na ordem. DOIS formatos, os dois validos: (a) lista JSON, cada gesto um objeto - [{\"acao\":\"clicar\",\"seletor\":\"#btn-x\"},{\"acao\":\"escrever\",\"seletor\":\"#campo\",\"texto\":\"oi\",\"limpar\":true},{\"acao\":\"teclar\",\"tecla\":\"Enter\"}]; (b) um gesto POR LINHA, com o alvo a seguir a acao - 'clicar #btn-x', 'escrever #campo | oi', 'teclar Enter', 'esperar 500', 'recarregar'. Vale a acao 'esperar' com os milissegundos. Corre tudo numa so chamada e para no primeiro gesto que falhar. Cada passo aceita tambem 'espera' em milissegundos (ate 5000), aguardada ANTES do gesto: use quando o passo anterior abre ou fecha algo com animacao, para o gesto seguinte agir na pagina ja parada.",
        },
        "largura": {
            "tipo": "INTEGER", "obrig": False, "padrao": 0,
            "desc": "LARGURA EM PIXEIS em que a pagina e disposta antes do gesto (emulacao de viewport pelo CDP): use 390 para agir e medir como num telemovel. Sem isto, a largura real da janela. Vale em 'clicar', 'escrever', 'teclar', 'arrastar' e 'roda'; a emulacao e desfeita no fim do pedido.",
        },
        "altura": {
            "tipo": "INTEGER", "obrig": False, "padrao": 0,
            "desc": "Altura em pixeis da emulacao de viewport (por omissao 844, a de um telefone). So tem efeito com 'largura'.",
        },
        "mobile": {
            "tipo": "BOOLEAN", "obrig": False, "padrao": False,
            "desc": "Com 'largura': true emula um TELEMOVEL a serio (respeita o viewport meta); false (por omissao) forca a disposicao exatamente na largura pedida.",
        },
        "repetir": {
            "tipo": "BOOLEAN", "obrig": False, "padrao": False,
            "desc": "Em 'clicar': por omissao UM gesto e UM evento - se nada mudar, a ferramenta espera de novo e diz que nao mudou, sem repetir o clique (um botao que grava nao pode ser disparado duas vezes as escuras). Com repetir=true, e disparado uma segunda vez quando a primeira nao provocou mudanca observavel - use so quando souber que o botao nao grava nada.",
        },
        "tela": {
            "tipo": "STRING", "obrig": False, "padrao": "preview",
            "enum": ["preview", "janela"],
            "desc": "ONDE agir: 'preview' (a pagina aberta no visualizador, por omissao) ou 'janela' (a propria interface do Axio - o mesmo clique, texto, teclas e roteiro, mas no Chromium que desenha a aplicacao). Use 'janela' para exercitar a interface do proprio Axio, com o mesmo relato de efeito.",
        },
    },
)
def tool_operar_preview(acao="", seletor="", ponto="", alvo="", texto="", limpar=False, tecla="", passos="", tela="preview", largura=0, altura=0, mobile=False, repetir=False):
    ponte_preview = _Ponte(tela)
    pedido = str(acao or "").strip().lower()
    if pedido not in ACOES_DE_OPERACAO:
        return f"ERRO: acao desconhecida '{acao}'. Use uma de: {', '.join(ACOES_DE_OPERACAO)}."
    emit_event("executing", function=f"Agindo no preview: {pedido}")
    medida = {"largura": int(largura or 0), "altura": int(altura or 0), "mobile": bool(mobile)}

    ignorado = _argumento_ignorado(pedido, {
        "seletor": seletor, "ponto": ponto, "alvo": alvo,
        "texto": texto, "limpar": limpar, "tecla": tecla, "passos": passos,
    })
    if ignorado:
        return ignorado

    if pedido == "carregar":
        destino = (alvo or texto).strip()
        if not destino:
            return "ERRO: indique 'alvo' com o endereco ou o ficheiro a abrir no preview."
        if _e_rota_do_servidor(destino):
            destino = _origem_do_servidor() + destino
        elif not _e_endereco(destino):
            convertido, motivo = _endereco_do_ficheiro(destino)
            if convertido:
                destino = convertido
            elif destino.startswith("/") and not destino.startswith("//"):
                destino = _origem_do_servidor() + destino
            elif motivo:
                return f"ERRO: {motivo}."
        dados, erro = ponte_preview.pedir("carregar", alvo=destino)
        if erro:
            return f"ERRO: {erro}."
        if not dados.get("ok"):
            return f"ERRO: {dados.get('erro') or 'nao foi possivel carregar'}."
        aviso = _renovar_pagina_local(destino)
        ficou = str(dados.get("alvo") or destino)
        for _ in range(20):
            estado, falha_estado = ponte_preview.pedir("estado")
            if falha_estado:
                break
            if not estado.get("carregando"):
                ficou = str(estado.get("url") or ficou)
                break
            time.sleep(0.15)
        nota = ""
        if ficou.rstrip("/") != str(dados.get("alvo") or destino).rstrip("/"):
            nota = (
                f" ATENCAO: pedi {dados.get('alvo') or destino} e a barra do preview ficou em"
                f" {ficou} - a pagina navegou ou recusou a navegacao. E o que ficou que conta."
            )
        return (f"Preview carregado: {ficou}.{aviso}{nota} "
                "Use acao='estado' para confirmar.")

    if pedido == "mostrar":
        dados, erro = ponte_preview.pedir("mostrar")
        if erro:
            return f"ERRO: {erro}."
        return "O preview passou para a frente na janela do Axio."

    if pedido == "recarregar":
        dados, erro = ponte_preview.pedir("recarregar")
        if erro:
            return f"ERRO: {erro}."
        if not dados.get("ok"):
            return f"ERRO: {dados.get('erro') or 'nao foi possivel recarregar o preview'}."
        estado = "ja carregada" if dados.get("pronto") else "ainda a carregar"
        linha = (f"Preview recarregado sem cache ({dados.get('url') or 'pagina atual'}, {estado}). "
                 "Se acabou de editar frontend, e este o codigo novo: use acao='consola' para "
                 "ver os erros dele.")
        modulos = dados.get("modulos")
        if isinstance(modulos, list) and modulos:
            do_cache = [m.get("ficheiro") for m in modulos if m.get("do_cache")]
            if do_cache:
                linha += (
                    f" ATENCAO: {len(do_cache)} ficheiro(s) de codigo vieram da CACHE"
                    f" ({', '.join(str(n) for n in do_cache[:6])}) - se editei um destes, o que se"
                    " mede agora ainda pode ser a versao antiga."
                )
            else:
                linha += (
                    f" {len(modulos)} ficheiro(s) de codigo revalidados, nenhum veio da cache."
                )
        return linha

    if pedido == "clicar":
        if seletor.strip():
            dados, erro = ponte_preview.pedir(
                "clicar", seletor=seletor, repetir=bool(repetir), **medida
            )
            onde = seletor
        else:
            posicao, falha = _ponto_do_texto(ponto)
            if falha:
                return f"ERRO: {falha}."
            dados, erro = ponte_preview.pedir(
                "clicar", x=posicao[0], y=posicao[1], repetir=bool(repetir), **medida
            )
            onde = ponto
        if erro:
            return f"ERRO: {erro}."
        if not dados.get("ok"):
            return f"ERRO: {dados.get('erro') or 'o clique falhou'}."
        return _com_efeito(f"Clique feito em {onde} (x={dados.get('x')}, y={dados.get('y')}).", dados)

    if pedido == "arrastar":
        lista, falha = _pontos_do_texto(ponto)
        if falha:
            return f"ERRO: {falha}."
        dados, erro = ponte_preview.pedir("arrastar", pontos=[list(par) for par in lista], **medida)
        if erro:
            return f"ERRO: {erro}."
        if not dados.get("ok"):
            return f"ERRO: {dados.get('erro') or 'o arrasto falhou'}."
        primeiro = lista[0]
        return _com_efeito(
            f"Arrasto de {primeiro[0]},{primeiro[1]} ate (x={dados.get('x')}, y={dados.get('y')})"
            f" em {len(lista)} ponto(s) e {dados.get('movimentos')} movimento(s) - botao premido"
            " todo o caminho.",
            dados
        )

    if pedido == "roda":
        posicao, _ = _ponto_do_texto(ponto)
        delta = None
        if str(texto or "").strip():
            try:
                delta = int(round(float(str(texto).strip())))
            except ValueError:
                return (f"ERRO: em 'roda', 'texto' e quanto rolar em pixeis (negativo aproxima,"
                        f" positivo afasta); '{texto}' nao e um numero.")
        if posicao:
            dados, erro = ponte_preview.pedir("roda", x=posicao[0], y=posicao[1], delta=delta, **medida)
            onde = ponto
        elif seletor.strip():
            dados, erro = ponte_preview.pedir("roda", seletor=seletor, delta=delta, **medida)
            onde = seletor
        else:
            return "ERRO: indique 'ponto' (x,y) ou 'seletor' no sitio onde a roda deve girar."
        if erro:
            return f"ERRO: {erro}."
        if not dados.get("ok"):
            return f"ERRO: {dados.get('erro') or 'a roda falhou'}."
        sentido = "para cima (aproxima)" if (dados.get("delta") or 0) < 0 else "para baixo (afasta)"
        return _com_efeito(
            f"Roda girada {sentido} {dados.get('delta')} px em {onde}"
            f" (x={dados.get('x')}, y={dados.get('y')}).",
            dados
        )

    if pedido == "escrever":
        if not texto and not limpar:
            return ("ERRO: indique 'texto' com o que escrever, ou 'limpar' com o campo "
                    "indicado em 'seletor' para o esvaziar.")
        do_cofre = cofre.tem_placeholders(texto)
        texto, erro_cofre = cofre.resolver_ou_erro(texto)
        if erro_cofre:
            return f"ERRO: {erro_cofre}."
        dados, erro = ponte_preview.pedir(
            "escrever", seletor=seletor, texto=texto, limpar=bool(limpar), **medida
        )
        if erro:
            return f"ERRO: {erro}."
        if not dados.get("ok"):
            return f"ERRO: {dados.get('erro') or 'nao foi possivel escrever'}."
        destino = f" no campo '{seletor}'" if seletor.strip() else " no campo com o foco"
        if not texto and limpar:
            return _com_efeito(f"Campo esvaziado{destino}.", dados)
        origem = " (valor guardado, vindo do cofre)" if do_cofre else ""
        return _com_efeito(f"Escritos {dados.get('escrito')} caractere(s){destino}{origem}."
                           + _texto_da_conferencia(dados.get("conferencia")), dados)

    if pedido == "roteiro":
        lista, falha = _passos_do_roteiro(passos)
        if falha:
            return f"ERRO: {falha}."
        emit_event("executing", function=f"Correndo roteiro de {len(lista)} gesto(s)")
        return _correr_roteiro(lista, tela, medida)

    if pedido == "ficheiro":
        caminho = (alvo or texto).strip()
        if not caminho:
            return ("ERRO: indique em 'alvo' o ficheiro a colocar no campo de ficheiro da pagina "
                    "(por exemplo uma imagem de perfil).")
        destino, falha = resolver_caminho_arquivo(caminho)
        if falha:
            return f"ERRO: {falha}."
        if not os.path.isfile(destino):
            return f"ERRO: nao existe nenhum ficheiro em {destino}."
        dados, erro = ponte_preview.pedir("ficheiro", caminho=destino, seletor=seletor)
        if erro:
            return f"ERRO: {erro}."
        if not dados.get("ok"):
            return f"ERRO: {dados.get('erro') or 'o campo recusou o ficheiro'}."
        via = " (pelo escolhedor que a propria pagina tinha aberto)" if dados.get("do_escolhedor") else ""
        return (f"Ficheiro colocado no campo da pagina: {destino}{via}. "
                "O campo ja recebeu o evento de mudanca; confirme pelo efeito no ecra.")

    dados, erro = ponte_preview.pedir("teclar", tecla=tecla, **medida)
    if erro:
        return f"ERRO: {erro}."
    if not dados.get("ok"):
        return f"ERRO: {dados.get('erro') or 'a tecla falhou'}."
    return _com_efeito(f"Tecla {dados.get('tecla')} premida na pagina.", dados)
