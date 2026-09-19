"""Auditor de imports, orfaos e dead code de modulos JavaScript."""

import os
import re

from src.backend.services.file_service import arquivos_recursivos, resolver_caminho
from src.backend.state import emit_event
from src.backend.tools.js_lexico import (
    contar_declaracoes,
    contar_membro,
    contar_simbolo,
    exports_do_texto,
    limpar,
    ocorrencias_declaracao,
    remover_exports,
)
from src.backend.tools.registry import register


def _fontes_da_pasta_acima(files):
    """Ficheiros .js da pasta acima do alvo, para o cruzamento do que esta morto.

    Sem eles, um export consumido FORA da pasta auditada sai como candidato a apagar
    (falso positivo que convida a destruir codigo vivo) e um simbolo importado de fora
    nunca aparece como FALTANTE, porque o dono dele nao entrou na varredura.
    """
    if not files:
        return []
    pai = os.path.dirname(os.path.dirname(files[0]))
    if not pai or pai == os.path.dirname(files[0]):
        return []
    alvo = {os.path.basename(p) for p in files}
    saida = []
    for p in arquivos_recursivos(pai, ".js"):
        nome = os.path.basename(p)
        if nome in alvo or 'vendor' in p.replace('\\', '/').split('/'):
            continue
        try:
            if os.path.getsize(p) > 400000:
                continue
        except OSError:
            continue
        saida.append(p)
    return saida


def _indexar(files):
    fnames = [os.path.basename(p) for p in files]
    contents = {}
    limpos = {}
    limpos_sem_export = {}
    exports_by_file = {}
    for p, fname in zip(files, fnames):
        with open(p, "r", encoding="utf-8") as f:
            c = f.read()
        contents[fname] = c
        limpos[fname] = limpar(c)
        limpos_sem_export[fname] = remover_exports(limpos[fname])
        exports_by_file[fname] = exports_do_texto(c)

    for p in _fontes_da_pasta_acima(files):
        fname = os.path.basename(p)
        if fname in limpos:
            continue
        with open(p, "r", encoding="utf-8") as f:
            c = f.read()
        limpos[fname] = limpar(c)
        limpos_sem_export[fname] = remover_exports(limpos[fname])
        exports_by_file[fname] = exports_do_texto(c)
    return fnames, contents, limpos, limpos_sem_export, exports_by_file


def _indexar_exportadores(exports_by_file):
    exporters = {}
    for fname, ex in exports_by_file.items():
        for s in ex:
            exporters.setdefault(s, set()).add(fname)
    return exporters


def _imports_dos_ficheiros(fnames, contents):
    imports_by_file = {}
    namespace_by_file = {}
    for fname in fnames:
        c = contents[fname]
        imp = {}
        ns = {}
        for m in re.finditer(r'import\s*\{([^}]*)\}\s*from\s*[\'"]([^\'"]+)[\'"]', c):
            module = m.group(2)
            for item in m.group(1).split(','):
                item = item.strip()
                if not item:
                    continue
                if ' as ' in item:
                    _, local = item.split(' as ')
                    local = local.strip()
                else:
                    local = item.strip()
                imp[local] = module
        for m in re.finditer(r'import\s+([A-Za-z_$][\w$]*)\s+from\s*[\'"][^\'"]+[\'"]', c):
            imp[m.group(1)] = 'default'
        for m in re.finditer(r'import\s*\*\s*as\s+([A-Za-z_$][\w$]*)\s+from\s*[\'"]([^\'"]+)[\'"]', c):
            imp[m.group(1)] = 'namespace'
            ns[m.group(1)] = m.group(2)
        imports_by_file[fname] = imp
        namespace_by_file[fname] = ns
    return imports_by_file, namespace_by_file


def _orfaos(imp, limpo, exporters, fname):
    orfaos = []
    for local, module in imp.items():
        if contar_simbolo(local, limpo) <= 1:
            outros = exporters.get(local, set()) - {fname}
            if outros:
                orfaos.append(f"    - {local} (import de '{module}') -> exportado em {', '.join(sorted(outros))} [ORFAO LOCAL: remover so deste import]")
            else:
                orfaos.append(f"    - {local} (import de '{module}') -> nao exportado em nenhum modulo [ORFAO LOCAL: remover deste import]")
    return orfaos


