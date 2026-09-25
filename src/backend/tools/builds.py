import os
import time

from src.backend.builds import construir, detetar, instalar, kits
from src.backend.services.saida import recortar_texto
from src.backend.state import emit_event, estado, notificar_mudanca_arquivos
from src.backend.tools.process import correr_como_card, iniciar_processo
from src.backend.tools.registry import register


@register(
    "tool_gerir_projeto",
    "Percebe, configura, compila e corre um projeto que NAO e o Axio (Qt/C++, CMake, Visual Studio). "
    "Use quando a pasta aberta - ou a indicada em 'pasta' - tiver CMakeLists.txt/.sln/.pro e a tarefa for "
    "construir, gerar o executavel ou correr o programa. Quem escolhe o kit, o gerador e os modulos e esta "
    "ferramenta: nunca peca ao utilizador para decidir compilador, versao de Qt ou caminhos. "
    "Fluxo: acao='detetar' (o que e o projeto e o que exige), 'kits' (o que esta instalado e o que foi "
    "escolhido), 'preparar' (escolhe o kit, escreve o preset e configura), 'construir' (compila), "
    "'correr' (abre o que ficou compilado) e 'instalar' (traz do instalador da Qt os modulos que o "
    "projeto pede e o kit nao tem - sem uma unica janela). "
    "'construir' e 'correr' fazem o preparo sozinhos. "
    "build corre como card do terminal (saida a vivo, com botao de parar). "
    "Nao serve para ler nem editar codigo (para isso ha as ferramentas de arquivo) nem para construir o "
    "proprio Axio.",
    {
        "acao": {
            "tipo": "STRING",
            "desc": "detetar | kits | preparar | construir | correr | instalar",
            "enum": ["detetar", "kits", "preparar", "construir", "correr", "instalar"],
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
    },
)
def tool_gerir_projeto(acao="detetar", pasta="", configuracao="debug", alvo=""):
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
    if resultado.returncode == 0:
        notificar_mudanca_arquivos()
        return True, f"CONFIGURADO (exit 0).\n{saida}"
    return False, f"ERRO AO CONFIGURAR (exit {resultado.returncode}):\n{saida}"


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
