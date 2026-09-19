"""Auditoria e edicao de comentarios de codigo, por linguagem.

Camada de ESCRITA do auditor: filtra, substitui, remove e grava comentarios,
com undo e rollback automatico. A deteccao lexica (que extensao usa que modo e
onde cada comentario comeca) vive em `tools/comments_lexer.py` e e importada
daqui - este modulo nao sabe tokenizar linguagem nenhuma.

Seguranca da escrita: valida a sintaxe EM MEMORIA antes de gravar (python,
css, json), confirma DEPOIS de gravar (js/ts) e REVERTE sozinho se o
resultado quebrar - o ficheiro nunca fica pior do que estava. Toda a escrita
entra na pilha de undo (tool_desfazer) e o retorno traz o SHA-256 antes e
depois, para conferencia (passe 'hash_arquivo_esperado' para recusar editar um
ficheiro que mudou desde a listagem).
"""

import os

from src.backend.services.file_service import caminho_contido, desfazer_edicao, raiz_abs, resolver_caminho
from src.backend.state import emit_event
from src.backend.tools.comments_lexer import (
    IGNORAR_PASTAS, TIPOS_DE_COMENTARIO, detetar, linguagem_de,
    modo_de, montar_comentarios, resumo, sha,
)
from src.backend.tools.edit import gravar_edicao_com_diff
from src.backend.tools.registry import register
from src.backend.tools.syntax import validar_texto


def _fim_de_linha(linha):
    if linha.endswith("\r\n"):
        return "\r\n"
    if linha.endswith("\n"):
        return "\n"
    return ""

def _filtrar(registos, tipo, linha_inicio, linha_fim, filtro_texto, hash_alvo, excluir_docstrings=False):
    """Aplica os filtros comuns ao listar/remover/substituir.

    Docstrings so saem quando o tipo e pedido explicitamente ('docstring' ou
    'todos'): uma remocao sem tipo nao apaga docstrings por acidente.
    """
    saida = []
    agulha = (filtro_texto or "").strip().lower()
    for reg in registos:
        if hash_alvo and reg["hash"] != hash_alvo.strip():
            continue
        if tipo and tipo not in ("todos", "tudo") and reg["tipo"] != tipo:
            continue
        if not tipo and excluir_docstrings and reg["tipo"] == "docstring":
            continue
        if linha_inicio is not None and reg["fim_linha"] < linha_inicio:
            continue
        if linha_fim is not None and reg["linha"] > linha_fim:
            continue
        if agulha and agulha not in reg["resumo"].lower():
            continue
        saida.append(reg)
    return saida

def _remover_alvos(texto, alvos):
    """Reconstroi o texto sem os comentarios indicados (de tras para a frente).

    Comentario sozinho na linha -> a linha inteira sai. Comentario depois de
    codigo -> so o comentario sai (o codigo fica, sem espaco pendurado).
    """
    linhas = texto.splitlines(keepends=True)
    for reg in sorted(alvos, key=lambda r: (r["linha"], r["col"]), reverse=True):
        linha_ini, col = reg["linha"], reg["col"]
        linha_fim, fim_col = reg["fim_linha"], reg["fim_col"]
        if linha_ini < 1 or linha_fim > len(linhas):
            continue
        prefixo = linhas[linha_ini - 1][:col]
        sufixo = linhas[linha_fim - 1][fim_col:]
        if not prefixo.strip() and not sufixo.strip():
            del linhas[linha_ini - 1:linha_fim]
            continue
        eol = _fim_de_linha(linhas[linha_fim - 1]) or _fim_de_linha(linhas[linha_ini - 1])
        if prefixo.strip():
            linhas[linha_ini - 1] = prefixo.rstrip() + (sufixo if sufixo.strip() else eol)
        else:
            linhas[linha_ini - 1] = sufixo.lstrip() if sufixo.strip() else eol
        if linha_fim > linha_ini:
            del linhas[linha_ini:linha_fim]
    return "".join(linhas)

