import html
import os
import re
from functools import lru_cache

BASE_PADRAO = 'docs/projetos/Tibia74'

SANGUE_PARA_RACE = {'blood': 'blood', 'slime': 'venom', 'bones': 'undead', 'fire': 'fire'}

FLAGS_DO_MON = {
    'KickBoxes': ('flags', 'canpushitems', '1'),
    'KickCreatures': ('flags', 'canpushcreatures', '1'),
    'Unpushable': ('flags', 'pushable', '0'),
    'NoSummon': ('flags', 'summonable', '0'),
    'NoIllusion': ('flags', 'illusionable', '0'),
    'NoConvince': ('flags', 'convinceable', '0'),
    'NoBurning': ('immunities', 'fire', '1'),
    'NoPoison': ('immunities', 'poison', '1'),
    'NoEnergy': ('immunities', 'energy', '1'),
    'NoLifeDrain': ('immunities', 'lifedrain', '1'),
    'NoParalyze': ('immunities', 'paralyze', '1'),
    'NoHit': ('immunities', 'physical', '1'),
}

FLAGS_SEM_CAMPO = {'SeeInvisible'}


CORPO_DE = re.compile(r'^(dead|slain|remains)')


def _sem_artigo(nome):
    return re.sub(r'^(a|an|the)\s+', '', nome.lower().strip())


def _palavras(nome):
    return set(re.findall(r'[a-z0-9]+', _sem_artigo(nome)))


def _normalizar(nome):
    return re.sub(r'[^a-z0-9]', '', _sem_artigo(nome))


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


