"""Analise AST (tree-sitter) de scripts JS classicos e migracao para ESM."""

import os
import re
from src.backend.tools.registry import register
from src.backend.services.file_service import resolver_caminho
from src.backend.state import emit_event
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
    esm_by_file = {}
    for f in files:
        path = os.path.join(abs_dir, f)
        with open(path, "r", encoding="utf-8") as file:
            content = file.read()
        esm_by_file[f] = bool(re.search(r'^\s*(?:import|export)\b', content, re.M))
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

    return {"files": files, "declarations_by_file": declarations_by_file, "uses_by_file": uses_by_file, "esm_by_file": esm_by_file}, None


@register(
    "tool_analisar_dependencias_globais_js",
    'Analisa scripts JS clássicos em uma pasta usando AST (tree-sitter) para descobrir quais variáveis/funções globais cada arquivo declara e quais ele consome de outros arquivos. Essencial para planejar migração para ESM.',
    {
        'pasta': {"tipo": "STRING", "desc": 'Pasta contendo os scripts (ex: src/frontend/js/editor)', "obrig": True, "padrao": ""},
    },
    disponivel="edicao",
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
    esm_by_file = dados.get("esm_by_file", {})

    report = []
    report.append("=== ANÁLISE DE DEPENDÊNCIAS GLOBAIS (AST) ===")
    arquivos_esm = sorted(f for f, is_esm in esm_by_file.items() if is_esm)
    if arquivos_esm:
        report.append(
            "AVISO: esta pasta ja contem modulos ESM (com import/export): "
            + ", ".join(arquivos_esm)
            + ". Esta analise destina-se a scripts CLASSICOS (globais via <script>). Em arquivos ESM os "
            "nomes de topo locais aparecem como 'usos externos' (ruido) - para ESM use tool_auditar_imports_js."
        )
    
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
    "tool_migrar_para_esm",
    "Migra scripts JS clássicos para ES Modules (ESM) injetando 'export' nas declarações globais e 'import' para as dependências externas, baseado na análise AST.",
    {
        'pasta': {"tipo": "STRING", "desc": 'Pasta contendo os scripts (ex: src/frontend/js/editor)', "obrig": True, "padrao": ""},
    },
    disponivel="edicao",
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
