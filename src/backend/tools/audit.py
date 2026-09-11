import os
import subprocess
import re
import ast
import symtable
import builtins
from src.backend.tools.registry import register
from src.backend.services.file_service import caminho_contido, resolver_caminho, raiz_abs
from src.backend.config import APP_ROOT
from src.backend.state import emit_event
from src.backend.tools.process import matar_arvore

@register(
    name="tool_auditar_codigo",
    description="Executa um linter (ESLint para JS, Ruff para Python) para detectar variáveis não declaradas (no-undef), código morto (no-unused-vars) e outros erros estáticos.",
    parameters={
        "type": "OBJECT",
        "properties": {
            "caminho_relativo": {
                "type": "STRING",
                "description": "Arquivo ou pasta para auditar (ex: src/frontend/js/chat)"
            },
            "linguagem": {
                "type": "STRING",
                "description": "Linguagem (javascript, typescript, python)"
            }
        },
        "required": ["caminho_relativo", "linguagem"]
    }
)
def tool_auditar_codigo(caminho_relativo, linguagem="javascript"):
    emit_event("executing", function=f"Auditando código: {caminho_relativo}")
    abs_path, erro = resolver_caminho(caminho_relativo)
    if erro:
        return erro

    linguagem = linguagem.lower()
    if linguagem in ("javascript", "typescript"):
        # Usa npx eslint sem arquivo de configuração, aplicando regras básicas
        # Usa eslint@8 para manter compatibilidade com as flags de CLI (--env, --parser-options)
        cmd = f"npx --yes eslint@8 --no-eslintrc --env browser,node,es2024 --global io --parser-options sourceType:module --rule \"no-undef: error\" --rule \"no-unused-vars: warn\" \"{abs_path}\""
        try:
            proc = _run_com_timeout(cmd)
            saida = (proc.stdout or "").strip() + "\n" + (proc.stderr or "").strip()
            if proc.returncode == 0 and not saida.strip():
                return "Auditoria concluída: Nenhum erro encontrado."
            return f"Resultado da Auditoria (ESLint):\n{saida}"
        except Exception as e:
            return f"Erro ao executar ESLint: {e}"

    elif linguagem == "python":
        # Usa o ruff (linter Python moderno); se nao estiver instalado, reporta erro claro
        try:
            proc = _run_com_timeout(["ruff", "check", abs_path])
            if proc.returncode == 0 and not proc.stdout.strip():
                return "Auditoria concluída: Nenhum erro encontrado."
            return f"Resultado da Auditoria (Ruff):\n{proc.stdout.strip()}\n{proc.stderr.strip()}"
        except FileNotFoundError:
            return "ERRO: 'ruff' não encontrado no PATH. Instale-o ou use outra ferramenta."
        except Exception as e:
            return f"Erro ao executar Ruff: {e}"
    
    return f"Linguagem '{linguagem}' não suportada para auditoria automática."

def _run_com_timeout(cmd, timeout=60):
    """Executa um comando externo com timeout que realmente funciona no Windows.

    subprocess.run(..., shell=True, timeout=...) mata apenas o shell; o processo
    neto (ex: node via npx) herda os pipes de stdout/stderr e o communicate()
    nunca retorna, ignorando o timeout. Aqui usamos Popen + communicate(timeout)
    e, ao estourar, encerramos a arvore inteira com matar_arvore antes de relancar
    subprocess.TimeoutExpired para o chamador tratar.
    """
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        shell=isinstance(cmd, str),
    )
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        matar_arvore(proc)
        try:
            proc.communicate(timeout=5)
        except Exception:
            pass
        raise
    return subprocess.CompletedProcess(proc.args, proc.returncode, out, err)

@register(
    name="tool_analisar_similaridade",
    description="Executa o jscpd (Copy/Paste Detector) para encontrar blocos de código duplicados ou muito similares.",
    parameters={
        "type": "OBJECT",
        "properties": {
            "caminho_relativo": {
                "type": "STRING",
                "description": "Pasta para analisar (ex: src/frontend/js/chat)"
            },
            "min_linhas": {
                "type": "INTEGER",
                "description": "Número mínimo de linhas para considerar clone (padrão: 5)"
            }
        },
        "required": ["caminho_relativo"]
    }
)
def tool_analisar_similaridade(caminho_relativo, min_linhas=5):
    emit_event("executing", function=f"Auditando similaridade: {caminho_relativo}")
    abs_path, erro = resolver_caminho(caminho_relativo)
    if erro:
        return erro

    cmd = f"npx --yes jscpd \"{abs_path}\" --min-lines {min_linhas} --reporters console"
    try:
        proc = _run_com_timeout(cmd, timeout=120)
        saida = (proc.stdout or "").strip() + "\n" + (proc.stderr or "").strip()
        return f"Resultado da Análise de Similaridade (jscpd):\n{saida}"
    except subprocess.TimeoutExpired:
        return "ERRO: a analise de similaridade (jscpd) excedeu 120s e foi interrompida. Tente uma pasta menor ou verifique a conexao (primeira execucao baixa o pacote)."
    except Exception as e:
        return f"Erro ao executar jscpd: {e}"


