import difflib

def gerar_diff(texto_antigo, texto_novo):
    diff = []
    linhas_antigas = texto_antigo.replace('\r\n', '\n').splitlines(keepends=True)
    linhas_novas = texto_novo.replace('\r\n', '\n').splitlines(keepends=True)
    matcher = difflib.SequenceMatcher(None, linhas_antigas, linhas_novas)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            diff.append({"type": "unmodified", "text": "".join(linhas_antigas[i1:i2])})
        elif tag == 'replace':
            diff.append({"type": "deleted", "text": "".join(linhas_antigas[i1:i2])})
            diff.append({"type": "added", "text": "".join(linhas_novas[j1:j2])})
        elif tag == 'delete':
            diff.append({"type": "deleted", "text": "".join(linhas_antigas[i1:i2])})
        elif tag == 'insert':
            diff.append({"type": "added", "text": "".join(linhas_novas[j1:j2])})
    return diff
