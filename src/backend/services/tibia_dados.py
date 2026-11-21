import html
import json
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

RECEITA_DO_MON = """=== RECEITA .mon -> XML (conferida no codigo do motor; manda sobre qualquer nota antiga) ===

TABELA 1 - todos os campos
health=HitPoints 1:1 | experience=Experience 1:1, MAS o video manda quando existe (so vale a
gravacao onde o jogador mata SO aquele monstro: morte em area soma varios de uma vez e falseia o
salto de xp) | defenses armor=Armor 1:1 | defenses defense=Defend 1:1 | blockValue=def*skill/19 |
melee skill=FistFighting 1:1 | melee attack=Attack 1:1 | melee min/max=Damage(base,var) ->
base-var..base+var | melee poison=Poison 1:1 | cura min/max=Healing(base,var) -> base-var..base+var |
cura chance=Healing:N -> 100/N com interval="2000" | speed=GoStrength -> 2*GS+80 (as 41 fixadas a
olho nao se tocam) | speedchange=(a-b)*10, per-mil, nunca abaixo de -1000 | speedchange_max=(a+b)*10 |
duration=c*1000 (c em segundos) | chance da magia speed=50/N com interval="1000" (ou 100/N com
"2000") | outras magias=100/N com interval="2000".

O INTERVALO NAO EXISTE NO .mon. O original rola as magias num ciclo de 2s, mas o motor tem DOIS
contadores independentes (monster.cpp: attackTicks e defenseTicks), por isso um ataque pode sair a
1s e a cura a 2s no mesmo bicho. Medido: a pedra do dwarf geomancer sai a 1s e a cura a 2s. O ritmo
tira-se da gravacao (missil pela posicao de ORIGEM, cura pelo id de criatura da vida), nunca se
adivinha - e entre 1s e 2s a diferenca e o dobro da frequencia.

A DEFESA DO MONSTRO (monster.cpp:513)
  if(mType->defense <= 0) return 0;
  skill = meleeSkill do <attack name="melee">; if(skill <= 0) skill = 42;
  return mType->defense * skill / 19;
  Armadilhas: monstro SEM melee usa skill=42 (def 60 bloqueia 132, nao zero); defense<=0 devolve 0 e
  o ramo do escudo nem corre.

O MELEE DO MONSTRO (weapons.cpp getMaxMeleeDamage)
  ceil(skill*attack*0.05 + attack*0.5); o dano sai de 0 ate esse valor.
  O motor so ignora min/max quando a entrada traz skill+attack JUNTOS (monsters.cpp:415); sem os
  dois le min/max direto - por isso min="-0" max="-800" funciona e NAO se mexe.

SUMMON (dentro do bloco Spells: "Origin (0, 13) -> Summon (id, max) : N")
  chance = 100/N (igual as outras magias, com interval="2000") | maxSummons = max.
  O `max` de cada <summon> e INERTE no motor (monsters.cpp le so speed/interval, chance e name):
  quem manda e o maxSummons do <summons>.
  O `id` e o RaceNumber do .mon, NUNCA o nome - converter pelo RaceNumber de cada .mon
  (ex: 35=demon, 49=fire elemental, 72=stalker, 101=bonebeast, 20=slime2, 19=slime).
  O NOME TEM DE EXISTIR no monsters.xml: summon com nome inexistente CARREGA e nunca invoca nada,
  em silencio. Casos medidos: 'bonebeast' -> 'bone beast'; 'stalkers' -> 'stalker'.
  CHANCE ACIMA DE 100 E BUG: o motor faz chance=100 quando passa de 100 (monsters.cpp), logo
  chance="3000" significa SEMPRE invocar. Os valores 1000/3000 sao uma coluna por-mil mal copiada.

LOSETARGET -> targetchange chance, 1:1 (PROVADO e ja aplicado em 80 XML)
  chance = LoseTarget. O Tarsal documenta "chance creature will retarget" e os 11 monstros
  DistanceFighting do projeto tem 50; os 25 que ja tinham chance="0" no XML sao exactamente os que
  tem LoseTarget=0. O chance="8" fixo era enchimento do datapack.
  O INTERVALO nao se converte: o campo nao existe no .mon. Fica como esta.
  Diferenca de comportamento que continua: o original escolhe o alvo mais PROXIMO ao retargetar e o
  nosso motor usa searchTarget(TARGETSEARCH_RANDOM) (monster.cpp:866).

STRATEGY - quatro numeros no .mon, tres no XML, e nao falta nada
  Strategy = (a, b, c, d) e A SOMA E SEMPRE 100 (medido nos 154 .mon).
  attack=a (alvo mais PROXIMO) | defense=b (menos vida) | hurt=c (quem mais dano lhe fez) |
  d = a fatia "sem preferencia", que NAO se escreve no XML: o motor cai nela sozinho quando o
  sorteio passa de a+b+c (monster.cpp:417-433, strategy 3 = escolha aleatoria entre os candidatos).
  Medido a 2026-11-18: 105 de 105 monstros batem. Nao e campo a corrigir em massa.

TABELA 2 - LOOT: onde vai e em que ordem
chance: .mon por mil -> chance = por_mil*100 (motor MAX_LOOTCHANCE=100000); 800=80%.
countmax 1:1 (o motor sorteia 1..countmax). chancemax e INERTE.
gold: entradas separadas, cada uma com o seu sorteio - nunca um countmax grande.
BAG: Weapon, Shield, Bow, Throw, Wand, Torch, aneis COM CARGA.
CORPO: Armor, Food, gold, joias/colares, pedras, runas, osso/chifre/ervas.
Food e gold podem cair no corpo E na bag; o .mon tem UMA entrada e as duas do XML sao aproximacao
nossa - confirmar monstro a monstro.
saco vazio nao cai (o motor apaga container sem itens): a linha da bag vai a chance="100000".
ORDEM (a do FICHEIRO - a ferramenta acusa quando falha): a bag e a PRIMEIRA linha do <loot> e, por
baixo dela, o corpo vem em ordem ALFABETICA CRESCENTE; DENTRO da bag a ordem e ALFABETICA
DECRESCENTE. Container que esteja dentro da bag conta como um item da bag, pelo seu proprio nome,
e o que ele traz dentro segue a mesma regra decrescente. Ordena-se pelo NOME do items.xml COM
espacos: "gold ring" vem antes de "golden legs". No ecra sai ao contrario (corpo decrescente, bag
crescente) - nunca inverter o ficheiro por causa disso.

O ID DO ITEM - a cadeia que NUNCA se atalha
  1. o .mon guarda o TypeID do objects.srv, que vive em
     gerados/monstros/cipsoft/objects.srv e e TEXTO PURO - abre com '# ObjectTypes File for Server'
     e le-se como um .txt, sem ferramenta especial.
  2. Esse TypeID NAO e o id do nosso servidor. objects.srv 3447 = 'an arrow', mas no nosso items.xml
     3447 nao existe e arrow e 2544. Caminho obrigatorio: TypeID -> Name no objects.srv -> nome sem
     artigo -> id do NOSSO items.xml (o nosso poe o article ENTRE o id e o name).
  3. O nome pode diferir de um lado para o outro e ser o MESMO item (broadsword / broad sword,
     magic lightwand / magic light wand, o 'a spellbook' do .mon) - casar por nome normalizado,
     nunca por numero.
  4. Item que o .mon cita e o nosso items.xml nao tem = item que nao existe nesta versao (o
     'wand of cosmic energy' do elf arcanist, que o .mon traz por ser 7.5): fica FORA do XML e
     diz-se isso na resposta, com o nome.
  5. ANTES de dizer que uma linha do XML 'esta a mais', listar o Inventory INTEIRO pelo objects.srv.
     O que parece invencao pode ser fiel: a 'morning star' a 10% do elder beholder, que a wiki manda
     apagar e o .mon prova que cai. E antes de acrescentar um item que o .mon tem, confirmar que o
     NOME existe no nosso items.xml - se nao existe, nao entra.

AS 4 REGRAS DE OURO
1. Uma entrada do .mon = um sorteio = um destino. Varias entradas do mesmo item podem cair nos dois
   lados do MESMO corpo - e normal (ouro do demon).
2. A bag do monstro e a que esta DENTRO do corpo; a mochila do jogador aberta logo depois NAO e bag
   do monstro - descartar.
3. Ouro nunca se calibra pelo video (o jogador saqueia) - serve para saber ONDE a pilha cai.
4. Posicao nao se calibra por "quantas vezes apareceu num sitio": soma corpo+saco e compara com o
   numero de entradas do .mon.

PADRAO DO FICHEIRO
'# Tibia - graphical Multi-User-Dungeon' no inicio -> informacoes do monstro -> flags -> ataque ->
defesa -> imunidade -> loot -> vozes POR ULTIMO, com uma linha em branco entre cada bloco.
Modelo: amazon.xml. Conferir tambem o nameDescription (o Article do .mon manda: 'an elf', nao 'a elf').

ORDEM DE VALIDACAO
1 tool_validar_monstro (ids, chances, melee, cabecalho, ordem, separacao, nameDescription)
2 tool_ler_rec(varrer=X, loot=X) - todas as gravacoes, com o sitio de cada item
3 tool_ler_rec(gravacao=Y, loot=X) - corpo a corpo numa gravacao
4 .mon -> video/.rec -> datapack 7.4 -> wiki ou notas do Tarsal
  (https://tibiantis-notes.github.io/Creature) -> tibia-rust (so estrutura e ticks, nunca
  comportamento)

CRUZAR SEMPRE, NUNCA UMA FONTE SO
Nem o .mon (e de 7.5), nem o video (amostra pequena), nem a wiki (erra data e chance) sao a verdade
sozinhos: cruzar os quatro e dizer de onde veio cada facto. Analisar bloco a bloco: monster, health,
look, targetchange, strategy, flags, attacks, defenses, immunities, summon, voices, loot."""


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
    bloco_spells = re.search(r'^Spells\s*=\s*\{(.*?)' + seguinte, texto, re.S | re.M)

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

    magias = []
    if bloco_spells:
        for achado in re.finditer(
            r'(Actor|Victim|Origin|Angle|Destination)\s*\(([^)]*)\)\s*->\s*(\w+)\s*'
            r'\(((?:[^()]|\([^()]*\))*)\)\s*:\s*(\d+)',
            bloco_spells.group(1),
        ):
            magias.append({
                'quem': achado.group(1),
                'efeito': achado.group(3),
                'numeros': [int(p) for p in re.findall(r'-?\d+', achado.group(4))],
                'n': int(achado.group(5)),
            })

    artigo = re.search(r'^Article\s*=\s*"([^"]*)"', texto, re.M)

    return {
        'nome': nome_do_mon,
        'artigo': artigo.group(1).strip() if artigo else '',
        'racenumero': numero('RaceNumber'),
        'corpse': numero('Corpse'),
        'sangue': palavra('Blood'),
        'experiencia': numero('Experience'),
        'custo_invocacao': numero('SummonCost'),
        'foge': numero('FleeThreshold') or 0,
        'lose_target': numero('LoseTarget'),
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
            {'typeid': int(t), 'max': int(c), 'chance': 100.0 / int(n)}
            for t, c, n in re.findall(r'Summon\s*\((\d+),\s*(\d+)\)\s*:\s*(\d+)', texto)
        ],
        'falas': falas,
        'magias': magias,
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
def _monstros_registados(base=BASE_PADRAO):
    texto = open(f'{base}/Server/data/monster/monsters.xml', encoding='latin-1').read()
    return {_normalizar(nome) for nome in re.findall(r'<monster\s+name="([^"]+)"', texto)}