@register(
    name="tool_corrigir_imports_js",
    description="Varre os módulos JS de uma pasta, identifica dependências cruzadas (exports usados em outros arquivos) e injeta os imports corretos no topo de cada arquivo.",
    parameters={
        "type": "OBJECT",
        "properties": {
            "pasta_js": {
                "type": "STRING",
                "description": "Pasta contendo os módulos (ex: src/frontend/js/chat)"
            }
        },
        "required": ["pasta_js"]
    }
)
def tool_corrigir_imports_js(pasta_js):
    emit_event("executing", function=f"Auditando/corrigindo imports JS: {pasta_js}")
    abs_dir, erro = resolver_caminho(pasta_js)
    if erro:
        return erro
        
    import re
    
    files = [f for f in os.listdir(abs_dir) if f.endswith(".js")]
    
    # 1. Extrair todos os exports de cada arquivo
    exports_by_file = {}
    for f in files:
        path = os.path.join(abs_dir, f)
        with open(path, "r", encoding="utf-8") as file:
            content = file.read()
        
        exports = set()
        exports.update(re.findall(r'export\s+function\s+([a-zA-Z0-9_]+)', content))
        exports.update(re.findall(r'export\s+async\s+function\s+([a-zA-Z0-9_]+)', content))
        exports.update(re.findall(r'export\s+const\s+([a-zA-Z0-9_]+)', content))
        blocks = re.findall(r'export\s*\{([^}]+)\}', content)
        for block in blocks:
            for item in block.split(','):
                item = item.strip()
                if item:
                    exports.add(item)
        
        exports_by_file[f] = exports

    resultados = []
    # 2. Para cada arquivo, encontrar quais funções de outros arquivos ele usa
    for f in files:
        if f in ["dom.js", "state.js"]:
            continue
            
        path = os.path.join(abs_dir, f)
        with open(path, "r", encoding="utf-8") as file:
            content = file.read()
            
        words = set(re.findall(r'\b[a-zA-Z0-9_]+\b', content))
        
        imports_to_add = {}
        for other_f, other_exports in exports_by_file.items():
            if other_f == f or other_f in ["dom.js", "state.js"]:
                continue
            
            used_exports = words.intersection(other_exports)
            if used_exports:
                imports_to_add[other_f] = sorted(list(used_exports))
                
        if not imports_to_add:
            continue
            
        import_lines = []
        for other_f, used in imports_to_add.items():
            import_lines.append(f"import {{ {', '.join(used)} }} from './{other_f}';")
            
        lines = content.splitlines()
        
        new_lines = []
        for line in lines:
            if line.startswith("import {") and "} from './" in line and not "dom.js" in line and not "state.js" in line:
                continue
            if line.startswith("import ") and "from './" in line and not "dom.js" in line and not "state.js" in line and "{" not in line:
                continue
            new_lines.append(line)
            
        insert_idx = 0
        for i, line in enumerate(new_lines):
            if line.startswith("import "):
                insert_idx = i + 1
                
        new_lines = new_lines[:insert_idx] + import_lines + new_lines[insert_idx:]
        
        with open(path, "w", encoding="utf-8") as file:
            file.write("\n".join(new_lines))
            
        resultados.append(f"{f}: Injetados imports de {list(imports_to_add.keys())}")

    if not resultados:
        return "Nenhum import precisou ser corrigido."
    return "Imports corrigidos:\n" + "\n".join(resultados)


