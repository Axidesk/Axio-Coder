import os
import time

from src.backend.builds import construir, depurar, detetar, diagnosticos, instalar, kits
from src.backend.config import APP_ROOT
from src.backend.services.saida import recortar_texto
from src.backend.state import emit_event, estado, notificar_mudanca_arquivos
from src.backend.tools.process import (correr_como_card, escrever_stdin_processo, iniciar_processo,
                                       parar_processo_reg, registrar_linha_processo,
                                       seguir_saida_processo)
from src.backend.tools.registry import register


@register(
    "tool_gerir_projeto",
    "Percebe, configura, compila e corre um projeto que NAO e o Axio (Qt/C++, CMake, Visual Studio). "
    "Use quando a pasta aberta - ou a indicada em 'pasta' - tiver CMakeLists.txt/.sln/.pro e a tarefa for "
    "construir, gerar o executavel ou correr o programa. Quem escolhe o kit, o gerador e os modulos e esta "
    "ferramenta: nunca peca ao utilizador para decidir compilador, versao de Qt ou caminhos. "
    "Fluxo: acao='detetar' (o que e o projeto e o que exige), 'kits' (o que esta instalado e o que foi "
    "escolhido), 'preparar' (escolhe o kit, escreve o preset e configura), 'construir' (compila), "
    "'correr' (abre o que ficou compilado), 'depurar' (abre o programa num card sob o depurador da "
    "linguagem que os pontos marcados pedem - C++ pelo cdb do Windows SDK, Python pelo pdb, que ja "
    "vem dentro do Python; sem nenhum ponto marcado corre o programa em modo de depuracao, para "
    "onde ele rebentar) e 'instalar' (traz do instalador "
    "da Qt os modulos que o projeto pede e o kit nao tem - sem uma unica janela). "
    "'construir' e 'correr' fazem o preparo sozinhos. "
    "build corre como card do terminal (saida a vivo, com botao de parar). "
    "Nao serve para ler nem editar codigo (para isso ha as ferramentas de arquivo) nem para construir o "
    "proprio Axio.",
    {
        "acao": {
            "tipo": "STRING",
            "desc": "detetar | kits | preparar | construir | correr | depurar | instalar",
            "enum": ["detetar", "kits", "preparar", "construir", "correr", "depurar", "instalar"],
            "padrao": "detetar",
        },
        "pasta": {
            "tipo": "STRING",
            "desc": "Pasta do projeto. Vazio usa a pasta de projeto aberta.",
            "padrao": "",
        },
        "configuracao": {
            "tipo": "STRING",
            "desc": "debug (por omissao) ou release",
            "enum": ["debug", "release"],
            "padrao": "debug",
        },
        "alvo": {
            "tipo": "STRING",
            "desc": "Alvo (target) especifico a compilar. Vazio compila o projeto todo.",
            "padrao": "",
        },
        "breakpoints": {
            "tipo": "STRING",
            "desc": "Pontos de paragem para 'depurar', no formato ficheiro:linha (um por linha ou "
                    "separados por ';'). Aceita modulo!ficheiro:linha quando o nome se repete. A "
                    "linguagem do primeiro ponto escolhe o depurador: ficheiro .py corre sob o pdb, "
                    "C/C++ sob o cdb.",
            "padrao": "",
        },
        "comandos": {
            "tipo": "STRING",
            "desc": "Comandos para conduzir a sessao de 'depurar' (um por linha ou separados por ';'). "
                    "Em C++: k, dv /t /v, ?? variavel, l+s, p, t, g, bp ficheiro:linha, q. Em Python: "
                    "c, n, s, p variavel, w, l, b ficheiro:linha, q - e aqui o 'p' IMPRIME uma "
                    "variavel (quem anda uma linha e o 'n'). Comandos sem breakpoints vao para a "
                    "sessao que ja esta aberta e a resposta volta aqui.",
            "padrao": "",
        },
    },
)
def tool_gerir_projeto(acao="detetar", pasta="", configuracao="debug", alvo="", breakpoints="", comandos=""):
    if acao == "depurar" and comandos and not breakpoints:
        return _depurar("", configuracao, breakpoints, comandos)
    caminho, erro = _pasta(pasta)
    if erro:
        return erro
    if acao == "detetar":
        return _texto_deteccao(detetar.detetar(caminho))
    if acao == "kits":
        return _texto_kits(caminho)
    if acao == "preparar":
        return _preparar(caminho, configuracao)
    if acao == "construir":
        return _construir(caminho, configuracao, alvo)
    if acao == "correr":
        return _correr(caminho, configuracao)
    if acao == "depurar":
        return _depurar(caminho, configuracao, breakpoints, comandos, alvo)
    if acao == "instalar":
        return _instalar(caminho, configuracao)
    return f"ERRO: acao desconhecida '{acao}'."