def _destructuring(c, limpo):
    dests = []
    ambiguos = []
    for m in re.finditer(r'\b(const|let|var)\s*\{([^}]*)\}\s*=\s*([A-Za-z_$][\w$]*)\s*;?', c):
        fonte = m.group(3)
        for item in m.group(2).split(','):
            item = item.strip()
            if not item:
                continue
            if ':' in item:
                chave, local = item.split(':', 1)
                chave = chave.strip()
                local = local.strip()
            else:
                chave = item
                local = item
            usos = contar_simbolo(local, limpo)
            n_decl = contar_declaracoes(local, limpo)
            if n_decl >= 2:
                onde = ", ".join(f"l.{linha} '{forma}'" for linha, forma in ocorrencias_declaracao(local, limpo))
                ambiguos.append(f"    - {local} (de {fonte}) -> declarado {n_decl}x: {onde} [AMBIGUO: sombra entre escopos; confirme o uso em cada local antes de remover]")
                continue
            if usos <= 1:
                prop_usos = contar_simbolo(fonte + '.' + chave, limpo)
                if prop_usos > 0:
                    dests.append(f"    - {local} (de {fonte}) -> variavel solta nao usada, mas {fonte}.{chave} usado {prop_usos}x [REDUNDANTE: remover so da desestruturacao]")
                else:
                    dests.append(f"    - {local} (de {fonte}) -> nao usado em lugar nenhum [ORFAO]")
    return dests, ambiguos


def _locais(limpo, exports_by_file, fname):
    locais = []
    for m in re.finditer(r'\b(const|let|var)\s+([A-Za-z_$][\w$]*)\s*=', limpo):
        nome = m.group(2)
        if nome in exports_by_file[fname]:
            continue
        if contar_declaracoes(nome, limpo) >= 2:
            continue
        if contar_simbolo(nome, limpo) <= 1:
            locais.append(f"    - {nome} ({m.group(1)}) -> declarado mas nunca usado [DEAD CODE LOCAL: candidato a apagar]")
    return locais


def _funcoes(limpo, exports_by_file, fname):
    funcs = []
    for m in re.finditer(r'\bfunction\s+([A-Za-z_$][\w$]*)\s*\(', limpo):
        nome = m.group(1)
        if nome in exports_by_file[fname]:
            continue
        if contar_declaracoes(nome, limpo) >= 2:
            continue
        if contar_simbolo(nome, limpo) <= 1:
            funcs.append(f"    - {nome}() -> declarado mas nunca chamado [DEAD CODE LOCAL: candidato a apagar]")
    return funcs


def _faltantes(limpo, exporters, imp, fname):
    faltantes = []
    chamadas = set(re.findall(r'(?<![A-Za-z0-9_$.])([A-Za-z_$][\w$]*)\s*\(', limpo))
    for simb in chamadas:
        outros = exporters.get(simb, set()) - {fname}
        if outros and simb not in imp:
            if contar_declaracoes(simb, limpo) >= 1:
                continue
            faltantes.append(f"    - {simb}() chamado aqui, exportado em {', '.join(sorted(outros))}, mas NAO importado [FALTANTE: risco de ReferenceError]")
    return faltantes


def _dead_code_global(fname, exports_by_file, sem_exp, limpos, namespace_by_file):
    deads = []
    for simb in sorted(exports_by_file[fname]):
        usado_fora = False
        for o, limpo_outro in limpos.items():
            if o == fname:
                continue
            if contar_simbolo(simb, limpo_outro) >= 1:
                usado_fora = True
                break
            for alias, mod in namespace_by_file.get(o, {}).items():
                if os.path.basename(mod) == fname and contar_membro(alias, simb, limpo_outro) >= 1:
                    usado_fora = True
                    break
            if usado_fora:
                break
        if usado_fora:
            continue
        if contar_simbolo(simb, sem_exp) <= 1:
            deads.append(f"    - {simb} (export em {fname}) -> nao importado em nenhum modulo nem usado internamente [DEAD CODE GLOBAL: candidato a apagar]")
    return deads