@register(
    name="tool_auditar_imports_js",
    description="Audita modulos JavaScript (imports, destructuring e declaracoes) e cruza os dados entre os modulos da pasta para classificar cada simbolo nao usado como: ORFAO LOCAL (usado em outro modulo, remover so do import daqui), DEAD CODE GLOBAL (nao usado em lugar nenhum, candidato a apagar a definicao) ou FALTANTE (usado mas nao importado, risco de ReferenceError). NAO edita nada, apenas reporta.",
    parameters={
        "type": "OBJECT",
        "properties": {
            "caminho_relativo": {
                "type": "STRING",
                "description": "Arquivo .js ou pasta contendo os modulos (ex: src/frontend/js/chat)"
            }
        },
        "required": ["caminho_relativo"]
    }
)
def tool_auditar_imports_js(caminho_relativo):
    emit_event("executing", function=f"Auditando imports/dead code: {caminho_relativo}")
    abs_path, erro = resolver_caminho(caminho_relativo)
    if erro:
        return erro

    if os.path.isdir(abs_path):
        files = sorted([os.path.join(abs_path, f) for f in os.listdir(abs_path) if f.endswith(".js")])
        report_only = None
    else:
        pasta = os.path.dirname(abs_path)
        files = sorted([os.path.join(pasta, f) for f in os.listdir(pasta) if f.endswith(".js")])
        report_only = os.path.basename(abs_path)

    if not files:
        return "Nenhum arquivo .js encontrado."

    def _limpar(texto):
        PALAVRAS_REGEX = {
            'return', 'case', 'throw', 'typeof', 'instanceof', 'new',
            'void', 'delete', 'yield', 'await', 'in', 'of', 'else', 'do',
        }
        out = []
        i = 0
        n = len(texto)
        prev = ''
        cur_word = ''
        last_word = ''
        while i < n:
            ch = texto[i]
            if ch == '/' and i + 1 < n and texto[i + 1] == '/':
                while i < n and texto[i] != '\n':
                    i += 1
                out.append(' ')
                if cur_word:
                    last_word = cur_word
                    cur_word = ''
                prev = ' '
                continue
            if ch == '/' and i + 1 < n and texto[i + 1] == '*':
                i += 2
                while i + 1 < n and not (texto[i] == '*' and texto[i + 1] == '/'):
                    i += 1
                i += 2
                out.append(' ')
                if cur_word:
                    last_word = cur_word
                    cur_word = ''
                prev = ' '
                continue
            if ch == '`':
                i += 1
                while i < n:
                    if texto[i] == '`':
                        i += 1
                        break
                    if texto[i] == '\\':
                        i += 2
                        continue
                    if texto[i] == '$' and i + 1 < n and texto[i + 1] == '{':
                        j = i + 2
                        depth = 1
                        while j < n and depth > 0:
                            c = texto[j]
                            if c == '\\':
                                j += 2
                                continue
                            if c in ('"', "'", '`'):
                                q = c
                                j += 1
                                while j < n and texto[j] != q:
                                    j += 2 if texto[j] == '\\' else 1
                                j += 1
                                continue
                            if c == '{':
                                depth += 1
                            elif c == '}':
                                depth -= 1
                            j += 1
                        out.append(' ' + _limpar(texto[i + 2:j - 1]) + ' ')
                        i = j
                        continue
                    i += 1
                out.append(' ')
                cur_word = ''
                last_word = ''
                prev = ' '
                continue
            if ch in ('"', "'"):
                quote = ch
                i += 1
                while i < n:
                    if texto[i] == '\\':
                        i += 2
                        continue
                    if texto[i] == quote:
                        i += 1
                        break
                    i += 1
                out.append(' ')
                cur_word = ''
                last_word = ''
                prev = ' '
                continue
            if ch == '/' and (prev == '' or prev in '([{,;:!?=+*%&|^~<>' or last_word in PALAVRAS_REGEX or cur_word in PALAVRAS_REGEX):
                i += 1
                in_class = False
                while i < n:
                    c = texto[i]
                    if c == '\\':
                        i += 2
                        continue
                    if c == '[':
                        in_class = True
                    elif c == ']':
                        in_class = False
                    elif c == '/' and not in_class:
                        i += 1
                        while i < n and texto[i].isalpha():
                            i += 1
                        break
                    elif c == '\n':
                        break
                    i += 1
                out.append(' ')
                cur_word = ''
                last_word = ''
                prev = ' '
                continue
            if ch == '.' and i + 2 < n and texto[i + 1] == '.' and texto[i + 2] == '.':
                out.append(' ')
                i += 3
                cur_word = ''
                last_word = ''
                prev = ' '
                continue
            out.append(ch)
            if ch.isalnum() or ch in '_$':
                cur_word += ch
                prev = ch
            elif not ch.isspace():
                if cur_word:
                    last_word = cur_word
                    cur_word = ''
                prev = ch
            else:
                if cur_word:
                    last_word = cur_word
                    cur_word = ''
            i += 1
        return ''.join(out)

    def _padrao(nome):
        return r'(?<![A-Za-z0-9_$.])' + re.escape(nome) + r'(?![A-Za-z0-9_$])'

    def _contar(nome, texto):
        return len(re.findall(_padrao(nome), texto))

    def _contar_membro(ns_alias, membro, texto):
        dot = r'(?<![A-Za-z0-9_$.])' + re.escape(ns_alias) + r'\.' + re.escape(membro) + r'(?![A-Za-z0-9_$])'
        brk = r'(?<![A-Za-z0-9_$.])' + re.escape(ns_alias) + r'\s*\[\s*[\'"]' + re.escape(membro) + r'[\'"]\s*\]'
        return len(re.findall(dot, texto)) + len(re.findall(brk, texto))

    def _declaracoes(nome, texto):
        n = re.escape(nome)
        padroes = [
            r'\b(?:const|let|var)\s+' + n + r'\b',
            r'\b(?:const|let|var)\s*\{[^}]*?\b' + n + r'\b',
            r'\bfunction\s+' + n + r'\b',
            r'\bclass\s+' + n + r'\b',
        ]
        return sum(len(re.findall(p, texto)) for p in padroes)

    def _sem_exports(texto):
        t = re.sub(r'export\s*\{[^}]*\}', ' ', texto)
        t = re.sub(r'export\s+(async\s+)?function\s+', 'function ', t)
        t = re.sub(r'export\s+(const|let|var)\s+', r'\1 ', t)
        return t

    fnames = [os.path.basename(p) for p in files]
    contents = {}
    limpos = {}
    limpos_sem_export = {}
    exports_by_file = {}
    for p, fname in zip(files, fnames):
        with open(p, "r", encoding="utf-8") as f:
            c = f.read()
        contents[fname] = c
        limpos[fname] = _limpar(c)
        limpos_sem_export[fname] = _sem_exports(limpos[fname])
        ex = set()
        ex.update(re.findall(r'export\s+async\s+function\s+([A-Za-z_$][\w$]*)', c))
        ex.update(re.findall(r'export\s+function\s+([A-Za-z_$][\w$]*)', c))
        ex.update(re.findall(r'export\s+const\s+([A-Za-z_$][\w$]*)', c))
        ex.update(re.findall(r'export\s+let\s+([A-Za-z_$][\w$]*)', c))
        ex.update(re.findall(r'export\s+var\s+([A-Za-z_$][\w$]*)', c))
        for bloco in re.findall(r'export\s*\{([^}]+)\}', c):
            for item in bloco.split(','):
                item = item.strip().split(' as ')[0].strip()
                if item:
                    ex.add(item)
        exports_by_file[fname] = ex

    exporters = {}
    for fname, ex in exports_by_file.items():
        for s in ex:
            exporters.setdefault(s, set()).add(fname)

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

    if report_only:
        linhas = ["=== AUDITORIA DE IMPORTS E DEAD CODE (JS) ===", f"Cruzamento com {len(files)} arquivo(s) da pasta. Relatorio do arquivo alvo: {report_only}\n"]
    else:
        linhas = ["=== AUDITORIA DE IMPORTS E DEAD CODE (JS) ===", f"Analisados {len(files)} arquivo(s).\n"]
    total = 0

    for fname in fnames:
        if report_only and fname != report_only:
            continue
        c = contents[fname]
        limpo = limpos[fname]
        sem_exp = limpos_sem_export[fname]
        imp = imports_by_file[fname]
        blocos = []

        orfaos = []
        ambiguos = []
        for local, module in imp.items():
            if _contar(local, limpo) <= 1:
                outros = exporters.get(local, set()) - {fname}
                if outros:
                    orfaos.append(f"    - {local} (import de '{module}') -> exportado em {', '.join(sorted(outros))} [ORFAO LOCAL: remover so deste import]")
                else:
                    orfaos.append(f"    - {local} (import de '{module}') -> nao exportado em nenhum modulo [ORFAO LOCAL: remover deste import]")
        if orfaos:
            blocos.append("  [IMPORTS NAO USADOS]")
            blocos.extend(orfaos)
            total += len(orfaos)

        dests = []
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
                usos = _contar(local, limpo)
                n_decl = _declaracoes(local, limpo)
                if n_decl >= 2:
                    ambiguos.append(f"    - {local} (de {fonte}) -> declarado {n_decl}x no arquivo (sombra entre escopos) [AMBIGUO: regex nao distingue escopo, verificar manualmente]")
                    continue
                if usos <= 1:
                    prop_usos = _contar(fonte + '.' + chave, limpo)
                    if prop_usos > 0:
                        dests.append(f"    - {local} (de {fonte}) -> variavel solta nao usada, mas {fonte}.{chave} usado {prop_usos}x [REDUNDANTE: remover so da desestruturacao]")
                    else:
                        dests.append(f"    - {local} (de {fonte}) -> nao usado em lugar nenhum [ORFAO]")
        if dests:
            blocos.append("  [DESTRUCTURING NAO USADOS]")
            blocos.extend(dests)
            total += len(dests)
        if ambiguos:
            blocos.append("  [AMBIGUOS / SOMBRA (verificacao manual, NAO remover as cegas)]")
            blocos.extend(ambiguos)
            total += len(ambiguos)

        locais = []
        for m in re.finditer(r'\b(const|let|var)\s+([A-Za-z_$][\w$]*)\s*=', limpo):
            nome = m.group(2)
            if nome in exports_by_file[fname]:
                continue
            if _declaracoes(nome, limpo) >= 2:
                continue
            if _contar(nome, limpo) <= 1:
                locais.append(f"    - {nome} ({m.group(1)}) -> declarado mas nunca usado [DEAD CODE LOCAL: candidato a apagar]")
        if locais:
            blocos.append("  [DECLARACOES LOCAIS NAO USADAS]")
            blocos.extend(locais)
            total += len(locais)

        funcs = []
        for m in re.finditer(r'\bfunction\s+([A-Za-z_$][\w$]*)\s*\(', limpo):
            nome = m.group(1)
            if nome in exports_by_file[fname]:
                continue
            if _declaracoes(nome, limpo) >= 2:
                continue
            if _contar(nome, limpo) <= 1:
                funcs.append(f"    - {nome}() -> declarado mas nunca chamado [DEAD CODE LOCAL: candidato a apagar]")
        if funcs:
            blocos.append("  [FUNCOES LOCAIS NAO USADAS]")
            blocos.extend(funcs)
            total += len(funcs)

        faltantes = []
        chamadas = set(re.findall(r'(?<![A-Za-z0-9_$.])([A-Za-z_$][\w$]*)\s*\(', limpo))
        for simb in chamadas:
            outros = exporters.get(simb, set()) - {fname}
            if outros and simb not in imp:
                if _declaracoes(simb, limpo) >= 1:
                    continue
                faltantes.append(f"    - {simb}() chamado aqui, exportado em {', '.join(sorted(outros))}, mas NAO importado [FALTANTE: risco de ReferenceError]")
        if faltantes:
            blocos.append("  [FALTANTES (usado mas nao importado)]")
            blocos.extend(faltantes)
            total += len(faltantes)

        deads = []
        for simb in sorted(exports_by_file[fname]):
            usado_fora = False
            for o in fnames:
                if o == fname:
                    continue
                if _contar(simb, limpos[o]) >= 1:
                    usado_fora = True
                    break
                for alias, mod in namespace_by_file.get(o, {}).items():
                    if os.path.basename(mod) == fname and _contar_membro(alias, simb, limpos[o]) >= 1:
                        usado_fora = True
                        break
                if usado_fora:
                    break
            if usado_fora:
                continue
            if _contar(simb, sem_exp) <= 1:
                deads.append(f"    - {simb} (export em {fname}) -> nao importado em nenhum modulo nem usado internamente [DEAD CODE GLOBAL: candidato a apagar]")
        if deads:
            blocos.append("  [DEAD CODE GLOBAL (candidatos a apagar)]")
            blocos.extend(deads)
            total += len(deads)

        if blocos:
            linhas.append(f"ARQUIVO: {fname}")
            linhas.extend(blocos)
            linhas.append("")

    if total == 0:
        linhas.append("Nenhum import, destructuring, declaracao local, funcao ou dead code orfao encontrado.")
    else:
        linhas.append(f"Total de itens sinalizados: {total}")
        linhas.append("IMPORTANTE: relatorio apenas informativo. Nada foi editado. Revise antes de remover/mover.")
    linhas.append("")
    linhas.append("NOTA: analise heuristica (regex, sem AST). Pode dar falso positivo/negativo em nomes")
    linhas.append("redeclarados em escopos diferentes (sombra), reexports dinamicos ou metodos de objeto.")
    linhas.append("Itens marcados [AMBIGUO] NAO devem ser removidos sem verificacao manual.")
    return "\n".join(linhas)