def _substituir_alvo(texto, reg, novo_conteudo):
    """Troca o corpo de UM comentario, preservando os delimitadores."""
    linhas = texto.splitlines(keepends=True)
    abre, fecha = reg["abre"], reg["fecha"]
    espaco_abre = " " if reg.get("espaco_abre") else ""
    espaco_fecha = " " if reg.get("espaco_fecha") and fecha else ""
    novo = abre + espaco_abre + novo_conteudo + espaco_fecha + fecha
    linha_ini, col = reg["linha"], reg["col"]
    linha_fim, fim_col = reg["fim_linha"], reg["fim_col"]
    prefixo = linhas[linha_ini - 1][:col]
    sufixo = linhas[linha_fim - 1][fim_col:]
    linhas[linha_ini - 1] = prefixo + novo + sufixo
    if linha_fim > linha_ini:
        del linhas[linha_ini:linha_fim]
    return "".join(linhas)

def _ler_ficheiro(abs_path):
    try:
        with open(abs_path, "r", encoding="utf-8") as fh:
            return fh.read(), None
    except UnicodeDecodeError:
        return None, "ERRO: o ficheiro nao e UTF-8; edicao abortada para nao corromper os bytes."
    except OSError as e:
        return None, f"ERRO ao ler o ficheiro: {e}"

def _listar_ficheiro(abs_path, rotulo, tipo, linha_inicio, linha_fim, filtro_texto, incluir_docstrings):
    """(linhas_texto, total_encontrado, total_filtrado, sha) de um ficheiro."""
    texto, erro = _ler_ficheiro(abs_path)
    if erro:
        return [f"  {rotulo}: {erro}"], 0, 0, ""
    modo, achados = detetar(abs_path, texto, incluir_docstrings)
    if not modo:
        return [], 0, 0, sha(texto)
    linhas = texto.splitlines(keepends=True)
    registos = montar_comentarios(linhas, achados, modo)
    selecionados = _filtrar(registos, tipo, linha_inicio, linha_fim, filtro_texto, None)
    cabecalho = (f"{rotulo}  [{linguagem_de(abs_path)}]  sha={sha(texto)[:12]}  "
                 f"{len(selecionados)}/{len(registos)} comentario(s)")
    corpo = [cabecalho]
    for reg in selecionados:
        faixa = f"L{reg['linha']}" if reg["linha"] == reg["fim_linha"] else f"L{reg['linha']}-{reg['fim_linha']}"
        corpo.append(f"  {faixa:<12} {reg['tipo']:<9} hash={reg['hash']}  {reg['resumo']}")
    return corpo, len(registos), len(selecionados), sha(texto)

def _acao_listar(abs_path, max_caracteres, tipo, linha_inicio, linha_fim, filtro_texto, incluir_docstrings):
    alvos = _arquivos_alvo(abs_path)
    if not alvos:
        return "ERRO: nenhum ficheiro com linguagem suportada encontrado."
    linhas_saida = []
    total = 0
    filtrados = 0
    usados = 0
    truncado = False
    for caminho in alvos:
        bloco, n_total, n_filtrados, _ = _listar_ficheiro(
            caminho, _rotulo_rel(caminho), tipo, linha_inicio, linha_fim, filtro_texto, incluir_docstrings)
        if not bloco:
            continue
        total += n_total
        filtrados += n_filtrados
        if n_filtrados == 0 and not _qualquer_filtro(tipo, linha_inicio, linha_fim, filtro_texto):
            continue
        for linha in bloco:
            usados += len(linha) + 1
            if usados > max_caracteres:
                truncado = True
                break
            linhas_saida.append(linha)
        if truncado:
            break
    if not linhas_saida:
        if truncado:
            detalhe = (f"{filtrados} comentario(s) correspondem aos filtros"
                       if _qualquer_filtro(tipo, linha_inicio, linha_fim, filtro_texto)
                       else f"{total} comentario(s) existem")
            return (f"AVISO: o teto de {max_caracteres} caracteres nao deu para listar nada, mas "
                    f"{detalhe} em {len(alvos)} ficheiro(s). Aumente 'max_caracteres' ou refine "
                    "com 'linha_inicio'/'linha_fim', 'tipo' ou 'filtro_texto'.")
        if _qualquer_filtro(tipo, linha_inicio, linha_fim, filtro_texto):
            return (f"Nenhum comentario corresponde aos filtros ({len(alvos)} ficheiro(s) "
                    f"varrido(s), com comentarios) - nada foi alterado.")
        return (f"Nenhum comentario: {len(alvos)} ficheiro(s) de linguagem suportada "
                f"varrido(s), todos sem comentarios.")
    cabecalho = f"COMENTARIOS ({len(alvos)} ficheiro(s) varrido(s), {total} no total, {filtrados} selecionado(s)):"
    rodape = []
    if truncado:
        rodape.append(f"AVISO: saida truncada em ~{max_caracteres} caracteres. "
                      "Refine com 'linha_inicio'/'linha_fim', 'tipo' ou 'filtro_texto', "
                      "ou aumente 'max_caracteres'.")
    rodape.append("Para editar: acao='substituir' (hash_alvo ou linha_inicio/linha_fim + texto_novo) "
                  "ou acao='remover' (mesmos filtros).")
    return "\n".join([cabecalho] + linhas_saida + [""] + rodape)