def _pasta(pasta):
    alvo = (pasta or "").strip() or estado.get("pasta_raiz") or ""
    if not alvo:
        return "", ("ERRO: nao ha pasta de projeto aberta e nenhuma foi indicada. Esta ferramenta nao "
                     "adivinha que projeto construir - indique o 'pasta' do projeto.")
    alvo = os.path.abspath(alvo)
    if not os.path.isdir(alvo):
        return "", f"ERRO: '{pasta}' nao e uma pasta."
    return alvo, ""

def _preparar(pasta, configuracao):
    plano = construir.preparar(pasta, configuracao)
    falha = _bloqueio(plano)
    if falha:
        return falha
    _, texto = _configurar(pasta, plano)
    return _texto_plano(plano) + "\n\n" + texto

def _configurar(pasta, plano):
    """Configura o projeto (escreve o cache do CMake) como card do terminal. Devolve (ok, texto)."""
    comando = plano["configurar"]
    emit_event("executing", function=f"Configurando {os.path.basename(pasta)} ({comando})")
    resultado = correr_como_card(comando, cwd=pasta, timeout=construir.TIMEOUT_CONFIGURAR,
                                 caminhos_extra=plano["escolha"].get("caminhos"))
    saida = recortar_texto(_texto_do_processo(resultado))
    if _interrompido(resultado):
        return False, "CONFIGURACAO INTERROMPIDA: o card do terminal foi parado."
    achados = diagnosticos.resumo(saida, raiz=pasta)
    prefixo = f"{achados}\n\n" if achados else ""
    if resultado.returncode == 0:
        notificar_mudanca_arquivos()
        return True, f"{prefixo}CONFIGURADO (exit 0).\n{saida}"
    return False, f"{prefixo}ERRO AO CONFIGURAR (exit {resultado.returncode}):\n{saida}"

def _construir(pasta, configuracao, alvo):
    plano = construir.preparar(pasta, configuracao)
    falha = _bloqueio(plano)
    if falha:
        return falha
    blocos = [_texto_plano(plano)]
    if plano.get("precisa_configurar"):
        ok, texto = _configurar(pasta, plano)
        blocos.append(texto)
        if not ok:
            return "\n\n".join(blocos)
    comando = plano["construir"] + (f" --target {alvo}" if alvo else "")
    inicio = time.time()
    emit_event("executing", function=f"Compilando {plano['deteccao'].get('projeto') or os.path.basename(pasta)}")
    resultado = correr_como_card(comando, cwd=pasta, timeout=construir.TIMEOUT_CONSTRUIR,
                                 caminhos_extra=plano["escolha"].get("caminhos"))
    saida = recortar_texto(_texto_do_processo(resultado))
    produzidos = construir.exe_produzido(
        plano["pasta_build"], desde=inicio, nome=plano["deteccao"].get("projeto", "")
    )
    if _interrompido(resultado):
        blocos.append("COMPILACAO INTERROMPIDA: o card do terminal foi parado.")
        return "\n\n".join(blocos)
    achados = diagnosticos.resumo(saida, raiz=pasta)
    if achados:
        blocos.append(achados)
    if resultado.returncode == 0:
        notificar_mudanca_arquivos()
        blocos.append(f"COMPILADO (exit 0).\n{_texto_executaveis(produzidos)}\n{saida}")
        return "\n\n".join(blocos)
    blocos.append(f"ERRO AO COMPILAR (exit {resultado.returncode}):\n{saida}")
    return "\n\n".join(blocos)

def _bloqueio(plano):
    if plano.get("erro"):
        return f"ERRO: {plano['erro']}"
    if plano.get("faltam"):
        return _texto_faltam(plano)
    return ""

def _interrompido(resultado):
    return getattr(resultado, "status", "") == "parado"