PY_EXTRA_GLOBALS = {
    '__name__', '__file__', '__doc__', '__package__', '__spec__', '__loader__',
    '__builtins__', '__debug__', '__dict__', '__class__', '__all__',
    '__annotations__', '__qualname__', '__module__'
}

def _py_arquivos(pasta):
    """Lista recursivamente os .py de uma pasta, ignorando venv/caches/build."""
    if not os.path.isdir(pasta):
        return [pasta] if pasta.endswith(".py") else []
    ignorar = {'.venv', 'venv', '__pycache__', '.git', 'node_modules', 'build', 'dist', '.vs', 'site-packages'}
    saida = []
    for dirpath, dirnames, filenames in os.walk(pasta):
        dirnames[:] = [d for d in dirnames if d not in ignorar and not d.startswith('.')]
        saida.extend(os.path.join(dirpath, f) for f in filenames if f.endswith(".py"))
    return sorted(saida)

def _py_ler(caminho):
    """Le e analisa um .py. Devolve (arvore, symtable_mod, erro)."""
    try:
        with open(caminho, "r", encoding="utf-8") as fh:
            src = fh.read()
    except Exception as e:
        return None, None, f"erro de leitura: {e}"
    try:
        arvore = ast.parse(src, caminho)
    except SyntaxError as e:
        return None, None, f"erro de sintaxe na linha {e.lineno}: {e.msg}"
    try:
        return arvore, symtable.symtable(src, caminho, "exec"), None
    except Exception as e:
        return None, None, f"erro ao montar symtable: {e}"