def _qualquer_filtro(tipo, linha_inicio, linha_fim, filtro_texto):
    return bool(tipo or linha_inicio is not None or linha_fim is not None or filtro_texto)

def _arquivos_alvo(abs_path):
    """Ficheiros com linguagem suportada: o proprio ficheiro ou a pasta (recursivo)."""
    if os.path.isfile(abs_path):
        return [abs_path]
    if not os.path.isdir(abs_path):
        return []
    saida = []
    for raiz, dirs, arquivos in os.walk(abs_path):
        dirs[:] = [d for d in dirs if d not in IGNORAR_PASTAS and not d.startswith(".")]
        for nome in sorted(arquivos):
            caminho = os.path.join(raiz, nome)
            if modo_de(caminho):
                saida.append(caminho)
    return sorted(saida)

def _rotulo_rel(abs_path):
    raiz = raiz_abs()
    if raiz and caminho_contido(abs_path, raiz):
        return os.path.relpath(abs_path, raiz).replace(os.sep, "/")
    return abs_path.replace(os.sep, "/")

def _aplicar_e_gravar(abs_path, rotulo, antigo, novo, rotulo_acao):
    """Grava com undo + diff e REVERTE se a sintaxe quebrar. Devolve (ok, mensagem)."""
    erro_memoria = validar_texto(rotulo, novo)
    if erro_memoria:
        return False, (f"ERRO: a edicao deixaria o ficheiro com sintaxe invalida - nada foi gravado.\n"
                       f"{erro_memoria}")
    try:
        avisos = gravar_edicao_com_diff(rotulo, abs_path, antigo, novo, rotulo_acao)
    except ValueError as e:
        return False, f"ERRO: {e}"
    except Exception as e:
        return False, f"ERRO ao gravar: {e}"
    if "AVISO SINTAXE" in (avisos or ""):
        desfazer_edicao(abs_path)
        return False, ("ERRO: a edicao quebrou a sintaxe e foi REVERTIDA automaticamente - "
                       "o ficheiro esta como estava." + (avisos or ""))
    return True, (avisos or "")