def _correr(pasta, configuracao):
    plano = construir.preparar(pasta, configuracao)
    if plano.get("erro"):
        return f"ERRO: {plano['erro']}"
    if plano.get("faltam"):
        return _texto_faltam(plano)
    produzidos = construir.exe_produzido(plano["pasta_build"], nome=plano["deteccao"].get("projeto", ""))
    if not produzidos:
        return (f"ERRO: nao ha nenhum executavel em '{plano['pasta_build']}'. "
                "Corra primeiro acao='construir'.")
    executavel = os.path.normpath(produzidos[0]["caminho"])
    emit_event("executing", function=f"Abrindo {os.path.basename(executavel)}")
    try:
        registo = iniciar_processo(
            f'"{executavel}"',
            cwd=os.path.dirname(executavel),
            modo="segundo_plano",
            acompanhar=True,
            caminhos_extra=plano["escolha"].get("caminhos"),
        )
    except OSError as e:
        return f"ERRO: nao consegui abrir '{executavel}' ({e})."
    return (f"ABERTO: {executavel} (pid={registo['id']}).\n"
            "A janela do programa aparece no ecra; o card do processo fica no terminal, onde a saida dele "
            "e o botao de parar estao.")

def _depurar(pasta, configuracao, breakpoints, comandos="", alvo=""):
    if comandos and _sessao_viva():
        return _conduzir_depuracao(comandos)
    if comandos and not breakpoints:
        return ("NAO HA SESSAO DE DEPURACAO ABERTA: a ultima fechou (o programa terminou ou o card foi "
                "parado). Abra outra com acao='depurar' e os 'breakpoints'.")
    if depurar.motor_do_alvo(breakpoints, alvo, pasta) == "python":
        return _depurar_python(pasta, breakpoints, comandos, alvo)
    if not depurar.cdb():
        return ("ERRO: nao encontrei o depurador de consola do Windows SDK (cdb.exe), que vem com os "
                "\"Debugging Tools for Windows\". Sem ele nao ha como depurar C++ nesta maquina.")
    plano = construir.preparar(pasta, configuracao)
    falha = _bloqueio(plano)
    if falha:
        return falha
    produzidos = construir.exe_produzido(plano["pasta_build"], nome=plano["deteccao"].get("projeto", ""))
    if not produzidos:
        return (f"ERRO: nao ha nenhum executavel em '{plano['pasta_build']}' para depurar. "
                "Corra primeiro acao='construir'.")
    executavel = os.path.normpath(produzidos[0]["caminho"])
    pontos_de_paragem = depurar.pontos(breakpoints)
    linha = depurar.comando(executavel, [pasta, os.path.dirname(executavel)])
    emit_event("executing", function=f"Depurando {os.path.basename(executavel)}")
    try:
        registo = iniciar_processo(linha, cwd=pasta, modo="card", stdin_pipe=True, acompanhar=True,
                                   caminhos_extra=plano["escolha"].get("caminhos"),
                                   rotulo=f"DEPURADOR: {os.path.basename(executavel)}",
                                   controles=depurar.controles("cpp"))
    except OSError as e:
        return f"ERRO: nao consegui abrir o depurador ({e})."
    depurar.guardar_sessao(registo["id"], executavel)
    registrar_linha_processo(registo["id"], depurar.LINHA_DO_CARD)
    seguir_saida_processo(registo["id"], _vigia_do_depurador(registo["id"]))
    escritos = depurar.preparacao(pontos_de_paragem)
    for escrito in escritos:
        escrever_stdin_processo(registo["id"], escrito)
    texto = _texto_depuracao(registo_id=registo["id"], executavel=executavel,
                             pontos=pontos_de_paragem, escritos=escritos)
    if comandos:
        return texto + "\n\n" + _conduzir_depuracao(comandos)
    return texto

_AVISO_AXIO_NO_DEPURADOR = ("[axio] e o arranque do proprio Axio: nao escreva 'c' aqui - uma segunda "
                            "instancia dele abriria por cima desta. olhe com p/n/w e saia com q")