def _py_escopos(st):
    """Achata a arvore de escopos do symtable (modulo, funcoes, classes, comprehensions)."""
    saida = [st]
    for filho in st.get_children():
        saida.extend(_py_escopos(filho))
    return saida

def _py_nomes_carregados(arvore):
    """Nomes lidos (ctx Load) do arquivo. Ignora atribuicoes, que nao sao usos."""
    return {no.id for no in ast.walk(arvore) if isinstance(no, ast.Name) and isinstance(no.ctx, ast.Load)}

def _py_imports(arvore):
    """Nomes introduzidos por import/from-import (descontando __future__ e import *)."""
    nomes = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            for al in no.names:
                nomes.add((al.asname or al.name).split(".")[0])
        elif isinstance(no, ast.ImportFrom) and no.module != "__future__":
            for al in no.names:
                if al.name != "*":
                    nomes.add(al.asname or al.name)
    return nomes

def _py_tem_star_import(arvore):
    for no in ast.walk(arvore):
        if isinstance(no, ast.ImportFrom) and any(al.name == "*" for al in no.names):
            return True
    return False

def _py_exports(arvore):
    """Nomes declarados em __all__ = [...] (reexports explicitos)."""
    nomes = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Assign) and any(isinstance(a, ast.Name) and a.id == "__all__" for a in no.targets):
            if isinstance(no.value, (ast.List, ast.Tuple)):
                for el in no.value.elts:
                    if isinstance(el, ast.Constant) and isinstance(el.value, str):
                        nomes.add(el.value)
    return nomes

def _py_definicoes_topo(arvore):
    """Funcoes/classes de topo sem decorador (decoradas sao usadas por registro implicito)."""
    return [no.name for no in arvore.body
            if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and not no.decorator_list]