@register(
    "tool_auditar_imports_js",
    'Audita módulos JavaScript (imports, destructuring e declarações) e cruza os dados entre os módulos da pasta para classificar cada símbolo não usado como: ÓRFÃO LOCAL (usado em outro módulo, remover só do import daqui), DEAD CODE GLOBAL (não usado em lugar nenhum, candidato a apagar a definição) ou FALTANTE (usado mas não importado, risco de ReferenceError). NÃO edita nada, apenas reporta. Use para auditar uma pasta ou arquivo .js específico.',
    {
        'caminho_relativo': {"tipo": "STRING", "desc": 'Arquivo .js ou pasta contendo os módulos (ex: src/frontend/js/chat)', "obrig": True, "padrao": ""},
    },
    disponivel="edicao",
)
def tool_auditar_imports_js(caminho_relativo):
    emit_event("executing", function=f"Auditando imports/dead code: {caminho_relativo}")
    abs_path, erro = resolver_caminho(caminho_relativo)
    if erro:
        return erro

    if os.path.isdir(abs_path):
        files = arquivos_recursivos(abs_path, ".js")
        report_only = None
    else:
        files = arquivos_recursivos(os.path.dirname(abs_path), ".js")
        report_only = os.path.basename(abs_path)

    if not files:
        return f"Nenhum arquivo .js encontrado em '{caminho_relativo}'."

    fnames, contents, limpos, limpos_sem_export, exports_by_file = _indexar(files)
    exporters = _indexar_exportadores(exports_by_file)
    imports_by_file, namespace_by_file = _imports_dos_ficheiros(fnames, contents)

    if report_only:
        linhas = ["=== AUDITORIA DE IMPORTS E DEAD CODE (JS) ===", f"Cruzamento com {len(limpos)} arquivo(s) (a pasta alvo e a de cima). Relatorio do arquivo alvo: {report_only}\n"]
    else:
        linhas = ["=== AUDITORIA DE IMPORTS E DEAD CODE (JS) ===", f"Analisados {len(files)} arquivo(s); o morto so o e depois de cruzado com {len(limpos)}.\n"]
    total = 0

    for fname in fnames:
        if report_only and fname != report_only:
            continue
        limpo = limpos[fname]
        imp = imports_by_file[fname]
        dests, ambiguos = _destructuring(contents[fname], limpo)
        blocos = []
        for itens, cabecalho in (
            (_orfaos(imp, limpo, exporters, fname), "  [IMPORTS NAO USADOS]"),
            (dests, "  [DESTRUCTURING NAO USADOS]"),
            (ambiguos, "  [AMBIGUOS / SOMBRA (verificacao manual, NAO remover as cegas)]"),
            (_locais(limpo, exports_by_file, fname), "  [DECLARACOES LOCAIS NAO USADAS]"),
            (_funcoes(limpo, exports_by_file, fname), "  [FUNCOES LOCAIS NAO USADAS]"),
            (_faltantes(limpo, exporters, imp, fname), "  [FALTANTES (usado mas nao importado)]"),
            (_dead_code_global(fname, exports_by_file, limpos_sem_export[fname], limpos, namespace_by_file),
             "  [DEAD CODE GLOBAL (candidatos a apagar)]"),
        ):
            if itens:
                blocos.append(cabecalho)
                blocos.extend(itens)
                total += len(itens)
        if blocos:
            linhas.append(f"ARQUIVO: {fname}")
            linhas.extend(blocos)
            linhas.append("")

    if total == 0:
        linhas.append("Nenhum achado nos modulos varridos: sem ORFAO LOCAL, sem FALTANTE e sem DEAD CODE GLOBAL.")
        linhas.append("Isto NAO quer dizer que os ficheiros varridos nao tenham imports nem declaracoes - quer")
        linhas.append("dizer que nao ha nada a remover/mover. Um ficheiro pode muito bem ter imports e um bloco")
        linhas.append("'export { ... }' a meio do texto e nao gerar achado nenhum.")
    else:
        linhas.append(f"Total de itens sinalizados: {total}")
        linhas.append("IMPORTANTE: relatorio apenas informativo. Nada foi editado. Revise antes de remover/mover.")
    linhas.append("")
    linhas.append("NOTA: analise heuristica (regex, sem AST). Pode dar falso positivo/negativo em nomes")
    linhas.append("redeclarados em escopos diferentes (sombra), reexports dinamicos ou metodos de objeto.")
    linhas.append("Itens marcados [AMBIGUO] NAO devem ser removidos sem verificacao manual.")
    return "\n".join(linhas)