def _depurar_python(pasta, breakpoints, comandos, alvo=""):
    pontos = depurar.pontos_python(breakpoints, pasta)
    script = pontos[0]["ficheiro"] if pontos else depurar.script_de_arranque(alvo, pasta)
    if not script:
        if pontos:
            return (f"ERRO: nenhum destes pontos aponta para um ficheiro dentro de '{pasta}': "
                    f"{breakpoints}. Abra um ficheiro .py no editor ou indique o ficheiro "
                    f"(ex: app.py:62).")
        return (f"ERRO: nao encontrei nenhum ficheiro .py para arrancar em '{pasta}'. Abra no "
                "editor o ficheiro que quer depurar e carregue outra vez no botao.")
    linha = depurar.comando_python(script, pasta)
    if not linha:
        return f"ERRO: nao consegui montar o depurador para '{script}'."
    emit_event("executing", function=f"Depurando {os.path.basename(script)}")
    try:
        registo = iniciar_processo(linha, cwd=pasta, modo="card", stdin_pipe=True, acompanhar=True,
                                   rotulo=f"DEPURADOR: {os.path.basename(script)}",
                                   controles=depurar.controles("python"))
    except OSError as e:
        return f"ERRO: nao consegui abrir o depurador ({e})."
    depurar.guardar_sessao(registo["id"], script)
    registrar_linha_processo(registo["id"], depurar.LINHA_DO_CARD_PY)
    if _sobe_o_axio(pasta, script):
        registrar_linha_processo(registo["id"], _AVISO_AXIO_NO_DEPURADOR)
    seguir_saida_processo(registo["id"], _vigia_do_depurador(registo["id"]))
    escritos = depurar.preparacao_python(pontos, script)
    for escrito in escritos:
        escrever_stdin_processo(registo["id"], escrito)
    texto = _texto_depuracao_py(registo_id=registo["id"], script=script, pontos=pontos,
                                escritos=escritos,
                                fora=depurar.pontos_de_outra_linguagem(breakpoints, "python"))
    if comandos:
        return texto + "\n\n" + _conduzir_depuracao(comandos)
    return texto

def _sessao_viva():
    """Diz se a sessao de depuracao ainda tem um card a correr, e esquece-a quando morreu."""
    if not depurar.sessao_aberta():
        return False
    reg = estado.get("processos", {}).get(depurar.card_da_sessao()) or {}
    popen = reg.get("popen")
    vivo = popen is not None
    if vivo:
        try:
            vivo = popen.poll() is None
        except Exception:
            vivo = False
    if not vivo:
        depurar.esquecer_sessao()
    return vivo

def abrir_depuracao(pasta, pontos="", arquivo=""):
    """Abre a sessao pedida pela barra do terminal: o ficheiro aberto no editor e os pontos
    marcados na margem. Devolve o card aberto, ou o motivo por que nao abriu."""
    caminho, erro = _pasta(pasta)
    if erro:
        return {"ok": False, "texto": erro}
    if not pontos and _sobe_o_axio(caminho, arquivo):
        return {"ok": False, "texto": (
            "NAO ABRI: este ficheiro arranca o proprio Axio, e uma segunda instancia dele "
            "disputava a porta 5000. Marque uma linha na margem e carregue outra vez - a "
            "sessao abre parada nesse ponto, sem o programa arrancar.")}
    depurar.esquecer_sessao()
    texto = _depurar(caminho, "debug", pontos, "", arquivo)
    card = depurar.card_da_sessao()
    if not card:
        return {"ok": False, "texto": texto}
    return {"ok": True, "id": card, "texto": texto}

def _sobe_o_axio(pasta, arquivo):
    """Diz se este alvo arrancaria o proprio Axio - a mesma trava que a rota do terminal usa."""
    if os.path.normcase(os.path.abspath(pasta)) != os.path.normcase(APP_ROOT):
        return False
    nome = os.path.basename((arquivo or "").replace("\\", "/")).lower()
    if not nome:
        return any(os.path.isfile(os.path.join(pasta, n)) for n in ("app.py", "ax.py"))
    return nome in ("app.py", "ax.py")