def _py_nome_modulo(caminho, raiz):
    """Converte caminho absoluto no nome dotted do modulo (relativo a raiz)."""
    try:
        rel = os.path.relpath(caminho, raiz).replace(os.sep, "/")
    except Exception:
        return ""
    if rel.endswith(".py"):
        rel = rel[:-3]
    if rel.endswith("/__init__"):
        rel = rel[:-9]
    return rel.replace("/", ".")

def _py_raiz_varredura(abs_path):
    """Escolhe a raiz para a varredura cross-file: o ancestral mais proximo que seja raiz de projeto."""
    alvo = os.path.abspath(abs_path)
    candidatos = []
    selecionada = raiz_abs()
    if selecionada:
        candidatos.append(os.path.abspath(selecionada))
    candidatos.append(APP_ROOT)
    for cand in candidatos:
        if caminho_contido(alvo, cand):
            return cand
    return os.path.dirname(alvo) if os.path.isfile(alvo) else alvo

@register(
    name="tool_auditar_imports_py",
    description="Audita modulos Python (AST + symtable, com escopos reais) e classifica: FALTANTE (nome usado como global mas nao importado/definido no modulo -> risco de NameError), IMPORT NAO USADO (candidato a remover, ja descontando reexports e __all__) e DEAD CODE GLOBAL (funcao/classe de topo nunca referenciada no projeto). NAO edita nada, apenas reporta.",
    parameters={
        "type": "OBJECT",
        "properties": {
            "caminho_relativo": {
                "type": "STRING",
                "description": "Arquivo .py ou pasta contendo os modulos (ex: src/backend/routes)"
            }
        },
        "required": ["caminho_relativo"]
    }
)
def tool_auditar_imports_py(caminho_relativo):
    emit_event("executing", function=f"Auditando imports/dead code (Python): {caminho_relativo}")
    abs_path, erro = resolver_caminho(caminho_relativo)
    if erro:
        return erro

    if os.path.isdir(abs_path):
        arquivos = _py_arquivos(abs_path)
        report_only = None
    else:
        arquivos = [abs_path]
        report_only = os.path.basename(abs_path)

    if not arquivos:
        return "Nenhum arquivo .py encontrado."

    raiz = _py_raiz_varredura(abs_path)
    cache = {}
    for caminho in _py_arquivos(raiz):
        arvore, st, _err = _py_ler(caminho)
        cache[caminho] = (arvore, st)

    usados_no_projeto = set()
    importados_entre_modulos = set()
    for _caminho, (arvore, _st) in cache.items():
        if arvore is None:
            continue
        usados_no_projeto |= _py_nomes_carregados(arvore)
        for no in ast.walk(arvore):
            if isinstance(no, ast.ImportFrom) and no.module:
                for al in no.names:
                    importados_entre_modulos.add((no.module, al.asname or al.name))

    builtins_set = set(dir(builtins)) | PY_EXTRA_GLOBALS
    linhas = ["=== AUDITORIA DE IMPORTS E DEAD CODE (PYTHON) ===",
              f"Escopo da varredura: {raiz}",
              f"Analisados {len(arquivos)} arquivo(s).", ""]
    total = 0

    for caminho in arquivos:
        fname = os.path.basename(caminho)
        if report_only and fname != report_only:
            continue

        arvore, st = cache.get(caminho, (None, None))
        if arvore is None or st is None:
            _a, _s, err = _py_ler(caminho)
            linhas.append(f"ARQUIVO: {fname}")
            linhas.append(f"  [NAO ANALISADO] {err}")
            linhas.append("")
            total += 1
            continue

        modulo_names = set(st.get_identifiers())
        carregados_aqui = _py_nomes_carregados(arvore)
        exports = _py_exports(arvore)
        dotted = _py_nome_modulo(caminho, raiz)

        faltantes = set()
        if not _py_tem_star_import(arvore):
            for escopo in _py_escopos(st):
                for simb in escopo.get_symbols():
                    nome = simb.get_name()
                    if not simb.is_global():
                        continue
                    if nome in modulo_names or nome in builtins_set:
                        continue
                    faltantes.add(nome)

        nao_usados = set()
        for nome in _py_imports(arvore):
            if nome in carregados_aqui or nome in exports:
                continue
            if (dotted, nome) in importados_entre_modulos:
                continue
            nao_usados.add(nome)

        deads = set()
        for nome in _py_definicoes_topo(arvore):
            if nome in usados_no_projeto or nome in exports:
                continue
            deads.add(nome)

        blocos = []
        if faltantes:
            blocos.append("  [FALTANTE (usado mas nao importado -> risco de NameError)]")
            blocos.extend(f"    - {n} -> usado como global, mas nao importado/definido neste modulo" for n in sorted(faltantes))
        if nao_usados:
            blocos.append("  [IMPORT NAO USADO (confirmar antes de remover)]")
            blocos.extend(f"    - {n} -> importado e nunca referenciado no arquivo" for n in sorted(nao_usados))
        if deads:
            blocos.append("  [DEAD CODE GLOBAL (candidatos a apagar)]")
            blocos.extend(f"    - {n}() -> definido no topo e nunca referenciado no projeto" for n in sorted(deads))

        if blocos:
            linhas.append(f"ARQUIVO: {fname}")
            linhas.extend(blocos)
            linhas.append("")
            total += len(faltantes) + len(nao_usados) + len(deads)

    if total == 0:
        linhas.append("Nenhum import faltante, import nao usado ou dead code de topo encontrado.")
    else:
        linhas.append(f"Total de itens sinalizados: {total}")
        linhas.append("IMPORTANTE: relatorio apenas informativo. Nada foi editado. Revise antes de remover/mover.")
    linhas.append("")
    linhas.append("NOTA: FALTANTE e o achado mais grave (NameError real em runtime) e tem baixo falso")
    linhas.append("positivo, pois usa AST + symtable (escopos reais). IMPORT NAO USADO ja desconta reexports,")
    linhas.append("__all__ e imports relativos, mas imports feitos por efeito colateral podem aparecer como")
    linhas.append("falso positivo: confirme antes de remover. DEAD CODE ignora funcoes decoradas (usadas via")
    linhas.append("registro/decorador) e nomes citados em strings de anotacao podem escapar da deteccao.")
    return "\n".join(linhas)