@lru_cache(maxsize=4)
def nomes_crus_740(base=BASE_PADRAO):
    caminho = f'{base}/Tools/Map Editor/data/740/items.xml'
    texto = open(caminho, encoding='latin-1').read()
    return {
        int(ident): nome
        for ident, nome in re.findall(r'<item\s+id="(\d+)"[^>]*name="([^"]*)"', texto)
    }


def _comparar_identidade(base, cabecalho, texto, xp_do_video=None):
    """Cruza race, corpse, flags, imunidades, invocacoes e vozes do XML com o .mon."""
    problemas = []
    divergencias = []
    objetos = objetos_do_srv(base)

    esperado = SANGUE_PARA_RACE.get((cabecalho['sangue'] or '').lower(), '')
    achado = re.search(r'<monster[^>]*\brace="(\w+)"', texto)
    if achado and esperado and achado.group(1).lower() != esperado:
        divergencias.append(
            f'race="{achado.group(1)}" mas o .mon diz {cabecalho["sangue"]} -> devia ser "{esperado}"'
            f' (confirme com tool_ler_rec raca={cabecalho["nome"]}: a cor do numero e o efeito 9/16'
            f' no tile do monstro provam a race na gravacao)'
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

    experiencia_do_video = xp_do_video if xp_do_video is not None else cabecalho['experiencia']
    for rotulo, do_mon, padrao in (
        ('health', cabecalho['vida'], r'<health[^>]*max="(-?\d+)"'),
        ('defenses armor', cabecalho['armadura'], r'<defenses[^>]*armor="(-?\d+)"'),
        ('defenses defense', cabecalho['defesa'], r'<defenses[^>]*defense="(-?\d+)"'),
        ('experience', experiencia_do_video, r'<monster[^>]*\bexperience="(-?\d+)"'),
        ('manacost', cabecalho['custo_invocacao'], r'<monster[^>]*\bmanacost="(-?\d+)"'),
        ('melee attack', cabecalho['ataque'], r'<attack name="melee"[^>]*attack="(-?\d+)"'),
        ('melee skill', cabecalho['skill_melee'], r'<attack name="melee"[^>]*skill="(-?\d+)"'),
    ):
        if do_mon is None:
            continue
        achado = re.search(padrao, texto)
        if achado and int(achado.group(1)) != do_mon:
            divergencias.append(f'{rotulo}: .mon {do_mon} vs xml {achado.group(1)}')

    achado_speed = re.search(r'<monster[^>]*\bspeed="(-?\d+)"', texto)
    if achado_speed and cabecalho['velocidade_base'] is not None:
        base_speed = cabecalho['velocidade_base']
        esperado_speed = 2 * base_speed + 80 if base_speed > 0 else 0
        if int(achado_speed.group(1)) != esperado_speed:
            motivo = 'GoStrength -1 quer dizer parado' if base_speed <= 0 else (
                f'2*GoStrength+80 com GoStrength {base_speed}'
            )
            divergencias.append(
                f'speed: xml {achado_speed.group(1)} e o .mon da {esperado_speed} ({motivo})'
                f' - so mexer com o video: ha speeds fixados a mao que nao seguem a formula'
            )

    achado_look = re.search(r'<look\s+([^>]*?)/?>', texto)
    if achado_look and cabecalho.get('outfit'):
        look = dict(re.findall(r'(\w+)="([^"]*)"', achado_look.group(1)))
        if 'type' in look and int(look['type']) != cabecalho['outfit'][0]:
            divergencias.append(
                f'look type="{look["type"]}" mas o Outfit do .mon e {cabecalho["outfit"][0]}'
                f' - troca so visual: aplicar apenas se o outfit {cabecalho["outfit"][0]}'
                f' existir no cliente, senao o monstro fica invisivel'
            )

    achado_melee = re.search(r'<attack name="melee"([^>]*)/>', texto)
    if (
        achado_melee
        and 'skill=' not in achado_melee.group(1)
        and 'min=' in achado_melee.group(1)
        and cabecalho['ataque']
        and cabecalho['skill_melee']
    ):
        bruto = cabecalho['skill_melee'] * cabecalho['ataque'] * 5 + cabecalho['ataque'] * 50
        dano_max = -(-bruto // 100)
        divergencias.append(
            f'melee escrito por min/max: o .mon da FistFighting {cabecalho["skill_melee"]} e'
            f' Attack {cabecalho["ataque"]} -> skill="{cabecalho["skill_melee"]}"'
            f' attack="{cabecalho["ataque"]}" (dano 0..{dano_max})'
        )

    querida = cabecalho['estrategia'][:3]
    if querida != [0, 0, 0] and not re.search(r'<strategy[^>]*\battack=', texto):
        divergencias.append(
            f'sem <strategy attack/defense/hurt>: o .mon diz {querida}'
            f' (a 4a entrada do .mon, {100 - sum(querida)}, e a fatia "sem preferencia",'
            f' que nao se escreve no XML)'
        )

    for indice, atributo in ((0, 'attack'), (1, 'defense'), (2, 'hurt')):
        if len(cabecalho['estrategia']) <= indice:
            continue
        achado = re.search(r'<strategy[^>]*\b%s="(-?\d+)"' % atributo, texto)
        if achado and int(achado.group(1)) != cabecalho['estrategia'][indice]:
            divergencias.append(
                f'strategy {atributo}: .mon {cabecalho["estrategia"][indice]} vs xml {achado.group(1)}'
            )

    if cabecalho.get('lose_target') is not None:
        achado = re.search(r'<targetchange([^>]*)/>', texto)
        if achado:
            atual = dict(re.findall(r'(\w+)="([^"]*)"', achado.group(1))).get('chance')
            if atual is not None and atual != str(cabecalho['lose_target']):
                divergencias.append(
                    f'targetchange chance="{atual}" mas o .mon tem LoseTarget '
                    f'{cabecalho["lose_target"]} -> devia ser "{cabecalho["lose_target"]}"'
                )

    de_dano = [magia for magia in cabecalho['magias']
               if magia['quem'] != 'Actor' and magia['efeito'] != 'Summon']
    ataques = [nome for nome in re.findall(r'<attack\s+name="(\w+)"', texto) if nome != 'melee']
    if len(ataques) > len(de_dano):
        divergencias.append(
            f'o XML tem {len(ataques)} magia(s) de ataque ({", ".join(ataques)}) e o .mon '
            f'declara {len(de_dano)} - ataque que o original nao tem'
        )

    chances_do_mon = [ficha['chance'] for ficha in cabecalho['invoca']]
    registados = _monstros_registados(base)
    chances_do_xml = []
    for achado in re.finditer(r'<summon\s+([^>]*)/>', texto):
        atributos = dict(re.findall(r'(\w+)="([^"]*)"', achado.group(1)))
        nome = atributos.get('name', '')
        if _normalizar(nome) not in registados:
            problemas.append(
                f'summon name="{nome}" nao existe no monsters.xml: o monstro carrega e nunca invoca'
            )
        try:
            chance = float(atributos.get('chance', 0))
        except ValueError:
            chance = 0.0
        if chance > 100 or chance < 0:
            problemas.append(
                f'summon "{nome}" com chance="{atributos.get("chance")}" fora de 0..100:'
                ' o motor corta para 100 e o monstro invoca sempre'
            )
        chances_do_xml.append(chance)
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
    teto = re.search(r'<summons\s+maxSummons="(\d+)"', texto)
    if teto and cabecalho['invoca']:
        maior = max(ficha['max'] for ficha in cabecalho['invoca'])
        if int(teto.group(1)) < maior:
            divergencias.append(
                f'maxSummons="{teto.group(1)}" nao chega ao max={maior} que o .mon da a invocacao'
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


def _ritmo_das_magias(cabecalho, texto):
    """Confere o ritmo: o .mon rola as magias a cada 2s, logo : N vale 30/N por minuto."""
    problemas = []
    divergencias = []
    ataques = []
    for achado in re.finditer(r'<attack\s+([^>]*)>', texto):
        atributos = dict(re.findall(r'(\w+)="([^"]*)"', achado.group(1)))
        try:
            ataques.append({
                'nome': atributos.get('name', ''),
                'intervalo': int(atributos.get('interval') or 0),
                'chance': float(atributos.get('chance') or 0),
                'min': abs(int(atributos.get('min') or 0)),
                'max': abs(int(atributos.get('max') or 0)),
                'usado': False,
            })
        except ValueError:
            continue
    curas = []
    for achado in re.finditer(r'<defense\s+([^>]*)>', texto):
        atributos = dict(re.findall(r'(\w+)="([^"]*)"', achado.group(1)))
        if atributos.get('name') != 'healing':
            continue
        try:
            curas.append({
                'intervalo': int(atributos.get('interval') or 0),
                'chance': float(atributos.get('chance') or 0),
                'usado': False,
            })
        except ValueError:
            continue

    for magia in cabecalho['magias']:
        if magia['n'] <= 0:
            continue
        numeros = magia['numeros']
        esperado = 30.0 / magia['n']
        alvo = None
        rotulo = ''
        if magia['efeito'] == 'Healing':
            alvo = next((c for c in curas if not c['usado']), None)
            rotulo = 'cura'
        elif magia['efeito'] == 'Damage' and len(numeros) >= 3:
            faixa = (numeros[1] - numeros[2], numeros[1] + numeros[2])
            alvo = next(
                (a for a in ataques if not a['usado'] and (a['min'], a['max']) == faixa), None
            )
            rotulo = f'{alvo["nome"]} {faixa[0]}-{faixa[1]}' if alvo else ''
        elif magia['efeito'] == 'Speed':
            alvo = next((a for a in ataques if not a['usado'] and a['nome'] == 'speed'), None)
            rotulo = 'speed'
        if alvo is None or not alvo['intervalo']:
            continue
        alvo['usado'] = True
        real = 600.0 * alvo['chance'] / alvo['intervalo']
        razao = real / esperado
        if 0.7 <= razao <= 1.4:
            continue
        if razao > 2.5:
            veredito = f'{razao:.1f} VEZES o original'
        elif razao > 1:
            veredito = 'o DOBRO do original'
        elif razao >= 0.45:
            veredito = 'METADE do original'
        else:
            veredito = f'{1 / razao:.1f} VEZES mais lenta que o original'
        divergencias.append(
            f'ritmo da magia "{rotulo}": {real:.1f} por minuto contra {esperado:.1f} do .mon'
            f' (: {magia["n"]}, rolagem a cada 2s) - {veredito}; esta com interval='
            f'"{alvo["intervalo"]}" e chance="{alvo["chance"]:.0f}", e o par certo e'
            f' chance="{100 / magia["n"]:.0f}" com interval="2000"'
        )
    return problemas, divergencias


@lru_cache(maxsize=2)
def _indice_de_gravacoes():
    raiz = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
    caminho = os.path.join(raiz, 'data', 'indice_recs.json')
    if not os.path.exists(caminho):
        return {}
    try:
        with open(caminho, encoding='utf-8') as aberto:
            return json.load(aberto).get('gravacoes', {})
    except (OSError, ValueError):
        return {}


def _saltos_casados_com_a_morte(blocos, procurado):
    """Saltos de experiencia que tem UMA morte conhecida na janela logo antes deles."""
    nomes, mortes, saltos = {}, [], []
    anterior = None
    for evento in blocos:
        tipo = evento.get('Event')
        if tipo == 'CreatureSeen':
            nome = (evento.get('Name') or '').strip().lower()
            if nome:
                nomes[evento.get('CreatureId')] = nome
        elif tipo == 'CreatureHealthUpdated':
            if evento.get('Health') == 0 and evento.get('CreatureId'):
                mortes.append((evento.get('__t') or 0.0, evento.get('CreatureId')))
        elif tipo == 'PlayerDataUpdated':
            valor = evento.get('Experience')
            if valor is None:
                continue
            if anterior is not None and valor > anterior:
                saltos.append((evento.get('__t') or 0.0, valor - anterior))
            anterior = valor
    mortes.sort()
    meus = []
    for instante, delta in saltos:
        ids = {cid for (quando, cid) in mortes if instante - 2.0 <= quando <= instante + 0.3}
        if len(ids) == 1 and nomes.get(next(iter(ids))) == procurado:
            meus.append(delta)
    return meus


def xp_do_video(base, monstro, corpo):
    """XP real de um abate: o salto de experiencia casado com a morte daquela criatura."""
    if not monstro:
        return None
    try:
        from src.backend.tools.gravacoes import eventos_da_gravacao
    except ImportError:
        return None
    procurado = monstro.strip().lower()
    alvo = str(corpo) if corpo else None
    candidatas = []
    for caminho, dados in _indice_de_gravacoes().items():
        corpos = dados.get('corpos') or {}
        meus = int((corpos.get(alvo) or {}).get('n') or 0) if alvo else 0
        if alvo and not meus:
            continue
        candidatas.append((meus, dados.get('bytes', 0), caminho, dados.get('nome', '')))
    if not candidatas:
        return None
    candidatas.sort(key=lambda c: (-c[0], c[1]))
    amostras, gravacoes = [], []
    for _, _, caminho, nome in candidatas[:4]:
        try:
            achados = _saltos_casados_com_a_morte(eventos_da_gravacao(caminho), procurado)
        except Exception:
            continue
        if achados:
            gravacoes.append(nome)
            amostras += achados
    if not amostras:
        return None
    moda = max(set(amostras), key=amostras.count)
    return {
        'xp': max(amostras),
        'moda': moda,
        'amostras': len(amostras),
        'iguais': amostras.count(moda),
        'gravacoes': gravacoes,
    }


def _nome_do_mon_por_chance(inventario, chance):
    candidatos = {}
    for produto in inventario:
        if abs(produto['chance'] - chance) <= 1.0:
            candidatos[_normalizar(produto['nome'])] = produto['nome']
    if len(candidatos) == 1:
        return next(iter(candidatos.values()))
    return None


def _faltas_de_separacao(texto):
    """Um bloco de topo por linha, separado dos vizinhos por uma linha em branco."""
    linhas = texto.split('\n')
    aberturas = ('<flags', '<attacks', '<defenses', '<immunities', '<summons', '<loot', '<voices')
    faltas = []
    for i, linha in enumerate(linhas):
        s = linha.strip()
        if not s.startswith(aberturas) and not s.startswith('</monster>'):
            continue
        if i and linhas[i - 1].strip() != '':
            faltas.append(f'falta linha em branco antes de {s[:24]} (linha {i + 1})')
    return faltas


_ORDEM_DOS_BLOCOS = ('flags', 'attacks', 'defenses', 'immunities', 'summons', 'loot', 'voices')
_ORDEM_DO_CABECALHO = ('health', 'look', 'targetchange', 'strategy')


def _fora_de_ordem(texto, nomes, referencia, rotulo):
    vistos = []
    for achado in re.finditer(r'<\s*(' + '|'.join(nomes) + r')\b', texto):
        if not vistos or vistos[-1] != achado.group(1):
            vistos.append(achado.group(1))
    for antes, depois in zip(vistos, vistos[1:]):
        if referencia.index(antes) > referencia.index(depois):
            return [f'{rotulo}: {antes} aparece antes de {depois} e devia vir depois - a ordem e '
                    + ' -> '.join(referencia) + f' (atual: {" -> ".join(vistos)})']
    return []


def _ordem_do_xml(texto):
    """O XML segue o padrao do ficheiro: cabecalho e depois flags -> ... -> loot -> voices."""
    faltas = _fora_de_ordem(texto, _ORDEM_DO_CABECALHO, _ORDEM_DO_CABECALHO, 'cabecalho')
    faltas.extend(_fora_de_ordem(texto, _ORDEM_DOS_BLOCOS, _ORDEM_DOS_BLOCOS, 'blocos'))
    return faltas


def _itens_do_loot(linhas):
    """Cada item do loot como bloco de linhas, ja com o que traz dentro."""
    itens, i = [], 0
    while i < len(linhas):
        linha = linhas[i]
        if not linha.strip().startswith('<item'):
            i += 1
            continue
        inicio = i
        if '/>' in linha:
            fim = i
        else:
            profundidade, fim = 0, len(linhas) - 1
            while i < len(linhas):
                if linhas[i].lstrip().startswith('<item') and '/>' not in linhas[i]:
                    profundidade += 1
                if '</item>' in linhas[i]:
                    profundidade -= 1
                if profundidade == 0:
                    fim = i
                    break
                i += 1
        itens.append(linhas[inicio:fim + 1])
        i = fim + 1
    return itens


def _id_do_item(bloco):
    achado = re.search('[^a-z]id="([0-9]+)"', " " + bloco[0])
    return int(achado.group(1)) if achado else None


def _limites_do_inside(bloco):
    abre = fecha = None
    for posicao, linha in enumerate(bloco):
        if abre is None and '<inside>' in linha:
            abre = posicao
        elif abre is not None and '</inside>' in linha:
            fecha = posicao
            break
    return (abre, fecha) if abre is not None and fecha is not None else None


def _ordem_do_loot(texto, nomes):
    """No corpo crescente e o saco primeiro; dentro de cada saco, decrescente."""
    bloco = re.search(r'<loot[^>]*>(.*?)</loot>', texto, re.S)
    if not bloco:
        return []
    faltas = []

    def nome_de(item):
        return nomes.get(_id_do_item(item), '')

    def conferir(linhas, rotulo, descendente):
        itens = _itens_do_loot(linhas)
        vistos = [nome_de(item) for item in itens]
        if descendente:
            if vistos != sorted(vistos, reverse=True):
                faltas.append(f'{rotulo}: dentro do saco a ordem e decrescente'
                              f' ({" | ".join(vistos)})')
        else:
            sacos = [item for item in itens if _limites_do_inside(item)]
            corpo = [item for item in itens if not _limites_do_inside(item)]
            if itens and itens[:len(sacos)] != sacos:
                faltas.append(f'{rotulo}: o saco tem de ser o primeiro item do loot')
            do_corpo = [nome_de(item) for item in corpo]
            if do_corpo != sorted(do_corpo):
                faltas.append(f'{rotulo}: no corpo a ordem e alfabetica crescente'
                              f' ({" | ".join(do_corpo)})')
        for item in itens:
            limites = _limites_do_inside(item)
            if limites:
                conferir(item[limites[0] + 1:limites[1]], f'{rotulo}>saco', True)

    conferir(bloco.group(1).split(chr(10)), 'loot', False)
    return faltas


def _sitios_do_xml(texto):
    """id -> 'corpo' ou 'saco' conforme o <inside> em que o item aparece."""
    bloco = re.search(r'<loot[^>]*>(.*?)</loot>', texto, re.S)
    if not bloco:
        return {}
    sitios = {}
    profundidade = 0
    for achado in re.finditer(r'<inside\b|</inside\b|<item\s+id="(\d+)"', bloco.group(1)):
        pedaco = achado.group(0)
        if pedaco.startswith('<inside'):
            profundidade += 1
            continue
        if pedaco.startswith('</inside'):
            profundidade = max(0, profundidade - 1)
            continue
        ident = int(achado.group(1))
        onde = 'saco' if profundidade else 'corpo'
        if sitios.get(ident) != 'corpo':
            sitios[ident] = onde
    return sitios


@lru_cache(maxsize=4)
def nomes_do_servidor(base=BASE_PADRAO):
    """id -> nome como o servidor o escreve, com espacos: e assim que o loot se ordena."""
    texto = open(f'{base}/Server/data/items/items.xml', encoding='latin-1').read()
    achados = re.findall(r'<item[ ]+id="([0-9]+)"[^>]*name="([^"]*)"', texto)
    return {int(ident): nome.strip().lower() for ident, nome in achados}


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
    normalizados_do_xml = {_normalizar(n) for n in nomes.values()}
    rotulo_do_mon = {_normalizar(p['nome']): p['nome'] for p in cruz['inventario']}
    for nome, chances_no_mon in do_mon_por_nome.items():
        entradas_xml = [c for i, n in nomes.items() if n == nome for c in do_xml.get(i, [])]
        if not entradas_xml:
            if nome not in normalizados_do_xml:
                divergencias.append(
                    f'"{rotulo_do_mon.get(nome, nome)}" esta no Inventory do .mon e NAO existe'
                    f' no nosso items.xml - fica fora do XML por ser item de versao posterior;'
                    f' confirmar que o nome nao e outro do 7.4'
                )
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

    quantidades_do_xml = {}
    for entrada in cruz['xml']:
        if entrada['id'] == 1987:
            continue
        quantidades_do_xml.setdefault(entrada['id'], set()).add(entrada['countmax'])
    for nome in do_mon_por_nome:
        do_mon_qtd = {
            produto['quantidade'] for produto in cruz['inventario']
            if _normalizar(produto['nome']) == nome
        }
        do_xml_qtd = set()
        for identificador, nome_do_xml in nomes.items():
            if nome_do_xml == nome:
                do_xml_qtd |= quantidades_do_xml.get(identificador, set())
        if not do_xml_qtd or do_mon_qtd == do_xml_qtd:
            continue
        divergencias.append(
            f'quantidade de "{rotulo_do_mon.get(nome, nome)}": .mon '
            f'{" / ".join(str(q) for q in sorted(do_mon_qtd))} vs xml '
            f'{" / ".join(str(q) for q in sorted(do_xml_qtd))} (countmax)'
        )

    cabecalho = cabecalho_do_mon(base, monstro)
    if cabecalho:
        achado_corpo = re.search(r'corpse="(\d+)"', texto)
        video = xp_do_video(base, monstro, int(achado_corpo.group(1))) if achado_corpo else None
        confiavel = video if video and video['xp'] >= cabecalho['experiencia'] else None
        da_identidade, divergencias_da_identidade = _comparar_identidade(
            base, cabecalho, texto, confiavel['xp'] if confiavel else None
        )
        problemas.extend(da_identidade)
        divergencias.extend(divergencias_da_identidade)
        if confiavel and cabecalho['experiencia'] != confiavel['xp']:
            divergencias.append(
                f'o .mon diz Experience {cabecalho["experiencia"]} e a gravacao da'
                f' {confiavel["xp"]} por abate ({confiavel["amostras"]} abates casados,'
                f' {" e ".join(confiavel["gravacoes"])}) - o video manda, nao reverter'
                f' para {cabecalho["experiencia"]}'
            )
        elif video and video['xp'] < cabecalho['experiencia']:
            divergencias.append(
                f'Experience {cabecalho["experiencia"]}: a gravacao so mostra saltos ate'
                f' {video["xp"]} ({video["amostras"]} abates, {" e ".join(video["gravacoes"])})'
                f' - abaixo do .mon, sinal de experiencia em partilha; nao confirma nem desmente'
            )
        do_ritmo, divergencias_do_ritmo = _ritmo_das_magias(cabecalho, texto)
        problemas.extend(do_ritmo)
        divergencias.extend(divergencias_do_ritmo)
        combinado = f"{cabecalho.get('artigo', '')} {cabecalho['nome']}".strip().lower()
        achado_nome = re.search(r'nameDescription="([^"]*)"', texto)
        if achado_nome and combinado and achado_nome.group(1).strip().lower() != combinado:
            divergencias.append(
                f'nameDescription "{achado_nome.group(1)}" nao bate com o .mon'
                f' (Article "{cabecalho.get("artigo", "")}" + Name "{cabecalho["nome"]}" ='
                f' "{combinado}")'
            )

    melee = re.search(r'<attack name="melee"[^>]*>', texto)
    if melee:
        linha = melee.group(0)
        tem_formula = 'skill=' in linha and 'attack=' in linha
        tem_faixa = 'min=' in linha and 'max=' in linha
        if not (tem_formula or tem_faixa):
            problemas.append('melee SEM skill+attack e SEM min+max: o motor nao carrega dano nenhum')

    if 'Tibia - graphical' not in texto:
        problemas.append('sem o cabecalho "# Tibia - graphical Multi-User-Dungeon" no inicio do ficheiro')

    problemas.extend(_ordem_do_xml(texto))

    try:
        from src.backend.tools.gravacoes import posicoes_do_loot
        vistas = posicoes_do_loot(monstro)
    except (ImportError, OSError, ValueError):
        vistas = {}
    if vistas:
        for ident, sitio in _sitios_do_xml(texto).items():
            if ident == 1987 or ident not in vistas or vistas[ident] == sitio:
                continue
            divergencias.append(
                f'"{nomes.get(ident, ident)}" ({ident}) esta no {sitio} do XML e as'
                f' gravacoes mostram-no no {vistas[ident]} - o video manda na posicao'
            )

    problemas.extend(_ordem_do_loot(texto, nomes_do_servidor(base)))

    problemas.extend(_faltas_de_separacao(texto))

    return {
        'monstro': monstro,
        'problemas': problemas,
        'divergencias': divergencias,
        'ok': not problemas,
        'produtos_no_mon': cruz['produtos_no_mon'],
        'entradas_no_xml': cruz['entradas_no_xml'],
    }