def _instalar(pasta, configuracao):
    """Traz do instalador da Qt os componentes que servem os modulos que o projeto pede e faltam."""
    deteccao = detetar.detetar(pasta)
    if deteccao.get("erro"):
        return f"ERRO: {deteccao['erro']}"
    escolha = kits.escolher_kit(deteccao, kits.kits_instalados(deteccao.get("prefixos", ())))
    qt = escolha.get("qt") or {}
    modulos = escolha.get("modulos_em_falta") or []
    if not qt:
        return ("NAO DA PARA INSTALAR SOZINHO: nao ha nenhum kit de Qt escolhido para este projeto, "
                "por isso o que falta instalar primeiro e o proprio Qt.\n" +
                _texto_faltam({"faltam": escolha.get("faltam") or [], "deteccao": deteccao}))
    instalador = qt.get("instalador") or ""
    if not instalador:
        return (f"ERRO: nao encontrei o instalador da Qt nesta maquina, por isso os modulos "
                f"{', '.join(modulos)} tem de ser instalados a mao.")
    if not modulos:
        return (f"NADA A INSTALAR: o kit de Qt {qt['versao']} {qt['kit']} ja traz todos os modulos "
                "que este projeto pede.")
    emit_event("executing", function=f"A consultar o catalogo da Qt ({len(modulos)} modulo(s) em falta)")
    plano = instalar.componentes_para(instalador, qt["versao"], modulos)
    if not plano["ids"]:
        return _texto_sem_componente(modulos, plano["sem_componente"])
    comando = instalar.comando_instalar(instalador, plano["ids"])
    emit_event("executing", function=f"Instalando {', '.join(plano['nomes'])}")
    resultado = correr_como_card(comando, cwd=pasta, timeout=instalar.TIMEOUT_INSTALAR,
                                 caminhos_extra=escolha.get("caminhos"))
    saida = recortar_texto(_texto_do_processo(resultado))
    if _interrompido(resultado):
        return f"INSTALACAO INTERROMPIDA: o card do terminal foi parado.\n{saida}"
    if resultado.returncode != 0:
        linhas = [
            f"NAO INSTALOU (exit {resultado.returncode}): {', '.join(plano['nomes'])}.",
            f"  componentes pedidos: {', '.join(plano['ids'])}",
        ]
        linhas += instalar.explicar(saida)
        return "\n".join(linhas + ["", saida])
    return _texto_instalado(pasta, plano, saida)

def _texto_do_processo(resultado):
    return ((resultado.stdout or "") + (resultado.stderr or "")).strip()

def _texto_instalado(pasta, plano, saida):
    deteccao = detetar.detetar(pasta)
    escolha = kits.escolher_kit(deteccao, kits.kits_instalados(deteccao.get("prefixos", ())))
    restantes = escolha.get("modulos_em_falta") or []
    linhas = [
        f"INSTALADO (exit 0): {', '.join(plano['nomes'])}.",
        f"  componentes: {', '.join(plano['ids'])}",
    ]
    if restantes:
        linhas.append(f"  ATENCAO: o kit escolhido continua sem {', '.join(restantes)}.")
    else:
        linhas.append("  CONFIRMADO: o kit ja traz os modulos que o projeto pede. "
                      "Corra acao='construir' para configurar e compilar.")
    if saida:
        linhas += ["", saida]
    return "\n".join(linhas)

def _texto_sem_componente(modulos, sem_componente):
    if not sem_componente:
        return (f"NADA A INSTALAR: o instalador ja da os componentes destes modulos "
                f"({', '.join(modulos)}) como instalados.")
    return "\n".join([
        "NAO HA COMPONENTE PARA INSTALAR:",
        f"  - o instalador da Qt nao lista nenhum componente para {', '.join(sem_componente)}",
        "",
        "Um modulo que o instalador nao lista a parte faz normalmente parte do proprio kit: nesse caso "
        "o que falta e o kit inteiro, e nao um extra. Veja o que falta com acao='kits'.",
    ])

def _texto_faltam(plano):
    linhas = ["NAO DA PARA CONFIGURAR ESTE PROJETO AINDA:", ""]
    linhas += [f"  - {falta}" for falta in plano["faltam"]]
    deteccao = plano.get("deteccao") or {}
    if deteccao:
        linhas += ["", _texto_deteccao(deteccao)]
    return "\n".join(linhas)

def _texto_plano(plano):
    deteccao = plano["deteccao"]
    escolha = plano["escolha"]
    escrita = plano["escrita"]
    qt = escolha.get("qt") or {}
    linhas = [
        "PLANO ESCOLHIDO PELO AXIO:",
        f"  projeto: {deteccao['rotulo']} '{deteccao.get('projeto') or os.path.basename(deteccao['pasta'])}'"
        + (f" ({', '.join(deteccao['vertentes'])})" if deteccao["vertentes"] else ""),
    ]
    if escolha.get("gerador"):
        linhas.append(
            f"  gerador: {escolha['gerador']}"
            + (f" {escolha['arquitetura']}" if escolha.get("arquitetura") else "")
        )
    if qt:
        linhas.append(f"  Qt: {qt['versao']} {qt['kit']}")
    if escolha.get("cmake"):
        linhas.append(f"  CMake: {escolha['cmake'].get('versao') or escolha['cmake']['caminho']}")
    if escolha.get("glslc"):
        linhas.append("  shaders: glslc encontrado")
    if escrita.get("preset"):
        linhas.append(f"  preset: {escrita['preset']} -> {escrita['arquivo']}")
        linhas.append(f"  pasta de build: {escrita['pasta_build']}")
    linhas += [f"  nota: {nota}" for nota in escolha.get("notas", [])]
    return "\n".join(linhas)