def _editar_ficheiro(abs_path, rotulo, acao, tipo, linha_inicio, linha_fim, filtro_texto,
                     hash_alvo, texto_novo, preview, incluir_docstrings):
    texto, erro = _ler_ficheiro(abs_path)
    if erro:
        return 0, erro, False
    modo, achados = detetar(abs_path, texto, incluir_docstrings)
    if not modo:
        return 0, f"{rotulo}: extensao sem suporte para comentarios.", False
    linhas = texto.splitlines(keepends=True)
    registos = montar_comentarios(linhas, achados, modo)
    alvos = _filtrar(registos, tipo, linha_inicio, linha_fim, filtro_texto, hash_alvo,
                     excluir_docstrings=(acao == "remover"))
    if not alvos:
        return 0, f"{rotulo}: nenhum comentario corresponde aos filtros.", False

    if acao == "substituir":
        if len(alvos) > 1:
            return 0, (f"{rotulo}: {len(alvos)} comentarios correspondem - a substituicao exige UM unico alvo. "
                       "Use 'hash_alvo' ou 'linha_inicio'/'linha_fim' para o isolar."), False
        reg = alvos[0]
        if reg["tipo"] == "linha" and "\n" in texto_novo:
            return 0, (f"{rotulo}: um comentario de linha (L{reg['linha']}) nao pode receber texto com "
                       "quebra de linha - use um comentario de bloco."), False
        if reg["fecha"] and reg["fecha"] in texto_novo:
            return 0, (f"{rotulo}: 'texto_novo' contem o delimitador de fecho '{reg['fecha']}', "
                       "o que quebraria o comentario. Remova-o."), False
        novo = _substituir_alvo(texto, reg, texto_novo)
        antes, depois = reg["texto"], resumo(texto_novo)
    else:
        preservados = (sum(1 for reg in registos if reg["tipo"] == "docstring")
                       if not tipo else 0)
        novo = _remover_alvos(texto, alvos)
        antes = f"{len(alvos)} comentario(s)"
        depois = "removidos"
        if preservados:
            depois += (f" ({preservados} docstring(s) preservado(s): uma remocao sem 'tipo' nao "
                       "lhes toca - passe tipo='docstring')")

    if novo == texto:
        return 0, f"{rotulo}: nada mudou (a edicao seria identica ao original).", False

    if preview:
        return len(alvos), (f"PREVIEW ({rotulo}): {len(alvos)} alvo(s).\n"
                            f"  {antes} -> {depois}\n"
                            f"  SHA-256 antes:  {sha(texto)[:16]}\n"
                            f"  SHA-256 depois: {sha(novo)[:16]}\n"
                            "Nada foi gravado (preview=True)."), False

    ok, mensagem = _aplicar_e_gravar(abs_path, rotulo, texto, novo, f"Comentarios ({acao}): {rotulo}")
    if not ok:
        return 0, mensagem, False
    return len(alvos), (f"{rotulo}: {len(alvos)} alvo(s) OK.\n"
                        f"  SHA-256 antes:  {sha(texto)[:16]}\n"
                        f"  SHA-256 depois: {sha(novo)[:16]}\n"
                        f"  Recuperavel com tool_desfazer('{rotulo}').{mensagem}"), True

def _verificar_hash_esperado(abs_path, rotulo, hash_esperado):
    if not hash_esperado:
        return None
    texto, erro = _ler_ficheiro(abs_path)
    if erro:
        return f"{rotulo}: {erro}"
    if not sha(texto).startswith(hash_esperado.strip()):
        return (f"{rotulo}: HASH DIVERGENTE - o ficheiro mudou desde a listagem "
                f"(esperado {hash_esperado.strip()}, atual {sha(texto)[:16]}). Nada foi alterado.")
    return None

