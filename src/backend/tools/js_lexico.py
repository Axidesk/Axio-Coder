"""Lexico de modulos JS: texto sem comentarios/strings e contagem de simbolos."""

import re


def limpar(texto):
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
            inicio_bloco = i
            while i + 1 < n and not (texto[i] == '*' and texto[i + 1] == '/'):
                i += 1
            i += 2
            out.append(' ')
            out.append('\n' * texto.count('\n', inicio_bloco, min(i, n)))
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
                    out.append(' ' + limpar(texto[i + 2:j - 1]) + ' ')
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


def _padrao_simbolo(nome):
    return r'(?<![A-Za-z0-9_$.])' + re.escape(nome) + r'(?![A-Za-z0-9_$])'


def contar_simbolo(nome, texto):
    return len(re.findall(_padrao_simbolo(nome), texto))


def contar_membro(ns_alias, membro, texto):
    dot = r'(?<![A-Za-z0-9_$.])' + re.escape(ns_alias) + r'\.' + re.escape(membro) + r'(?![A-Za-z0-9_$])'
    brk = r'(?<![A-Za-z0-9_$.])' + re.escape(ns_alias) + r'\s*\[\s*[\'"]' + re.escape(membro) + r'[\'"]\s*\]'
    return len(re.findall(dot, texto)) + len(re.findall(brk, texto))


def ocorrencias_declaracao(nome, texto):
    n = re.escape(nome)
    padroes = [
        r'\b(?:const|let|var)\s+' + n + r'\b',
        r'\b(?:const|let|var)\s*\{[^}]*?\b' + n + r'\b',
        r'\bfunction\s+' + n + r'\b',
        r'\bclass\s+' + n + r'\b',
    ]
    achados = []
    for p in padroes:
        for m in re.finditer(p, texto):
            achados.append((texto.count('\n', 0, m.start()) + 1, " ".join(m.group(0).split())))
    achados.sort()
    return achados


def contar_declaracoes(nome, texto):
    return len(ocorrencias_declaracao(nome, texto))


def remover_exports(texto):
    t = re.sub(r'export\s*\{[^}]*\}', ' ', texto)
    t = re.sub(r'export\s+(async\s+)?function\s+', 'function ', t)
    t = re.sub(r'export\s+(const|let|var)\s+', r'\1 ', t)
    return t


def exports_do_texto(c):
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
    return ex