def _texto_deteccao(dados):
    if dados.get("erro"):
        return f"ERRO: {dados['erro']}"
    linhas = [
        f"PROJETO: {dados['rotulo']} ('{dados['pasta']}')",
        f"IDENTIFICADO POR: {', '.join(dados['ficheiros'])}",
    ]
    if dados["tambem"]:
        linhas.append(f"TAMBEM E: {', '.join(dados['tambem'])}")
    if dados["vertentes"]:
        linhas.append(f"VERTENTES: {', '.join(dados['vertentes'])}")
    if dados.get("projeto"):
        linhas.append(f"NOME DO PROJETO: {dados['projeto']}")
    if dados["pacotes"]:
        linhas.append("EXIGE: " + "; ".join(_pacote_texto(p) for p in dados["pacotes"]))
    nomes_de_programas = [", ".join(p["nomes"]) for p in dados["programas"] if p["nomes"]]
    if nomes_de_programas:
        linhas.append("PROGRAMAS QUE TEM DE EXISTIR: " + "; ".join(nomes_de_programas))
    if dados["prefixos"]:
        linhas.append("CAMINHOS QUE O PROPRIO PROJETO INDICA: " + ", ".join(dados["prefixos"]))
    if dados.get("padrao_cxx"):
        linhas.append(f"NORMAS: C++{dados['padrao_cxx']}")
    if dados["tipo"] == "cmake":
        linhas.append(f"CMAKELISTS LIDOS: {dados['cmakelists_lidos']}")
        linhas.append(f"PRESETS DO PROJETO: {'sim' if dados.get('tem_presets') else 'nao'}")
    if dados["pastas_de_build"]:
        linhas.append("PASTAS DE BUILD QUE JA EXISTEM: " + ", ".join(dados["pastas_de_build"]))
    return "\n".join(linhas)

def _pacote_texto(pacote):
    modulos = f" ({', '.join(pacote['componentes'])})" if pacote["componentes"] else ""
    return pacote["nome"] + modulos + ("" if pacote["obrigatorio"] else " [opcional]")

def _texto_kits(pasta):
    deteccao = detetar.detetar(pasta)
    instalado = kits.kits_instalados(deteccao.get("prefixos", ()))
    escolha = kits.escolher_kit(deteccao, instalado)
    linhas = ["NA MAQUINA:"]
    linhas += [f"  Qt {k['versao']} {k['kit']} - {k['caminho']}" for k in instalado["qt"]]
    if not instalado["qt"]:
        linhas.append("  nenhum kit de Qt completo")
    linhas += [
        f"  {v['produto']} {v['versao']} - MSVC {'/'.join(v['ferramentas'])}"
        for v in instalado["msvc"]
    ]
    for chave, rotulo in (("cmake", "CMake"), ("ninja", "Ninja"), ("glslc", "glslc")):
        linhas += [f"  {rotulo} {f.get('versao') or '?'} - {f['caminho']}" for f in instalado[chave]]
    if instalado["vulkan"]["raiz"]:
        linhas.append(f"  Vulkan SDK - {instalado['vulkan']['raiz']}")
    if instalado["vcpkg"]:
        linhas.append(f"  vcpkg - {instalado['vcpkg'][0]}")
    linhas += ["", "ESCOLHIDO PARA ESTE PROJETO:"]
    vazio = {"escrita": {"preset": "", "arquivo": "", "pasta_build": ""}}
    linhas += _texto_plano({"deteccao": deteccao, "escolha": escolha, **vazio}).splitlines()[1:]
    if escolha["faltam"]:
        linhas += ["", "FALTA:"] + [f"  - {falta}" for falta in escolha["faltam"]]
    return "\n".join(linhas)

