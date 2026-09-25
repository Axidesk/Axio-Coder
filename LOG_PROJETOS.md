# LOG_PROJETOS — o Axio a ler, construir e correr projetos que não são ele

Log único do trabalho de "qualquer projeto, não só o Axio": perceber que projeto é, escolher
kit, configurar, compilar, correr, e ter as ferramentas de código certas para trabalhar nele
(C++, Python, JS). Escrito para sobreviver a reinícios de conversa: quem perdeu o fio lê isto.

## Objetivo (palavras do utilizador)

"Quero que a nossa interface carregue qualquer projeto de forma inteligente e que sejas TU a
escolher kits, módulos e compiladores — o utilizador leigo não decide nada disto." E também:
"o Axio tem de estar apto a criar do zero e a refatorar o que já existe, seja em C++, Python
ou outra coisa."

## Decisões (tomadas, não estão em aberto)

1. O **DRAFTCAD fica na raiz como cobaia** e não se recria nada: é o projeto real dele
   (CMake + Qt6 + QML + Vulkan + shaders, com biblioteca externa) e as ferramentas aceitam
   `pasta`, logo trabalha-se a partir do Axio sem trocar a pasta aberta.
2. **Não se move nada no disco.** O Qt Creator também não move: a arrumação em
   Headers/Source Files é virtual. Mover a sério partiria os `#include`. O que se adapta é a
   LEITURA da interface, nunca os ficheiros do projeto.
3. **Uma ferramenta** (`tool_gerir_projeto`: detetar/kits/preparar/construir/correr), nunca dez.
   Reusa o runner de processos, os cards e o recorte de saída. Nada disto entra nas instruções
   do sistema — é código que só corre quando é preciso.
4. **Sem botões novos.** Correr o que ficou compilado usa o MESMO mecanismo dos cards.
5. **O Monaco fica.** Inteligência extra, quando vier, é o clangd a ler o
   `compile_commands.json` — não é trocar de editor.
6. **Instalar: autorizado.** O MaintenanceTool dele está autenticado em `D:\Programas\Qt`,
   logo os módulos de Qt saem sem uma única janela.

## O que existe hoje

`src/backend/builds/` — o motor de construir:

| ficheiro | faz |
|---|---|
| `detetar.py` | que projeto é (por evidência no disco), vertentes, o que EXIGE (lendo `find_package`/`find_program`/`CMAKE_PREFIX_PATH`) e os alvos que o `CMakeLists` declara (`add_executable`/`add_library`) |
| `kits.py` | o que está NA máquina (Qt por kit, MSVC por `vswhere`, CMake, Ninja, `glslc`, Vulkan, vcpkg); nota cada kit contra o projeto e nomeia o que falta |
| `presets.py` | escreve o `CMakeUserPresets.json` LOCAL (schema 6/10) — nunca toca no do projeto |
| `construir.py` | decisões e comandos (não executa): `preparar` devolve `precisa_configurar` |
| `cmake_api.py` | a File API do CMake: escreve o pedido, lê a resposta e devolve os alvos com fontes, grupos e flags |
| `msbuild.py` | a árvore como o Visual Studio a vê (`.sln`/`.vcxproj`/`.vcxproj.filters` lidos do texto) e o agrupamento por tipo partilhado |
| `arvore.py` | a árvore agrupada para o explorer (só leitura), os nós virtuais `@arvore/...` e o projeto lido do texto do CMake antes da primeira configuração |
| `instalar.py` | o catálogo do instalador da Qt e o id do componente que traz cada módulo em falta |

`src/backend/tools/builds.py` — `tool_gerir_projeto` (detetar/kits/preparar/construir/correr).
O build corre como **card do terminal** (saída a vivo, botão de parar) e configura sozinho
antes de compilar, como o Qt Creator.

`src/backend/tools/cpp.py` — o leitor de C/C++ (árvore, localização, sintaxe, includes) e
`src/backend/tools/cpp_auditoria.py` — a auditoria do projeto (`tool_auditar_cpp`). São dois
assuntos: um lê UM ficheiro, o outro julga o PROJETO inteiro. (Ver a secção seguinte.)

## Fases

- [x] **Fase 0** (2026-10-06) — construir o DRAFTCAD do zero, pelo nosso caminho, sem abrir o
      Qt Creator. Prova: configure exit 0 (60s) + build exit 0 (225s), `DraftCAD.exe` a abrir
      com Vulkan a 100 FPS; ficheiros do projeto intactos (mtimes de abril).
- [x] **Fase 2** (2026-10-06) — o build como card do terminal, com progresso e paragem; e os
      **cards de sugestão** para um projeto CMake: configurar / compilar / executar o .exe.
      Medido no DRAFTCAD: 4 ms, e o executável escolhido é o `DraftCAD.exe` (não o `dwg2dxf`).
      O botão de build não precisa de botão — é o mesmo mecanismo dos cards que já existiam.
