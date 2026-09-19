"""Injetor de imports de modulos JavaScript."""

import os
import re

from src.backend.services.file_service import resolver_caminho
from src.backend.state import emit_event
from src.backend.tools.registry import register


@register(
    "tool_corrigir_imports_js",
    'Varre os módulos JS de uma pasta, identifica dependências cruzadas (exports usados em outros arquivos) e injeta os imports corretos no topo de cada arquivo automaticamente.',
    {
        'pasta_js': {"tipo": "STRING", "desc": 'Caminho da pasta contendo os arquivos JS (ex: src/frontend/js/chat)', "obrig": True, "padrao": ""},
    },
    disponivel="edicao",
)
def tool_corrigir_imports_js(pasta_js):
    emit_event("executing", function=f"Auditando/corrigindo imports JS: {pasta_js}")
    abs_dir, erro = resolver_caminho(pasta_js)
    if erro:
        return erro
        
    files = [f for f in os.listdir(abs_dir) if f.endswith(".js")]
    
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