def _texto_executaveis(produzidos):
    if not produzidos:
        return "Executaveis novos: nenhum (o projeto compilou bibliotecas ou nada mudou)."
    linhas = ["EXECUTAVEIS:"]
    linhas += [f"  {p['caminho']} ({p['mb']} MB)" for p in produzidos[:5]]
    return "\n".join(linhas)

def _texto_depuracao(registo_id, executavel, pontos, escritos):
    blocos = [f"DEPURADOR ABERTO (card {registo_id}): {executavel}",
              "Comandos ja escritos: " + " | ".join(escritos)]
    if pontos:
        blocos.append("Pontos de paragem: " + ", ".join(pontos))
    else:
        blocos.append("Sem pontos de paragem: o programa para na primeira instrucao. "
                      "Marque um com bp `ficheiro.cpp:linha` escrito no campo do terminal com este card "
                      "selecionado.")
    blocos.append("Para conduzir a sessao, selecione o card e escreva no campo do terminal:\n"
                  + depurar.texto_dos_comandos())
    blocos.append("A saida do depurador aparece no card. tool_listar_processos(saida=N) devolve as "
                  "ultimas N linhas dela quando precisar de ler o que o depurador respondeu.")
    blocos.append("Para conduzir a sessao sem sair daqui, chame de novo acao='depurar' com 'comandos' "
                  "(ex: 'k;dv /t /v;?? argc'): os comandos vao para este card e a resposta volta aqui.")
    return "\n\n".join(blocos)

def _texto_depuracao_py(registo_id, script, pontos, escritos, fora):
    marcados = ", ".join(f"{os.path.basename(p['ficheiro'])}:{p['linha']}" for p in pontos)
    blocos = [f"DEPURADOR ABERTO (card {registo_id}): {script}",
              f"Pontos de paragem: {marcados}",
              "Comandos ja escritos: " + " | ".join(escritos)]
    if fora:
        blocos.append("Ficaram de fora, nao sao Python: " + ", ".join(fora))
    blocos.append("Para conduzir a sessao, selecione o card e escreva no campo do terminal:\n"
                  + depurar.texto_dos_comandos_py())
    blocos.append("Atencao a uma diferenca do depurador de C++: aqui o 'p' IMPRIME uma variavel "
                  "(ex: p total) e andar uma linha e o 'n'.")
    blocos.append("A saida do depurador aparece no card. tool_listar_processos(saida=N) devolve as "
                  "ultimas N linhas dela quando precisar de ler o que ele respondeu.")
    blocos.append("Para conduzir a sessao sem sair daqui, chame de novo acao='depurar' com 'comandos' "
                  "(ex: 'w;p total;n'): os comandos vao para este card e a resposta volta aqui.")
    return "\n\n".join(blocos)

def _vigia_do_depurador(registo_id):
    """Vai lendo a saida do depurador a medida que ela chega: escreve no card, em linguagem
    simples, onde a execucao parou - e avisa o editor da linha, para ele a abrir sozinho."""
    janela = []
    visto = {"paragem": {}, "erro": None, "terminou": False}

    def vigia(linha):
        if depurar.card_da_sessao() != registo_id:
            return
        janela.append((linha or "").rstrip())
        del janela[:-depurar.JANELA_DA_LEITURA]
        for texto in depurar.leitura_nova(linha or ""):
            registrar_linha_processo(registo_id, texto)
        _avisar_do_fim(registo_id, visto)
        paragem = depurar.paragem_atual()
        if not paragem:
            _avisar_sem_arranque(registo_id, janela, visto)
            return
        anterior = visto["paragem"]
        if anterior and (anterior["arquivo"], anterior["linha"]) == (paragem["arquivo"],
                                                                     paragem["linha"]):
            return
        visto["paragem"] = paragem
        if not anterior and not paragem["acontecimento"]:
            return
        emit_event("debug_stop", pid=registo_id, arquivo=paragem["arquivo"], linha=paragem["linha"],
                   erro=paragem.get("queda", False))

    return vigia

def _avisar_do_fim(registo_id, visto):
    """Diz ao frontend que o programa chegou ao fim. Andar por um programa que ja terminou nao
    leva a lado nenhum, e os botoes tem de o dizer em vez de ficarem a fingir que andam."""
    terminou = depurar.programa_terminou()
    if terminou == visto.get("terminou", False):
        return
    visto["terminou"] = terminou
    emit_event("debug_fim", pid=registo_id, terminou=terminou)