- [x] **Ferramentas C/C++** (2026-10-06) — refatorar, analisar, listar e validar C++ de verdade
      (ver a secção seguinte).
- [x] **Fase 1** (2026-10-06) — CMake File API: alvos, fontes, grupos e flags reais
      (`builds/cmake_api.py`) e a árvore do explorer agrupada por alvo e categoria
      (`builds/arvore.py` + `routes/editor.py`), sem tocar no disco. Provado por HTTP: raiz do
      DRAFTCAD com 4 grupos (DraftCAD, dwg2dxf, doc, dxfrw), `@arvore/DraftCAD` com Fontes/
      Cabeçalhos/Outros, 40 cabeçalhos listados; a raiz do Axio (projeto Python) sai com 0 grupos.
      **Falta:** erros do compilador clicáveis no Monaco.
- [x] **Fase 3** (2026-10-06) — `builds/instalar.py`: lê o catálogo do instalador da Qt (`list` e
      `search`, em XML) e resolve o componente que traz cada módulo em falta, com a allowlist
      aberta aos subcomandos de consulta e instalação. **Bloqueado pela própria Qt** nesta máquina
      — ver a secção "Instalar o que falta".
- [x] **Arrumação da árvore** (2026-10-06) — o explorer passou a ler a arrumação que o projeto
      declara: CMake pela File API, Visual Studio pelos filtros do `.vcxproj.filters` e uma pasta de
      código sem projeto agrupada pelo tipo. Sem azul, sem mover nada. Ver a secção própria.
- [x] **Projeto do ZERO na árvore** (2026-10-06) — um projeto acabado de criar aparece arrumado
      sem nunca ter sido configurado: o `CMakeLists.txt` é lido como texto e o nó do projeto sai
      dali. Ver a secção própria.
- [ ] **Fase 4** — o `.sln` do Tibia: leitura das **flags** por `msbuild -getItem` e o retarget
      2015→2022 numa cópia, provado a compilar.
- [ ] **Fase 5** — clangd (opcional): ir à definição, erro enquanto se escreve.
- [ ] **Criar do zero** — esqueleto de projeto novo (CMake/Qt/Python) escolhido pelo tipo de
      programa que o utilizador pedir.
- [ ] **Captura ao vivo da janela no preview** (WGC, já pendente no plano).

## A arrumação da árvore: quem manda é o projeto (2026-10-06)

O explorer já mostrava os ficheiros do DRAFTCAD arrumados pelo CMake, mas tudo a azul e os grupos
soltos ao lado das pastas reais — e um projeto do **Visual Studio** (o Tibia74) carregava como uma
pasta normal. A pergunta que resolveu as duas coisas foi uma só: **quem sabe onde cada ficheiro fica
é o projeto, nunca a extensão do nome.**

| Projeto | Fonte da arrumação |
| --- | --- |
| CMake | File API (`sourceGroups`) — `builds/cmake_api.py` |
| Visual Studio (`.sln`/`.vcxproj`) | os filtros do `.vcxproj.filters` — `builds/msbuild.py` |
| Pasta de código sem projeto nenhum | agrupada pelo tipo, como o VS faria ao criar um projeto lá |

O `.vcxproj` diz QUE ficheiros pertencem ao projeto e o `.vcxproj.filters` diz em que pasta virtual
cada um fica (Source Files, Header Files, Resource Files) — é a mesma ideia da File API do CMake, e
lê-se do TEXTO, sem o Visual Studio instalado e sem avaliar condições. **Não confundir com a File API
do MSBuild** (`msbuild -getItem`), que avalia o projeto e fica para a Fase 4 (as flags reais).

`builds/arvore.py` passou a ser um motor só: monta uma árvore de nós virtual (prefixo `@arvore`),
escolhe a fonte pelo que a pasta tiver e resolve por caminho. Duas decisões que valem:

- **O que está num grupo sai da lista solta.** `ficheiros_agrupados` diz à rota quais os ficheiros já
  representados dentro de um grupo, e a raiz do explorer deixa de os repetir. É isto que faz uma
  pasta de `.cpp`/`.h` aparecer arrumada em Fontes/Cabeçalhos em vez de 150 ficheiros à solta — e no
  DRAFTCAD tira o `main.qml` e o `qml.qrc` da raiz (ficam em Resources, como no Qt Creator).
- **Nome repetido mostra o caminho.** Dois ficheiros com o mesmo nome no mesmo grupo deixam de ser
  indistinguíveis: o rótulo passa a ser o caminho relativo.

**Cor e ícone.** Os grupos deixaram de ser todos azuis: o nó de projeto tem ícone próprio e cor de
destaque (`--text-branco`), os sub-grupos (Fontes/Cabeçalhos) ficam discretos (`--text-suave`) e as
pastas reais continuam amarelas. Zero CSS azul na árvore.