@register(
    "tool_auditar_comentarios",
    "Lista, substitui ou remove comentarios de codigo por linguagem (Python, JS/TS/Java/C/C++/Go/Rust, CSS, HTML/XML/Vue/Markdown, YAML/TOML/shell/Ruby/INI, SQL). A deteccao e LEXICA: strings, template literals e regex literais nunca sao confundidos com comentarios. acao='listar' mostra cada comentario com linha, tipo (linha/bloco/html/docstring) e um hash curto; 'substituir' troca o corpo de UM comentario (por hash_alvo ou linha_inicio/linha_fim + texto_novo) preservando os delimitadores; 'remover' apaga os comentarios filtrados (tipo, intervalo de linhas, hash_alvo ou filtro_texto) e REVERTE sozinho se a edicao quebrar a sintaxe. Toda a escrita entra na pilha de undo e o retorno traz o SHA-256 antes/depois (passe hash_arquivo_esperado para recusar editar um ficheiro que mudou).",
    {
        'caminho_relativo': {"tipo": "STRING", "desc": 'Ficheiro ou pasta (ex: src/backend/tools)', "obrig": True, "padrao": ""},
        'acao': {"tipo": "STRING", "desc": "'listar' (padrao), 'substituir' ou 'remover'", "padrao": "listar"},
        'tipo': {"tipo": "STRING", "desc": "Filtro: 'linha', 'bloco', 'html', 'docstring' ou 'todos'"},
        'linha_inicio': {"tipo": "INTEGER", "desc": 'Inicio do intervalo de linhas (1-based)'},
        'linha_fim': {"tipo": "INTEGER", "desc": 'Fim do intervalo de linhas'},
        'filtro_texto': {"tipo": "STRING", "desc": 'So comentarios cujo texto contenha esta substring'},
        'hash_alvo': {"tipo": "STRING", "desc": 'Hash curto de um comentario listado'},
        'texto_novo': {"tipo": "STRING", "desc": "Novo corpo do comentario (acao='substituir'), sem os delimitadores"},
        'hash_arquivo_esperado': {"tipo": "STRING", "desc": 'SHA-256 (prefixo serve) do ficheiro, para recusar editar se mudou', "padrao": ""},
        'preview': {"tipo": "BOOLEAN", "desc": 'true = mostra o que mudaria sem gravar', "padrao": False},
        'incluir_docstrings': {"tipo": "BOOLEAN", "desc": 'Inclui docstrings do Python (padrao true)', "padrao": True},
        'max_caracteres': {"tipo": "INTEGER", "desc": 'Teto de caracteres da listagem (padrao 200000)', "padrao": 200000},
    },
    disponivel="edicao",
)
def tool_auditar_comentarios(caminho_relativo, acao="listar", tipo=None, linha_inicio=None,
                             linha_fim=None, filtro_texto=None, hash_alvo=None, texto_novo=None,
                             hash_arquivo_esperado="", preview=False, incluir_docstrings=True,
                             max_caracteres=200000):
    emit_event("executing", function=f"Auditando comentarios: {caminho_relativo}")
    if not caminho_relativo:
        return "ERRO: informe 'caminho_relativo' (ficheiro ou pasta)."
    acao = (acao or "listar").strip().lower()
    if acao not in ("listar", "substituir", "remover"):
        return "ERRO: 'acao' deve ser 'listar', 'substituir' ou 'remover'."
    if tipo and tipo not in TIPOS_DE_COMENTARIO + ("todos", "tudo"):
        return f"ERRO: 'tipo' invalido. Use um de: {', '.join(TIPOS_DE_COMENTARIO)} ou 'todos'."
    if acao == "substituir" and texto_novo is None:
        return "ERRO: acao='substituir' exige 'texto_novo' (o corpo novo do comentario)."
    try:
        max_caracteres = int(max_caracteres or 200000)
    except (TypeError, ValueError):
        max_caracteres = 200000
    abs_path, erro = resolver_caminho(caminho_relativo, permitir_extra=True)
    if erro:
        return erro
    if not os.path.exists(abs_path):
        return f"ERRO: '{caminho_relativo}' nao existe."

    if acao == "listar":
        return _acao_listar(abs_path, max_caracteres, tipo, linha_inicio, linha_fim,
                            filtro_texto, incluir_docstrings)

    alvos = _arquivos_alvo(abs_path)
    if not alvos:
        return "ERRO: nenhum ficheiro com linguagem suportada nesse caminho."
    if hash_alvo and len(alvos) > 1:
        return "ERRO: 'hash_alvo' exige um ficheiro unico (passe o caminho do ficheiro, nao a pasta)."
    if preview:
        relatorios = []
        for caminho in alvos:
            _, mensagem, _ = _editar_ficheiro(
                caminho, _rotulo_rel(caminho), acao, tipo, linha_inicio, linha_fim, filtro_texto,
                hash_alvo, texto_novo, True, incluir_docstrings)
            relatorios.append(mensagem)
        return "\n".join(relatorios)

    total = 0
    gravados = 0
    relatorios = []
    truncado = False
    usados = 0
    for caminho in alvos:
        rotulo = _rotulo_rel(caminho)
        divergente = _verificar_hash_esperado(caminho, rotulo, hash_arquivo_esperado)
        if divergente:
            relatorios.append(divergente)
            continue
        n, mensagem, gravou = _editar_ficheiro(
            caminho, rotulo, acao, tipo, linha_inicio, linha_fim, filtro_texto,
            hash_alvo, texto_novo, False, incluir_docstrings)
        total += n
        gravados += 1 if gravou else 0
        if n == 0 and len(alvos) > 1 and ("nenhum comentario" in mensagem or "nada mudou" in mensagem):
            continue
        usados += len(mensagem) + 1
        if usados > max_caracteres:
            truncado = True
            relatorios.append(mensagem)
            break
        relatorios.append(mensagem)
    if not relatorios:
        return "Nenhum comentario corresponde aos filtros - nada foi alterado."
    cabecalho = (f"ACAO '{acao}': {total} comentario(s) em {gravados} ficheiro(s)."
                 if acao == "remover" else
                 f"ACAO '{acao}': {total} alvo(s) em {gravados} ficheiro(s).")
    rodape = "AVISO: relatorio truncado; refine os filtros ou aumente 'max_caracteres'." if truncado else ""
    return "\n".join([cabecalho] + relatorios + ([rodape] if rodape else []))
