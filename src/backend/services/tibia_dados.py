import os
import re
from functools import lru_cache

BASE_PADRAO = 'docs/projetos/Tibia74'


def _normalizar(nome):
    nome = nome.lower()
    nome = re.sub(r'^(a|an|the)\s+', '', nome)
    return re.sub(r'[^a-z0-9]', '', nome)


@lru_cache(maxsize=4)
def objetos_do_srv(base=BASE_PADRAO):
    caminho = f'{base}/gerados/monstros/cipsoft/objects.srv'
    texto = open(caminho, encoding='latin-1').read()
    tabela = {}
    for bloco in re.finditer(r'TypeID\s*=\s*(\d+)(.*?)(?=\nTypeID|\Z)', texto, re.S):
        achado = re.search(r'Name\s*=\s*"([^"]*)"', bloco.group(2))
        if achado:
            tabela[int(bloco.group(1))] = achado.group(1)
    return tabela


@lru_cache(maxsize=4)
def items_740(base=BASE_PADRAO):
    caminho = f'{base}/Tools/Map Editor/data/740/items.xml'
    texto = open(caminho, encoding='latin-1').read()
    tabela = {}
    for achado in re.finditer(r'<item\s+id="(\d+)"[^>]*name="([^"]*)"', texto):
        tabela.setdefault(_normalizar(achado.group(2)), []).append(int(achado.group(1)))
    return tabela


def _ficheiro_do_mon(base, monstro):
    pasta = f'{base}/gerados/monstros/cipsoft'
    nome = _normalizar(monstro)
    candidatos = [f for f in os.listdir(pasta) if f.endswith('.mon')]
    for ficheiro in candidatos:
        if _normalizar(ficheiro[:-4]) == nome:
            return f'{pasta}/{ficheiro}'
    for ficheiro in candidatos:
        texto = open(f'{pasta}/{ficheiro}', encoding='latin-1').read(400)
        achado = re.search(r'Name\s*=\s*"([^"]*)"', texto)
        if achado and _normalizar(achado.group(1)) == nome:
            return f'{pasta}/{ficheiro}'
    return None


def inventario_do_mon(base, monstro):
    caminho = _ficheiro_do_mon(base, monstro)
    if not caminho:
        return None
    texto = open(caminho, encoding='latin-1').read()
    bloco = re.search(r'Inventory\s*=\s*\{(.*?)\}', texto, re.S)
    if not bloco:
        return []
    objetos = objetos_do_srv(base)
    itens = items_740(base)
    inventario = []
    for typeid, quantidade, chance in re.findall(r'\((\d+),\s*(\d+),\s*(\d+)\)', bloco.group(1)):
        nome = objetos.get(int(typeid), f'typeid {typeid}')
        inventario.append({
            'nome': nome,
            'quantidade': int(quantidade),
            'chance': int(chance) / 10,
            'ids_740': itens.get(_normalizar(nome), []),
        })
    return inventario


def _texto_do_xml(base, monstro):
    pasta = f'{base}/Server/data/monster'
    for ficheiro in os.listdir(pasta):
        if ficheiro.endswith('.xml') and _normalizar(ficheiro[:-4]) == _normalizar(monstro):
            return open(f'{pasta}/{ficheiro}', encoding='latin-1').read()
    return None


def _loot_do_xml(base, monstro):
    texto = _texto_do_xml(base, monstro)
    if texto is None:
        return None
    bloco = re.search(r'<loot>(.*?)</loot>', texto, re.S)
    if not bloco:
        return []
    entradas = []

    def ler(trecho, dentro):
        for item in re.finditer(r'<item\s+([^>]*?)(/>|>(.*?)</item>)', trecho, re.S):
            atributos = dict(re.findall(r'(\w+)="([^"]*)"', item.group(1)))
            if 'id' not in atributos:
                continue
            entradas.append({
                'id': int(atributos['id']),
                'countmax': int(atributos.get('countmax', 1)),
                'chance': int(atributos.get('chance', 0)) / 1000,
                'dentro': dentro,
            })
            if item.group(3):
                ler(item.group(3), True)

    ler(bloco.group(1), False)
    return entradas


def cruzar_monstro(base, monstro):
    inventario = inventario_do_mon(base, monstro)
    if inventario is None:
        return {'erro': f'nao achei o .mon de {monstro}'}
    entradas = _loot_do_xml(base, monstro)
    if entradas is None:
        return {'erro': f'nao achei o XML de {monstro}'}

    do_mon = {}
    inexistentes = []
    for produto in inventario:
        if not produto['ids_740']:
            inexistentes.append(produto['nome'])
            continue
        chave = _normalizar(produto['nome'])
        do_mon.setdefault(chave, {'nome': produto['nome'], 'chances': []})
        do_mon[chave]['chances'].append(produto['chance'])

    do_mon_ids = set()
    for produto in inventario:
        do_mon_ids.update(produto['ids_740'])
    so_no_xml = []
    for entrada in entradas:
        if entrada['id'] == 1987 or entrada['id'] in do_mon_ids:
            continue
        so_no_xml.append((entrada['id'], entrada['chance'], entrada['dentro']))

    chances = []
    for chave, dados in do_mon.items():
        ids = items_740(base).get(chave, [])
        no_xml = sorted(e['chance'] for e in entradas if e['id'] in ids)
        no_mon = sorted(dados['chances'])
        if not no_xml:
            continue
        if len(no_xml) != len(no_mon) or any(abs(a - b) > 0.05 for a, b in zip(no_xml, no_mon)):
            chances.append((dados['nome'], no_mon, no_xml))

    return {
        'monstro': monstro,
        'produtos_no_mon': len(inventario),
        'entradas_no_xml': len(entradas),
        'so_no_xml': so_no_xml,
        'inexistentes_no_740': inexistentes,
        'chances_diferentes': chances,
        'inventario': inventario,
        'xml': entradas,
    }