Medido (2026-10-06):

- **Tibia74:** 1 nó de projeto (`Tibia74`, aplicação) com **81 cabeçalhos** e **72 fontes**;
  `src/account.h` cai no filtro `Header Files`. A pasta `src` sozinha dá os mesmos grupos, sem
  projeto nenhum.
- **DRAFTCAD:** os 4 alvos do CMake (DraftCAD, dwg2dxf, doc, dxfrw); Fontes com 35 ficheiros; e
  `main.qml`/`qml.qrc` fora da raiz.
- **Axio** (projeto Python) e uma pasta sem C/C++: **zero grupos** — a árvore virtual não aparece
  onde não faz sentido.

### A vista de projeto esconde o que o projeto não declara (2026-10-06)

Até aqui a raiz mostrava os grupos **e** a lista solta da pasta: no DRAFTCAD apareciam `libs`,
`shaders`, `src`, `compile_commands.json` e os `LOG_*.md` ao lado dos alvos; no Tibia74 apareciam
`DATA ORIGINAIS`, `Debug`, `Release`, o `.sln` e o `.VC.db`. Nem o Qt Creator nem o Solution Explorer
fazem isso: a **vista de projeto** mostra o que o projeto declara e mais nada. `arvore.tem_projeto`
passou a decidir isto na rota `/api/explorer` — havendo projeto, a raiz fica **só** com ele; sem
projeto, continua a mostrar as pastas e a lista solta (o Axio, com 17 entradas, não mudou).

Os filtros que o projeto **declara** entram mesmo vazios: o `.vcxproj.filters` do Tibia74 declara
`Resource Files` e não tem lá nada, mas o VS mostra o nó — esconder um nó que o projeto pediu daria
uma árvore que não bate com a dele.