JS_BUILTINS = {
    'window', 'document', 'console', 'setTimeout', 'setInterval', 'clearTimeout', 'clearInterval',
    'Math', 'Object', 'Array', 'String', 'Number', 'Boolean', 'Promise', 'Error', 'Event', 'Map', 'Set',
    'JSON', 'localStorage', 'sessionStorage', 'fetch', 'navigator', 'location', 'history', 'require',
    'module', 'exports', 'process', 'global', 'undefined', 'NaN', 'Infinity', 'monaco', 'electron',
    'socket', 'io', 'alert', 'prompt', 'confirm', 'parseFloat', 'parseInt', 'decodeURI', 'decodeURIComponent',
    'encodeURI', 'encodeURIComponent', 'URL', 'URLSearchParams', 'Blob', 'File', 'FormData', 'Headers',
    'Request', 'Response', 'WebSocket', 'Worker', 'SharedWorker', 'Performance', 'PerformanceObserver',
    'MutationObserver', 'IntersectionObserver', 'ResizeObserver', 'CustomEvent', 'dispatchEvent',
    'addEventListener', 'removeEventListener', 'getComputedStyle', 'requestAnimationFrame', 'cancelAnimationFrame',
    'HTMLElement', 'Element', 'Node', 'EventTarget', 'DOMParser', 'XMLSerializer', 'TextDecoder', 'TextEncoder',
    'btoa', 'atob', 'crypto', 'SubtleCrypto', 'CryptoKey', 'Uint8Array', 'Uint16Array', 'Uint32Array',
    'Int8Array', 'Int16Array', 'Int32Array', 'Float32Array', 'Float64Array', 'DataView', 'ArrayBuffer',
    'Reflect', 'Proxy', 'Symbol', 'BigInt', 'Atomics', 'WebAssembly', 'Intl', 'arguments', 'eval',
    'isFinite', 'isNaN', 'escape', 'unescape', 'Image', 'Audio', 'Option', 'requireNode'
}

def _parse_js_project(abs_dir):
    """Le todos os .js de uma pasta e devolve (dados, erro).

    `dados` traz: files (nomes), declarations_by_file ({arquivo: {nome: no_ast}}) e
    uses_by_file ({arquivo: set}) com as referencias externas (fora builtins/declaracoes).
    """
    try:
        import tree_sitter_javascript as tsjs
        from tree_sitter import Language, Parser
    except ImportError:
        return None, "ERRO: tree_sitter ou tree_sitter_javascript não instalados."

    language = Language(tsjs.language())
    parser = Parser(language)

    files = [f for f in os.listdir(abs_dir) if f.endswith(".js")]
    declarations_by_file = {}
    uses_by_file = {}
    for f in files:
        path = os.path.join(abs_dir, f)
        with open(path, "r", encoding="utf-8") as file:
            content = file.read()
        source_bytes = bytes(content, "utf8")
        tree = parser.parse(source_bytes)
        root_node = tree.root_node

        declarations = {}
        for child in root_node.children:
            if child.type == 'function_declaration':
                name_node = child.child_by_field_name('name')
                if name_node:
                    name = source_bytes[name_node.start_byte:name_node.end_byte].decode('utf8')
                    declarations[name] = child
            elif child.type in ('variable_declaration', 'lexical_declaration'):
                for decl in child.children:
                    if decl.type == 'variable_declarator':
                        name_node = decl.child_by_field_name('name')
                        if name_node:
                            name = source_bytes[name_node.start_byte:name_node.end_byte].decode('utf8')
                            declarations[name] = child
            elif child.type == 'class_declaration':
                name_node = child.child_by_field_name('name')
                if name_node:
                    name = source_bytes[name_node.start_byte:name_node.end_byte].decode('utf8')
                    declarations[name] = child
        declarations_by_file[f] = declarations

        uses = set()
        def traverse(n):
            if n.type == 'identifier':
                parent = n.parent
                if parent and parent.type == 'member_expression' and parent.child_by_field_name('property') == n:
                    pass
                elif parent and parent.type == 'pair' and parent.child_by_field_name('key') == n:
                    pass
                elif parent and parent.type in ('function_declaration', 'variable_declarator', 'class_declaration') and parent.child_by_field_name('name') == n:
                    pass
                else:
                    uses.add(source_bytes[n.start_byte:n.end_byte].decode('utf8'))
            for child in n.children:
                traverse(child)
        traverse(root_node)
        uses_by_file[f] = uses - set(declarations.keys()) - JS_BUILTINS

    return {"files": files, "declarations_by_file": declarations_by_file, "uses_by_file": uses_by_file}, None