def _avisar_sem_arranque(registo_id, janela, visto):
    """Um erro de sintaxe impede o ficheiro de arrancar, e quem sabe a linha e o interpretador."""
    alvo = None
    for item in diagnosticos.analisar("\n".join(janela)):
        if item.get("caminho") and item.get("linha"):
            alvo = item
    if not alvo:
        return
    chave = (alvo["caminho"], alvo["linha"])
    if visto.get("erro") == chave:
        return
    visto["erro"] = chave
    registrar_linha_processo(registo_id,
                             f"[axio] nao arrancou: {alvo['codigo']} em {alvo['ficheiro']}:"
                             f"{alvo['linha']}  ->  {alvo['mensagem']}")
    emit_event("debug_stop", pid=registo_id, arquivo=alvo["caminho"], linha=alvo["linha"], erro=True)
    if alvo["codigo"] in _ERROS_QUE_IMPEDEM_O_ARRANQUE:
        _fechar_sessao_sem_arranque(registo_id)

_ERROS_QUE_IMPEDEM_O_ARRANQUE = ("SyntaxError", "IndentationError", "TabError")

def _fechar_sessao_sem_arranque(registo_id):
    """O ficheiro nao chegou a compilar: nao ha sessao para conduzir. Esquece a sessao e fecha o
    card - o 'q' sozinho nao chega, porque o pdb reinicia o programa em vez de sair e o card
    ficava aberto a repetir o mesmo traceback, com botoes que ja nao andam."""
    depurar.esquecer_sessao()
    parar_processo_reg(registo_id, estado.get("processos", {}).get(registo_id) or {})

def _conduzir_depuracao(comandos):
    """Escreve os comandos na sessao aberta e devolve, por comando, o que o depurador respondeu."""
    registo_id = depurar.card_da_sessao()
    lista = depurar.comandos_do_pedido(comandos)
    if not lista:
        return "ERRO: nenhum comando para enviar."
    blocos = [f"DEPURADOR (card {registo_id}): o que respondeu a cada comando"]
    _esperar_resposta(registo_id, _tamanho_da_saida(registo_id), teto=8.0)
    inicial = _tamanho_da_saida(registo_id)
    for comando in lista:
        desde = _tamanho_da_saida(registo_id)
        ok, motivo = escrever_stdin_processo(registo_id, comando)
        if not ok:
            blocos.append(f'  "{comando}" -> NAO ENVIOU: {motivo}')
            break
        resposta = _esperar_resposta(registo_id, desde)
        blocos.append(f"  > {comando}")
        blocos += [f"    {linha}" for linha in resposta] or ["    (sem resposta)"]
    lida = _mostrar_leitura(registo_id, inicial)
    if lida:
        blocos.append("Em linguagem simples:\n" + "\n".join(f"  {linha}" for linha in lida))
    blocos.append("Se um comando deixar o programa a correr, a resposta continua a chegar ao card: as "
                  "ultimas linhas dela saem com tool_listar_processos(saida=N).")
    return "\n".join(blocos)

def _mostrar_leitura(registo_id, desde=0):
    """A leitura em linguagem simples que ja foi para o card desde um ponto. Quem a escreve e o
    vigia do depurador, que le a saida a medida que ela chega - aqui colhe-se o que ele escreveu,
    para nao voltar a interpretar saida ja interpretada (era por aqui que um motivo antigo voltava
    a valer a cada comando)."""
    return [linha for linha in _linhas_do_card(registo_id, desde) if linha.startswith("[axio]")]


def _tamanho_da_saida(registo_id):
    return len((estado.get("processos", {}).get(registo_id) or {}).get("log") or [])

def _linhas_do_card(registo_id, desde=0):
    log = (estado.get("processos", {}).get(registo_id) or {}).get("log") or []
    return [linha.rstrip() for linha in log[desde:]]

def _esperar_resposta(registo_id, desde, teto=20.0, quieto=0.8):
    """Espera a saida do depurador: um comando so esta respondido quando ela cresce e volta a parar."""
    inicio = time.time()
    time.sleep(0.4)
    ultimo = _tamanho_da_saida(registo_id)
    estavel = 0.0
    while time.time() - inicio < teto:
        time.sleep(0.15)
        agora = _tamanho_da_saida(registo_id)
        if agora > ultimo:
            ultimo = agora
            estavel = 0.0
            continue
        estavel += 0.15
        if estavel >= quieto:
            break
    return _linhas_do_card(registo_id, desde)