@lru_cache(maxsize=64)
def cabecalho_do_mon(base, monstro):
    """Le do .mon a identidade, as flags, as skills, as invocacoes e as falas."""
    caminho = _ficheiro_do_mon(base, monstro)
    if not caminho:
        return None
    texto = open(caminho, encoding='latin-1').read()

    def numero(campo):
        achado = re.search(r'^%s\s*=\s*(-?\d+)' % campo, texto, re.M)
        return int(achado.group(1)) if achado else None

    def palavra(campo):
        achado = re.search(r'^%s\s*=\s*(\w+)' % campo, texto, re.M)
        return achado.group(1) if achado else ''

    outfit = re.search(r'^Outfit\s*=\s*\((\d+),\s*([\d-]+)\)', texto, re.M)
    bloco_flags = re.search(r'^Flags\s*=\s*\{(.*?)\}', texto, re.S | re.M)
    estrategia = re.search(r'^Strategy\s*=\s*\(([^)]*)\)', texto, re.M)
    seguinte = r'(?=\n[A-Z]\w*\s*=|\Z)'
    bloco_skills = re.search(r'^Skills\s*=\s*\{(.*?)' + seguinte, texto, re.S | re.M)
    bloco_talk = re.search(r'^Talk\s*=\s*\{(.*?)' + seguinte, texto, re.S | re.M)

    skills = {}
    if bloco_skills:
        for nome, valor in re.findall(r'\((\w+),\s*(-?\d+)', bloco_skills.group(1)):
            skills.setdefault(nome, int(valor))

    achado_nome = re.search(r'^Name\s*=\s*"([^"]*)"', texto, re.M)
    nome_do_mon = achado_nome.group(1) if achado_nome else monstro

    falas = []
    if bloco_talk:
        for achado in re.finditer(r'"(#[yY])?\s*([^"]*)"', bloco_talk.group(1)):
            falas.append({'grita': achado.group(1) == '#Y', 'frase': achado.group(2).strip()})

    return {
        'nome': nome_do_mon,
        'racenumero': numero('RaceNumber'),
        'corpse': numero('Corpse'),
        'sangue': palavra('Blood'),
        'experiencia': numero('Experience'),
        'custo_invocacao': numero('SummonCost'),
        'foge': numero('FleeThreshold') or 0,
        'ataque': numero('Attack'),
        'defesa': numero('Defend'),
        'armadura': numero('Armor'),
        'velocidade_base': skills.get('GoStrength'),
        'vida': skills.get('HitPoints'),
        'skill_melee': skills.get('FistFighting'),
        'outfit': [int(outfit.group(1))] + [int(p) for p in outfit.group(2).split('-')] if outfit else [],
        'estrategia': [int(p) for p in re.findall(r'-?\d+', estrategia.group(1))] if estrategia else [],
        'flags': set(re.findall(r'[A-Za-z]+', bloco_flags.group(1))) if bloco_flags else set(),
        'invoca': [
            {'typeid': int(t), 'chance': 100.0 / int(n)}
            for t, _c, n in re.findall(r'Summon\s*\((\d+),\s*(\d+)\)\s*:\s*(\d+)', texto)
        ],
        'falas': falas,
    }


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
            bruto = atributos.get('chance') or atributos.get('chance1') or 0
            entradas.append({
                'id': int(atributos['id']),
                'countmax': int(atributos.get('countmax', 1)),
                'chance': int(bruto) / 1000,
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


def _nomes_por_id(base):
    return {i: _normalizar(nome) for nome, ids in items_740(base).items() for i in ids}


@lru_cache(maxsize=4)
def nomes_crus_740(base=BASE_PADRAO):
    caminho = f'{base}/Tools/Map Editor/data/740/items.xml'
    texto = open(caminho, encoding='latin-1').read()
    return {
        int(ident): nome
        for ident, nome in re.findall(r'<item\s+id="(\d+)"[^>]*name="([^"]*)"', texto)
    }


def _comparar_identidade(base, cabecalho, texto):
    """Cruza race, corpse, flags, imunidades, invocacoes e vozes do XML com o .mon."""
    problemas = []
    divergencias = []
    objetos = objetos_do_srv(base)

    esperado = SANGUE_PARA_RACE.get((cabecalho['sangue'] or '').lower(), '')
    achado = re.search(r'<monster[^>]*\brace="(\w+)"', texto)
    if achado and esperado and achado.group(1).lower() != esperado:
        divergencias.append(
            f'race="{achado.group(1)}" mas o .mon diz {cabecalho["sangue"]} -> devia ser "{esperado}"'
        )

    if cabecalho['corpse'] is not None:
        nome_corpse = objetos.get(cabecalho['corpse'], '')
        achado = re.search(r'corpse="(\d+)"', texto)
        if not achado:
            problemas.append(
                f'sem corpse="": o .mon diz Corpse {cabecalho["corpse"]} ("{nome_corpse}")'
            )
        else:
            ident = int(achado.group(1))
            crus = nomes_crus_740(base)
            do_item = crus.get(ident, '')
            if not do_item:
                problemas.append(f'corpse="{ident}" nao existe no items.xml')
            else:
                nosso = _normalizar(do_item)
                do_mon = _normalizar(nome_corpse)
                proprios = sorted(
                    i for i, nome in crus.items()
                    if CORPO_DE.match(_sem_artigo(nome))
                    and _palavras(cabecalho['nome']) <= _palavras(nome)
                )
                if proprios and ident in proprios:
                    pass
                elif proprios:
                    problemas.append(
                        f'corpse="{ident}" e "{_sem_artigo(do_item)}", mas o corpo deste monstro'
                        f' e "{_sem_artigo(crus[proprios[0]])}" (id {proprios[0]})'
                    )
                elif nosso in do_mon or do_mon in nosso:
                    pass
                elif CORPO_DE.match(_sem_artigo(nome_corpse)) and not CORPO_DE.match(
                    _sem_artigo(do_item)
                ):
                    problemas.append(
                        f'corpse="{ident}" e "{_sem_artigo(do_item)}", que nao e corpo,'
                        f' e o .mon diz que o corpo e "{_sem_artigo(nome_corpse)}"'
                    )
                else:
                    divergencias.append(
                        f'corpo: o .mon chama-lhe "{_sem_artigo(nome_corpse)}" e o XML usa'
                        f' "{_sem_artigo(do_item)}" - confirmar no video'
                    )

    tabelas = {}
    for secao, tag in (('flags', 'flag'), ('immunities', 'immunity')):
        bloco = re.search(r'<%s>(.*?)</%s>' % (secao, secao), texto, re.S)
        tabelas[secao] = dict(re.findall(r'<%s\s+(\w+)="(-?\d+)' % tag, bloco.group(1))) if bloco else {}

    for atributo, (flag, (secao, _, valor)) in {
        alvo[1]: (nome, alvo) for nome, alvo in FLAGS_DO_MON.items()
    }.items():
        atual = tabelas[secao].get(atributo)
        if flag in cabecalho['flags']:
            if atual is None:
                divergencias.append(f'.mon tem {flag} e o XML nao declara {secao}/{atributo}')
            elif atual != valor:
                divergencias.append(
                    f'{secao}/{atributo}="{atual}" mas o .mon tem {flag} -> devia ser "{valor}"'
                )
            continue
        esperado_sem = '0' if valor == '1' else '1'
        if atual is None or atual == esperado_sem:
            continue
        if secao == 'immunities' and valor == '1':
            if atributo == 'physical':
                problemas.append(
                    'imunidade a physical="1" que o .mon nao tem (NoHit ausente)'
                    ' - o monstro fica invulneravel a dano fisico'
                )
            else:
                divergencias.append(
                    f'imunidade a {atributo}="1" que o .mon nao declara ({flag} ausente)'
                )
        else:
            divergencias.append(
                f'{secao}/{atributo}="{atual}" com {flag} ausente no .mon -> devia ser "{esperado_sem}"'
            )

    for rotulo, do_mon, padrao in (
        ('health', cabecalho['vida'], r'<health[^>]*max="(-?\d+)"'),
        ('defenses armor', cabecalho['armadura'], r'<defenses[^>]*armor="(-?\d+)"'),
        ('defenses defense', cabecalho['defesa'], r'<defenses[^>]*defense="(-?\d+)"'),
        ('experience', cabecalho['experiencia'], r'<monster[^>]*\bexperience="(-?\d+)"'),
        ('manacost', cabecalho['custo_invocacao'], r'<monster[^>]*\bmanacost="(-?\d+)"'),
        ('melee attack', cabecalho['ataque'], r'<attack name="melee"[^>]*attack="(-?\d+)"'),
        ('melee skill', cabecalho['skill_melee'], r'<attack name="melee"[^>]*skill="(-?\d+)"'),
    ):
        if do_mon is None:
            continue
        achado = re.search(padrao, texto)
        if achado and int(achado.group(1)) != do_mon:
            divergencias.append(f'{rotulo}: .mon {do_mon} vs xml {achado.group(1)}')

    for indice, atributo in ((0, 'attack'), (1, 'defense'), (2, 'hurt')):
        if len(cabecalho['estrategia']) <= indice:
            continue
        achado = re.search(r'<strategy[^>]*\b%s="(-?\d+)"' % atributo, texto)
        if achado and int(achado.group(1)) != cabecalho['estrategia'][indice]:
            divergencias.append(
                f'strategy {atributo}: .mon {cabecalho["estrategia"][indice]} vs xml {achado.group(1)}'
            )

    chances_do_mon = [ficha['chance'] for ficha in cabecalho['invoca']]
    chances_do_xml = []
    for achado in re.finditer(r'<summon\s+([^>]*)/>', texto):
        atributos = dict(re.findall(r'(\w+)="([^"]*)"', achado.group(1)))
        try:
            chances_do_xml.append(float(atributos.get('chance', 0)))
        except ValueError:
            continue
    if len(chances_do_mon) != len(chances_do_xml):
        divergencias.append(
            f'o .mon invoca {len(chances_do_mon)} criatura(s) e o XML invoca {len(chances_do_xml)}'
        )
    else:
        for do_mon, do_xml in zip(sorted(chances_do_mon), sorted(chances_do_xml)):
            if abs(do_mon - do_xml) > 1.0:
                divergencias.append(
                    f'chance de invocacao: .mon {do_mon:.0f}% vs xml {do_xml:.0f}%'
                )

    vozes = []
    for achado in re.finditer(r'<voice\s+([^>]*)/>', texto):
        atributos = dict(re.findall(r'(\w+)="([^"]*)"', achado.group(1)))
        vozes.append((html.unescape(atributos.get('sentence', '')), atributos.get('yell')))
    if vozes:
        if len(vozes) < len(cabecalho['falas']):
            divergencias.append(
                f'o .mon tem {len(cabecalho["falas"])} fala(s) e o XML tem {len(vozes)}'
            )
        por_frase = dict(vozes)
        for fala in cabecalho['falas']:
            if fala['frase'] not in por_frase:
                continue
            grita = por_frase[fala['frase']] == '1'
            if fala['grita'] and not grita:
                divergencias.append(
                    f'voz "{fala["frase"][:38]}" comeca por #Y (grito) e o XML nao tem yell="1"'
                )
            elif not fala['grita'] and grita:
                divergencias.append(
                    f'voz "{fala["frase"][:38]}" sai gritada no XML e o .mon nao tem #Y'
                )

    return problemas, divergencias


def _nome_do_mon_por_chance(inventario, chance):
    candidatos = {}
    for produto in inventario:
        if abs(produto['chance'] - chance) <= 1.0:
            candidatos[_normalizar(produto['nome'])] = produto['nome']
    if len(candidatos) == 1:
        return next(iter(candidatos.values()))
    return None


def validar_monstro(base, monstro):
    """Confere o XML de um monstro contra o .mon, o items.xml e o motor, e diz o que esta errado."""
    cruz = cruzar_monstro(base, monstro)
    if 'erro' in cruz:
        return cruz
    texto = _texto_do_xml(base, monstro) or ''
    nomes = _nomes_por_id(base)
    servidor = objetos_do_srv(base)
    do_mon = {_normalizar(p['nome']) for p in cruz['inventario']}

    problemas = []
    divergencias = []
    ja_avisado = set()

    for entrada in cruz['xml']:
        if entrada['id'] == 1987:
            continue
        ident = entrada['id']
        if not 0 <= entrada['chance'] <= 100:
            problemas.append(f'id {ident} com chance {entrada["chance"]} fora de 0..100')
        if ident in nomes:
            if nomes[ident] not in do_mon and nomes[ident] not in ja_avisado:
                ja_avisado.add(nomes[ident])
                gemeo = _nome_do_mon_por_chance(cruz['inventario'], entrada['chance'])
                if gemeo:
                    divergencias.append(
                        f'"{nomes[ident]}" ({ident}) nao casa por nome, mas o .mon tem'
                        f' "{gemeo}" com a mesma chance ({entrada["chance"]:.0f}%) -'
                        f' provavel o mesmo item'
                    )
                else:
                    divergencias.append(
                        f'"{nomes[ident]}" ({ident}) esta no XML e o .mon nao o tem -'
                        f' confirmar no video antes de apagar'
                    )
            continue
        if ident in servidor:
            problemas.append(
                f'id {ident} NAO existe no items.xml - no objects.srv e "{servidor[ident]}";'
                f' e id do servidor CipSoft, nao do nosso items.xml'
            )
        else:
            problemas.append(f'id {ident} nao existe no items.xml nem no objects.srv')

    do_xml = {}
    for entrada in cruz['xml']:
        if entrada['id'] == 1987:
            continue
        do_xml.setdefault(entrada['id'], []).append(entrada['chance'])
    do_mon_por_nome = {}
    for produto in cruz['inventario']:
        do_mon_por_nome.setdefault(_normalizar(produto['nome']), []).append(produto['chance'])
    for nome, chances_no_mon in do_mon_por_nome.items():
        entradas_xml = [c for i, n in nomes.items() if n == nome for c in do_xml.get(i, [])]
        if not entradas_xml:
            continue
        if nome in ja_avisado:
            continue
        junto_mon = 1.0
        for chance in chances_no_mon:
            junto_mon *= 1.0 - chance / 100.0
        junto_xml = 1.0
        for chance in entradas_xml:
            junto_xml *= 1.0 - chance / 100.0
        esperado = (1.0 - junto_mon) * 100.0
        junto = round((1.0 - junto_xml) * 100.0, 2)
        if abs(junto - esperado) <= max(2.0, esperado * 0.2):
            continue
        ja_avisado.add(nome)
        detalhe = ", ".join(f"{c:.1f}" for c in entradas_xml)
        chave_mon = ", ".join(f"{c:.1f}" for c in chances_no_mon)
        divergencias.append(
            f'chance de "{nome}" difere: .mon {chave_mon} ({esperado:.1f} juntas) vs'
            f' xml {detalhe} ({junto:.1f} juntas)'
        )

    cabecalho = cabecalho_do_mon(base, monstro)
    if cabecalho:
        da_identidade, divergencias_da_identidade = _comparar_identidade(base, cabecalho, texto)
        problemas.extend(da_identidade)
        divergencias.extend(divergencias_da_identidade)

    melee = re.search(r'<attack name="melee"[^>]*>', texto)
    if melee:
        linha = melee.group(0)
        tem_formula = 'skill=' in linha and 'attack=' in linha
        tem_faixa = 'min=' in linha and 'max=' in linha
        if not (tem_formula or tem_faixa):
            problemas.append('melee SEM skill+attack e SEM min+max: o motor nao carrega dano nenhum')

    if 'Tibia - graphical' not in texto:
        problemas.append('sem o cabecalho "# Tibia - graphical Multi-User-Dungeon" no inicio do ficheiro')

    ordem = [m.group(1) for m in re.finditer(r'<(flags|attacks|defenses|immunities|summons|loot|voices)>', texto)]
    if 'voices' in ordem and ordem[-1] != 'voices':
        problemas.append(f'voices nao fica por ultimo (ordem atual: {ordem})')

    return {
        'monstro': monstro,
        'problemas': problemas,
        'divergencias': divergencias,
        'ok': not problemas,
        'produtos_no_mon': cruz['produtos_no_mon'],
        'entradas_no_xml': cruz['entradas_no_xml'],
    }