O que **não** se copiou, de propósito: `References` e `External Dependencies`. A documentação da
Microsoft di-lo à letra (*"References and External Dependencies are special folders that don't
participate in filtering"*): o `External Dependencies` é o IntelliSense a indexar headers externos
(milhares de ficheiros; a comunidade do VS queixa-se dele e há opção para o esconder), e o Tibia74
não declara uma única `ProjectReference` — um nó `References` nasceria vazio a fingir.

Medido pela rota real (2026-10-06):

| Pasta aberta | Raiz mostra |
| --- | --- |
| DRAFTCAD (CMake) | 1 nó de projeto, e nada mais |
| Tibia74 (`.sln`) | 1 nó (`Tibia74`) — fora o `DATA ORIGINAIS`, `Debug`, `Release`, `.sln`, `.VC.db` |
| Tibia74 / projeto | Fontes, Cabeçalhos, Recursos (o terceiro vazio) |
| Tibia74 / Cabeçalhos | 81 ficheiros |
| `Projects/Tibia74/src` aberta como raiz | Fontes, Cabeçalhos |
| Axio (sem projeto) | 17 entradas, como sempre |

O ícone do nó de projeto trocou: em vez da caixa ("pacote") ficou uma **janela mínima** (retângulo +
barra no topo). **Superado no mesmo dia** — ver a secção seguinte: nenhum nível tem glifo próprio.

### A árvore aninhada e os "Módulos do CMake" (2026-10-06, no mesmo dia)

A pergunta que abriu isto: *"porque é que o nosso fica solto e não com a mesma estrutura do Qt?"* — com
uma captura do Qt Creator ao lado. Ele tinha razão e a causa era simples: cada alvo era um nó de topo,
sem hierarquia nenhuma.

**A hierarquia existe na própria resposta do CMake.** O `codemodel` traz, dentro de cada configuração,
um campo `directories` com `source`, `parentIndex` e `targetIndexes`, e cada alvo diz em que
`directoryIndex` nasce. É daqui que o Qt Creator desenha a vista de projeto — não há nada a adivinhar.
Medido no DRAFTCAD: três diretórios (`.`, `libs/libdxfrw`, `libs/libdxfrw/dwg2dxf`) e quatro alvos com
conteúdo.

O que mudou em `arvore.py`:

- o nó de topo passou a ser **o projeto** (nome do `project()`), e os alvos ficam dentro da pasta onde
  nascem, com os grupos de fontes dentro deles;
- as pastas que o CMake **não** nomeia (o `libs`, acima de `libs/libdxfrw`) são criadas a partir do
  caminho (`_pasta_virtual`) — sem isto a árvore ficava plana na mesma;
- o `CMakeLists.txt` de cada pasta aparece como **primeiro** filho dela;
- `ALL_BUILD`, `ZERO_CHECK` e os `*_autogen` caem sozinhos: ficam sem grupos depois de excluir o que é
  `gerado`;
- o `path` dos nós virtuais passou de **nome** para **índice** (`@arvore/0/2`). Armadilha medida: o
  `entradas_raiz` ficou a montar o caminho pelo nome e a árvore abria **vazia** — só a prova pela rota
  é que o apanhou.

**Os "Módulos do CMake".** Também não são invenção: o CMake considera os ficheiros dele parte do
projeto e lista-os no objeto `cmakeFiles` (todos os que leu na configuração), com `isCMake` a dizer
quais vêm da instalação. Medido: **1007 inputs**, dos quais **2** são do projeto (`libdxfrw.pc.in` e
`libdxfrwConfig.cmake`). O nó fica com os do projeto que terminam em `.cmake` / `.cmake.in` / `.pc.in`;
os da instalação ficam de fora, ou a lista teria milhares. Fonte: o próprio mantenedor do Qt Creator
(Tobias Hunger, lista qt-creator) — *"CMake does consider its own files as part of a project. That is
why you see them"*.

**Medido pela rota real** (processo novo, `/api/explorer` no DRAFTCAD):

```
DraftCAD [projeto]
    CMakeLists.txt
    DraftCAD [alvo aplicação]   -> Fontes 35, Cabeçalhos 40, Outros 2 (qml.qrc, main.qml)
    libs [pasta]
        libdxfrw [pasta]
            CMakeLists.txt
            doc [alvo]          -> Outros 1
            dxfrw [alvo biblioteca estática] -> Fontes 20, Cabeçalhos 19
            dwg2dxf [pasta]
                CMakeLists.txt
                dwg2dxf [alvo aplicação] -> Fontes 2, Cabeçalhos 2
    Módulos do CMake
        libs/libdxfrw -> libdxfrw.pc.in
                   cmake -> libdxfrwConfig.cmake
```

Tibia74 (`.sln`): `Tibia74 [projeto]` → Fontes (72), Cabeçalhos (81), Recursos (vazio).
`Projects/Tibia74/src` sem projeto: Fontes (72), Cabeçalhos (80). Axio (Python): 17 entradas, zero
grupos.

**O que ficou de fora, e digo-o:** o grupo que o CMake deixa **sem nome** (no DRAFTCAD, o `qml.qrc` e o
`main.qml`) sai como "Outros"; o Qt Creator chama-lhe "Resources" porque é **ele** que classifica
ficheiros `.qrc`/`.qml` — o CMake não o faz. E o `dwg2dxf` fica em pasta própria com o alvo dentro (a
pasta tem o seu `CMakeLists.txt`); nas capturas do Qt o nó aparece colapsado, logo não se vê se ele
aninha ou não.

**Ícones.** O nó de projeto deixou de ter glifo próprio: todos os níveis usam a **mesma pasta** e
separam-se por **cor e peso** (`workspace.css`) — projeto em `--text-branco` a negrito, alvo no azul de
ação, pasta em `--text-corpo`, grupo em `--text-suave`. `state.ICON_PROJETO` foi **removido** (a caixa
3D e o retângulo com barra liam-se como "pacote", que foi a queixa). Ficou registado nas preferências.

Fontes: [cmake-file-api(7)](https://cmake.org/cmake/help/latest/manual/cmake-file-api.7.html) e
[vcxproj.filters files](https://learn.microsoft.com/en-us/cpp/build/reference/vcxproj-filters-files).

## Projeto do zero: a árvore antes da primeira configuração (2026-10-06)

Pergunta que abriu isto: *"num projeto do zero, se eu decidir criar em C++, a doc atualiza
automaticamente para a estrutura nova?"* Medido antes de mexer (pasta limpa, `CMakeLists.txt` +
`src/*.cpp/.h`, nenhum `build/`): **a raiz não mostrava nada**. A File API só existe depois de o
CMake correr, e o nó de projeto era todo ele File API — logo, entre criar o projeto e o configurar,
o explorer não anunciava projeto nenhum. As pastas (`src/`) já agrupavam bem por tipo; faltava o nó.

Agora `arvore._projeto_por_texto` cobre esse intervalo, e só esse:

- o **nome** e o **tipo** saem do texto do `CMakeLists.txt` — `project(Nome)` e `add_executable` /
  `add_library STATIC|SHARED|MODULE|INTERFACE` (novo: `detetar._alvos_do_texto`);
- os **ficheiros** são os de código sob a pasta, fora das pastas de build e das escondidas,
  agrupados por tipo (Fontes / Cabeçalhos / Recursos / Outros);
- **só com UM alvo.** Com vários, os ficheiros de alvos diferentes apareceriam juntos e o nó mentiria
  sobre a que alvo pertence cada um — nesse caso não há nó de projeto e fica a pasta normal, até o
  CMake responder pela File API (que é quem sabe a pertença real). Um alvo por variável
  (`add_executable(${NOME}`) também não é nomeado: o nome só existe depois de o CMake avaliar.

O nó da File API continua a mandar assim que existe: o texto é o intervalo, não a substituição.

**Armadilha medida — o cache da árvore.** `_marca` só olhava a mtime da pasta consultada e dos
ficheiros de projeto, e a arrumação por texto lê o que está DENTRO das subpastas: criar
`src/nucleo/novo.cpp` não mudava a mtime da raiz, a chave do cache continuava igual e a árvore só
mudava ao navegar para fora e voltar. Agora a marca leva as mtimes das pastas até 3 níveis
(`PROFUNDIDADE_DA_MARCA`), provado: criar um ficheiro numa subpasta passa a mudar a árvore na hora.

**Ordem dos grupos.** O caminho CMake mostrava Fontes antes de Cabeçalhos e o caminho Visual
Studio ao contrário (ordem alfabética), o que fazia a mesma árvore mudar de aspecto conforme o
projeto. Uniformizado: Fontes → Cabeçalhos → Recursos → Outros nos dois.

**O que se ganhou de graça:** um `CMakeLists.txt` sozinho já não aparece dentro de um grupo "Outros"
(pasta de código sem projeto agrupava tudo o que estivesse lá, manifestos incluídos). Agora os
ficheiros sem tipo conhecido ficam na lista solta da pasta, onde sempre estiveram visíveis.

Prova (2026-10-06, pela rota real `/api/explorer`, com `pasta_raiz` a apontar a uma pasta temporária):

| Cenário | Resultado |
| --- | --- |
| projeto do zero, 1 alvo, sem `build/` | raiz = `MinhaApp` (aplicação) + `src` + `CMakeLists.txt`; Fontes e Cabeçalhos certos, incluindo ficheiros de subpasta |
| criar `src/nucleo/novo.cpp` | a árvore muda sem navegar |
| 2 alvos, ou alvo por variável | sem nó de projeto (pasta normal), como desenhado |
| `add_library STATIC/SHARED/sem tipo` | biblioteca estática / partilhada / biblioteca |
| `build/` com ficheiros gerados | os gerados não entram |
| DRAFTCAD, Tibia74, pasta `src` do Tibia, Axio | sem regressão (4 alvos / 81+72 / grupos por tipo / zero nós) |

## Ferramentas C/C++ (2026-10-06)

Nasceram do buraco medido: o motor verbatim existia para Python e JavaScript e, num `.cpp` a
sério (`DRAFTCAD/src/CameraManager.cpp`), recusava com *"Função 'applyPan' não encontrada no
JavaScript"* — um erro que não dizia nada sobre o ficheiro.

A base é o **tree-sitter-cpp**, que já estava instalado e já era usado pelo índice de código
(`tools/code_index.py`) — não entrou motor nem dependência novos. A árvore dá o que a regex não
dá: assinatura real, scope do método (`Classe::metodo`) e a diferença entre **declarar** (sem
corpo) e **definir**, que é o que decide se um movimento pode ser verbatim.

Em `src/backend/tools/cpp.py` (leitor, sem `@register` — é módulo de apoio):

- `entidades` / `mapa` — classes, métodos, funções, campos e protótipos com linha e assinatura
- `encontrar` / `localizar` / `escopo_de` — localizar a definição; recusa declarações sem corpo
  e nomes ambíguos (diz quais são)
- `header_da_classe` — que cabeçalho declara a classe (para o include do destino)
- `erros_de_sintaxe` / `erros_de_texto` — validação pela árvore
- `partir` / `colher` / `mencoes_por_classe` — a árvore e as entidades, para quem precisa de
  ler o ficheiro uma só vez (a auditoria lê os 77 ficheiros e cruza-os)

Em `src/backend/tools/cpp_auditoria.py` (a ferramenta):

- `tool_auditar_cpp` — cruza o que cada ficheiro declara com o que define

Ligado ao que já existia (reuso, não duplicação):

- `tool_mapear_codigo` passa a ler C/C++ pela árvore (o `.cpp` já não cai num regex de "C-like")
- `tool_validar_sintaxe` cobre C/C++ (e valida automaticamente cada edição a `.cpp`/`.h`)
- `tool_mover_funcao_verbatim` e `tool_remover_funcao` ganharam o localizador C++, e o mover
  acrescenta o `#include` do cabeçalho da classe no destino quando ele falta
- `tool_mover_bloco_verbatim` e `tool_mover_arquivo_binario` já eram agnósticos de linguagem

Armadilhas que custaram voltas (registadas para não voltarem):

- O campo `declarator` **nem sempre existe**: em `MaterialManager& MaterialManager::instance()`
  o `reference_declarator` traz o `&` anónimo e o `function_declarator` como filho simples.
  Seguir só o campo perdia toda a função que devolve referência ou ponteiro.
- Um macro **sem `;`** (`Q_OBJECT`) cola a declaração seguinte dentro dele e traz um `ERROR`:
  por isso é que o construtor desaparecia da classe.
- Construtor e destruidor dentro de uma classe são `declaration` (não `field_declaration`).
- `signals:` não tem corpo escrito por ninguém (gera-o o moc) → não conta como "sem definição".
- Overloads (incluindo `const`) e blocos `#if 0` davam falsos "definido duas vezes".
- O tree-sitter não conhece `Q_OBJECT`, `signals:`, `emit` — sem filtrar isso, todo cabeçalho Qt
  saía marcado como quebrado.

Armadilhas da File API (medidas no CMake 4.0.2, custaram voltas):

- No objeto `codemodel` os `projects`, `directories` e `targets` vivem **dentro de cada
  configuração**, não na raiz — ler a raiz dá `KeyError: 'projects'`.
- Os ficheiros gerados na árvore de build ficam **dentro** da pasta do projeto quando o build é
  in-tree (`build/axio-debug/...`), logo o caminho relativo não os distingue de ficheiros do
  projeto: quem exclui é a pasta de build (absoluta) ou o `isGenerated`.
- O `sourceGroups` do próprio CMake já traz os nomes ("Source Files", "Header Files", "CMake Rules"
  e um grupo sem nome onde caem o `qml.qrc` e o `main.qml`) — não é preciso adivinhar por extensão.
- Ordenar os grupos por nome na rota destruía a ordem "executável primeiro" calculada em `arvore.py`:
  os grupos passam a ser pré-colados depois de ordenar as entradas do disco.

Prova medida no DRAFTCAD (77 ficheiros, 110 classes): a auditoria desceu de **191 apontamentos
para 1** — e esse 1 é real (`stb_truetype.h` inclui `stb_rect_pack.h`, que não está no projeto).
Refactor provado num **cópia descartável** dentro do projeto (nunca nos ficheiros dele):
mover para destino novo escreve o `#include` e o corpo verbatim; mover de volta não duplica o
include; função inline e protótipo sem corpo são recusados com o motivo; remover apaga o range
certo e a sintaxe fica limpa.

## Instalar o que falta (2026-10-06) — o que a Qt permite e o que não

A CLI do instalador da Qt (https://doc.qt.io/qt-6/get-and-install-qt-cli.html) responde em **XML**:
`list` dá o que está instalado e `search --type package` dá o catálogo; a instalação sem janelas é
`--accept-licenses --default-answer --confirm-command install <ids>`. Os ids **nunca** são escritos
de memória: só se usa um id que o próprio instalador listou.

Medições que valem (nesta máquina, 2026-10-06):

- O código da versão nos ids concatena major+minor+patch **sem zeros**: 6.10.0 → `6100`,
  6.8.2 → `682`, 6.5.3 → `653`. Confirmado contra os 2079 pacotes do catálogo.
- Os addons aparecem no catálogo a nível de MÓDULO (`qt.qt6.6100.addons.qtwebsockets`), enquanto o
  `list` dos instalados os mostra com o kit no fim (`...qtwebsockets.win64_msvc2022_64`).
- **O catálogo NÃO prova que se instala.** O `search` lista 2079 pacotes, mas o `install` recusa
  selecionar componentes que não estejam já instalados: `qt.qt6.6100.addons.qtwebsockets` → *not
  found*; `qt.qt6.6120.win64_msvc2022_64` (kit base de uma versão corrente, não instalado) → *not
  found*; `qt.qt6.6100.addons.qtcharts.win64_msvc2022_64` (já instalado) → resolve. O
  `--accept-obligations` não muda nada e o `check-updates` só oferece o Qt Creator 20 (730 MB).
- Por isso a ferramenta **não diz "instalei"** quando não instalou: cita o instalador ("archive of
  historical versions", "No components available with the current selection") em vez de inventar a
  causa. O caminho seguinte é atualizar o instalador, que é uma mudança grande e não se faz sozinho.
- A allowlist ganhou os instaladores da Qt mas SÓ nos subcomandos de consulta e instalação:
  `remove` e `purge` são recusados — não se desinstala software do utilizador sem ele pedir.
- A sondagem que mede isto sem instalar nada: correr o `install` **sem** `--confirm-command`; se o
  componente existir, o instalador mostra o resumo e aborta (exit 3) em vez de instalar.

## Qualquer linguagem, não só C++ (2026-10-06)

Escolher um kit só faz sentido para projetos que se COMPILAM. O `kits.py` tratava qualquer pasta
como se fosse C++: pedir os kits do próprio Axio (projeto Python) respondia
*"gerador: Visual Studio 17 2022 x64"* — a resposta certa para o projeto errado.

Agora a decisão passa pelo TIPO detetado:

- `_TIPOS_COMPILADOS` (`cmake`, `msbuild`, `qmake`, `make`) seguem pelo caminho C++ de sempre.
- `python`, `npm`, `cargo` e `go` saem por `_kit_sem_compilador`: dizem sobre que ferramenta o
  projeto corre e se ela está no PATH, sem inventar gerador nenhum.
- Pasta **sem projeto conhecido** deixa de anunciar um gerador e passa a nomear o que falta
  (*"não tem nenhum ficheiro de projeto conhecido...: não há kit a escolher"*).

Medido (2026-10-06): Axio (python) -> gerador vazio + *"corre sobre o interpretador Python,
encontrado em .venv\\Scripts\\python.EXE"*; DRAFTCAD (cmake) -> `Visual Studio 17 2022 x64`
(sem regressão); `C:\\` e `src/frontend` (desconhecidos) -> *"não há kit a escolher"*.

A regra que fica: **a linguagem do projeto decide a ferramenta; o C++ é um caso, não o default.**

## Criar do zero: quem escolhe a stack (regra permanente)

Quando o projeto é NOVO não há nada para detetar — há para decidir. A ordem é:

1. **O tipo de programa decide a família** (serviço/API, app de desktop, CLI, ferramenta web,
   jogo, modelação...), nunca o hábito nem a linguagem da tarefa anterior.
2. **A documentação OFICIAL decide a escolha dentro da família** (pesquisa-primeiro): a versão
   vem da doc, nunca da memória do modelo.
3. **O que já existe na máquina ganha** a uma instalação nova, quando serve.
4. **Nada disto vira instrução do sistema**: é código que corre quando é preciso, para não
   poluir o contexto de quem está a trabalhar numa linguagem que não precisa dele.

## As instruções do sistema estavam engessadas em web/Python (revistas a 2026-10-06)

As regras que o agente recebe em TODAS as rodadas vivem em `src/backend/ai/instructions.py` (e a
descrição de `tool_planejar_arquitetura` em `tools/plan.py`). Estavam escritas como se todo o
projeto fosse uma aplicação Python/JS — foi preciso medir para ver o quanto:

- `0.0` mandava criar **sempre** um venv do projeto antes de instalar dependências (e dizia
  literalmente *"Não use cmake (compile) em projetos do Qt Creator"*, o oposto do que agora existe).
- `ESTRUTURA ENXUTA` obrigava a dividir o código em `backend/` + `frontend/` — divisão que não
  existe numa app nativa.
- `5. COMPILAÇÃO` dizia que num projeto do Qt Creator **não era preciso compilar**.
- `4.1`/`4.2`/`4.4` falavam só de `requirements.txt`/`package.json`, pip e npm.
- Nenhuma linha dizia que a **linguagem** de um projeto novo é escolha do agente: dava a entender,
  pelo resto do texto, que o produto era Python.

O que passou a valer (e a linguagem em que se escreve):

1. **Linguagem pelo problema, nunca pelo hábito.** Nativo/tempo real -> C++ ou Rust; serviço, dados
   e automação -> Python; browser -> HTML/JS ou o framework que a doc eleger; app nativa com
   interface -> C++/Qt. **Python não é a resposta por omissão** e o facto de as ferramentas do Axio
   serem em Python não decide o projeto do utilizador.
2. **Versões: sempre a ESTÁVEL mais recente publicada, e só essa** — vale para pacote, biblioteca,
   runtime, SDK, compilador, kit, ferramenta de build e programa auxiliar. `alpha/beta/rc/preview/
   nightly/canary/dev` **não entram** (obrigam a retrabalho quando sai a estável); se só uma
   pré-lançamento resolver, pergunta-se antes.
3. **Ambiente isolado por ecossistema** (nunca sujar o ambiente do Axio): Python -> venv do projeto;
   Node -> npm na pasta do projeto; C/C++ -> o diretório de build, escolhido pelo `tool_gerir_projeto`;
   Rust/Go -> resolvem-no sozinhos. Só projeto estático é que não cria ambiente nenhum.
4. **`4.5 PROJETO NATIVO`** (regra nova): nomeia `tool_gerir_projeto` (detetar/kits/preparar/
   construir/correr/instalar), as ferramentas C/C++ por árvore e o `tool_auditar_cpp` — e diz
   explicitamente que **num projeto Python/Node/Rust/Go nenhuma delas se chama**.
5. **`5. COMPILAÇÃO E EXECUÇÃO`**: compilar é `tool_gerir_projeto(acao='construir')` (card do
   terminal, com progresso e parar) e correr é `acao='correr'`; proibido pedir ao utilizador para
   compilar à mão ou dizer que "não precisa".

### O furo que isto destapou: a stack do contexto mentia

Ao reler as regras apareceu um enviesamento pior, este no código: `_detectar_stack`
(`tools/projeto_info.py`) começava **sempre** por `Python {versão do interpretador}` — abrir o
DRAFTCAD dava ao modelo a stack *"Python 3.14.2"* num projeto CMake/Qt/Vulkan.

Agora a stack sai do que o PROJETO declara (marcadores: `CMakeLists.txt`, `package.json`,
`Cargo.toml`, `go.mod`, `pyproject.toml`, `.sln`/`.csproj`...) com detalhe nativo (Qt, standard de
C++ pelo `CXX_STANDARD`/`cxx_std_`, Node por `engines`/`.nvmrc`), e o interpretador do Axio só entra
se o projeto for mesmo Python. Sem marcador nenhum, decide a extensão dominante dos ficheiros.

Medido (2026-10-06): Axio -> `Python 3.14.2, JavaScript/Node`; DRAFTCAD -> `C++ (CMake), Qt 6, C++17`;
pasta solta de `.cpp`/`.h` -> `C++ (pela extensao dos ficheiros)`; projeto Rust -> `Rust`; projeto Go
-> `Go` (com as dependências lidas do `Cargo.toml` e do `go.mod`).

Pelo caminho, os **manifestos nativos passaram a ser lidos** (`tools/dependencias.py`:
`_manifestos_nativos` + vcpkg/Conan/Cargo/Go): `find_package` e `pkg_check_modules` do `CMakeLists.txt`
são as dependências de um projeto CMake, e o retrato dizia "sem manifestos detectados" a um projeto
CMake inteiro. DRAFTCAD -> `CMakeLists.txt (2 pacotes CMake): Qt6, Vulkan`. É o que torna verdadeira
a regra 4.1 (o manifesto é a fonte canónica da stack) para projetos que não são Python.

## O que falta (medido, não suposto)

- **Erros do compilador clicáveis** no Monaco: a outra metade da Fase 1.
- **Instalar componentes da Qt** está bloqueado pelo próprio instalador nesta máquina (ver a secção
  "Instalar o que falta"): o passo seguinte é atualizá-lo (`MaintenanceTool update`), com o custo dito.
- **Pasta solta de `.cpp`/`.h`** sem ficheiro de projeto: o explorer já a arruma por tipo (Fontes /
  Cabeçalhos) e o retrato do contexto identifica-a (`C++ (pela extensao dos ficheiros)`). O que
  falta é o **motor de build**: `detetar.py` cai em "desconhecido" (os tipos são
  cmake/msbuild/qmake/python/npm/cargo/go/make), logo não há caminho de compilação para só código.
- **Dependências nativas atrasadas**: o bloco de manutenção do prompt mede PyPI/npm; vcpkg, Conan,
  NuGet e Cargo ainda não têm verificação de "está atrás do registo" (o manifesto já é lido, a
  versão publicada ainda não é comparada).

- **Erros do MSBuild/MSVC** chegam (ao card e a mim) mas ainda não são clicáveis no Monaco. A
  saída do MSBuild é **localizada em português** ("Arquivo de projeto não existe"); só os
  códigos ficam em inglês (`MSB1009`).
- **`.pro`** (qmake) não tem leitor: sem API oficial de fontes, a resposta da ferramenta di-lo em vez
  de falhar em silêncio. O `.sln` já é lido para a árvore; falta-o para as flags.
- **`.qmake`** (`.pro`) não tem API oficial de fontes.
- **Motor de jogo** (Unreal/Unity) fica de fora: tem pipeline próprio.

## O que NÃO se faz

- Não se reorganizam as pastas do projeto do utilizador (ver decisão 2).
- Não se misturam ferramentas: a responsabilidade de construir é uma, a de ler código é outra.
- Não se instala nada sem autorização quando a decisão for grande — módulos pequenos, segue.

## Fontes

- CMake File API — https://cmake.org/cmake/help/latest/manual/cmake-file-api.7.html
- CMake Presets — https://cmake.org/cmake/help/latest/manual/cmake-presets.7.html
- Qt: instalar e gerir por linha de comandos — https://doc.qt.io/qt-6/get-and-install-qt-cli.html
- MSBuild: avaliar itens e propriedades (`-getItem`) — https://learn.microsoft.com/en-us/visualstudio/msbuild/evaluate-items-and-properties
- Ficheiros de filtros do Visual C++ (`.vcxproj.filters`) — https://learn.microsoft.com/en-us/cpp/build/reference/vcxproj-filters-files
- Esquema dos ficheiros de projeto do MSBuild — https://learn.microsoft.com/en-us/visualstudio/msbuild/msbuild-project-file-schema-reference
- Portar/retarget de projetos Visual C++ — https://learn.microsoft.com/en-us/cpp/porting/overview-of-potential-upgrade-issues-visual-cpp