@register(
    name="tool_analisar_dependencias_globais_js",
    description="Analisa scripts JS clássicos em uma pasta usando AST (tree-sitter) para descobrir quais variáveis/funções globais cada arquivo declara e quais ele consome de outros arquivos. Essencial para planejar migração para ESM.",
    parameters={
        "type": "OBJECT",
        "properties": {
            "pasta": {
                "type": "STRING",
                "description": "Pasta contendo os scripts (ex: src/frontend/js/editor)"
            }
        },
        "required": ["pasta"]
    }
)
def tool_analisar_dependencias_globais_js(pasta):
    emit_event("executing", function=f"Analisando dependências globais: {pasta}")
    abs_dir, erro = resolver_caminho(pasta)
    if erro:
        return erro
        
    dados, erro = _parse_js_project(abs_dir)
    if erro:
        return erro
    files = dados["files"]
    declarations_by_file = dados["declarations_by_file"]
    uses_by_file = dados["uses_by_file"]
        
    report = []
    report.append("=== ANÁLISE DE DEPENDÊNCIAS GLOBAIS (AST) ===")
    
    for f in files:
        report.append(f"\nARQUIVO: {f}")
        decls = declarations_by_file[f]
        report.append(f"  [DECLARAÇÕES GLOBAIS (Potenciais Exports)]")
        if decls:
            for d in sorted(decls):
                report.append(f"    - {d}")
        else:
            report.append("    (nenhuma)")
            
        uses = uses_by_file[f]
        report.append(f"  [USOS EXTERNOS (Potenciais Imports)]")
        found_imports = False
        for u in sorted(uses):
            providers = [other_f for other_f, other_decls in declarations_by_file.items() if other_f != f and u in other_decls]
            if providers:
                report.append(f"    - {u} (fornecido por: {', '.join(providers)})")
                found_imports = True
            else:
                report.append(f"    - {u} (NÃO ENCONTRADO NOS OUTROS ARQUIVOS - pode ser builtin ou lib externa)")
                found_imports = True
                
        if not found_imports:
            report.append("    (nenhum)")
            
    return "\n".join(report)

@register(
    name="tool_migrar_para_esm",
    description="Migra scripts JS clássicos para ES Modules (ESM) injetando 'export' nas declarações globais e 'import' para as dependências externas, baseado na análise AST.",
    parameters={
        "type": "OBJECT",
        "properties": {
            "pasta": {
                "type": "STRING",
                "description": "Pasta contendo os scripts (ex: src/frontend/js/editor)"
            }
        },
        "required": ["pasta"]
    }
)
def tool_migrar_para_esm(pasta):
    emit_event("executing", function=f"Migrando para ESM: {pasta}")
    abs_dir, erro = resolver_caminho(pasta)
    if erro:
        return erro
        
    dados, erro = _parse_js_project(abs_dir)
    if erro:
        return erro
    files = dados["files"]
    declarations_by_file = dados["declarations_by_file"]
    uses_by_file = dados["uses_by_file"]
        
    resultados = []
    for f in files:
        path = os.path.join(abs_dir, f)
        with open(path, "r", encoding="utf-8") as file:
            content = file.read()
            
        imports_to_add = {}
        for u in uses_by_file[f]:
            for other_f, other_decls in declarations_by_file.items():
                if other_f != f and u in other_decls:
                    imports_to_add.setdefault(other_f, []).append(u)
                    break
                    
        decls = declarations_by_file[f]
        nodes_to_export = set(decls.values())
        sorted_nodes = sorted(nodes_to_export, key=lambda n: n.start_byte, reverse=True)
        
        source_bytes = bytes(content, "utf8")
        
        for node in sorted_nodes:
            if node.parent and node.parent.type == 'export_statement':
                continue
            start = node.start_byte
            source_bytes = source_bytes[:start] + b"export " + source_bytes[start:]
            
        new_content = source_bytes.decode('utf8')
        
        import_lines = []
        for other_f, used in imports_to_add.items():
            import_lines.append(f"import {{ {', '.join(sorted(used))} }} from './{other_f}';")
            
        if import_lines:
            new_content = "\n".join(import_lines) + "\n\n" + new_content
            
        with open(path, "w", encoding="utf-8") as file:
            file.write(new_content)
            
        resultados.append(f"{f}: Injetados {len(import_lines)} imports e {len(nodes_to_export)} exports.")
        
    return "Migração para ESM concluída:\n" + "\n".join(resultados)
