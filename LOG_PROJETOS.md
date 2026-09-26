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
      **Feito (2026-10-06, depois):** erros do compilador clicáveis — ver a secção própria.
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
- [ ] **Fase 4** — as **flags de qualquer `.sln`** por `msbuild -getItem`, e o retarget de um
      projeto antigo numa cópia. O Tibia74 é só o caso que mostrou a falta; a peça é do leitor de
      MSBuild (`builds/msbuild.py`), que já serve qualquer `.sln`. Nota de necessidade: num projeto
      CMake isto **não falta** — as flags dele vivem no preset e no `compile_commands.json`; só um
      projeto MSBuild nativo precisa do `-getItem` para saber o compilador e as definições.
- [ ] **Fase 5** — clangd (opcional): ir à definição, erro enquanto se escreve.
- [ ] **Fase 6** — depurador, com o mínimo de interface nova: C++ pelo `cdb` que JÁ está na máquina,
      depois o Monaco ligado ao motor, e Python/JS pelos adaptadores oficiais. Ver a secção própria
      ("O depurador e o resto do que um expert usa").
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

## Quem manda na arrumação é o projeto — e não há só CMake e sln (2026-10-06)

Pergunta do utilizador: *"isso só serve para cmake? o cmake é do Qt Creator? todo código cpp e h tem
necessariamente cmake e sln?"* — vale a pena ficar escrito, porque a resposta é o que decide se a
árvore é escalável ou feita à medida de dois programas.

**Medido na documentação oficial** (https://doc.qt.io/qtcreator/creator-reference-build-systems.html
e https://doc.qt.io/qt-6/topics-app-development.html): *"Qt Creator supports CMake, qmake, Qbs,
Autotools, Nimble, Meson, and IncrediBuild projects"*. Ou seja:

- O **CMake não é do Qt Creator**. É um gerador de build independente (Kitware) que o Qt Creator, o
  Visual Studio, o CLion e mais meia dúzia sabem ler. O `.sln`/`.vcxproj` é **MSBuild** (Microsoft) e
  não é mais "do C++" do que o CMake. Nenhum dos dois é intrínseco da linguagem.
- **Não existe UM formato de projeto.** Cada família declara o que quer, e quem não declara nada é
  agrupado pela extensão. A lista real: CMake (`CMakeLists.txt`), MSBuild (`.sln`/`.vcxproj`/
  `.vcxproj.filters`), qmake (`.pro`/`.pri`), Meson (`meson.build`), Autotools (`configure.ac`/
  `Makefile.am`), SCons (`SConstruct`), Premake (`premake5.lua`), GN (`BUILD.gn`), Bazel (`BUILD`),
  Xcode (`project.pbxproj`), Make (`Makefile`) e Ninja (`build.ninja`).

**O contrato do Axio** (é por isto que não engessa): um motor de árvore (`builds/arvore.py`) +
**um leitor por família** (`builds/cmake_api.py`, `builds/msbuild.py`) + **o agrupamento por extensão
como rede** para quem não declara nada. Um leitor devolve sempre a mesma forma —
`projetos: [{nome, grupos: [{nome, ficheiros}]}]` — e a visualização (ícones, cores, guias) nunca se
toca. Família nova = um ficheiro, não uma árvore nova.

Implementado a 2026-10-06: CMake pela File API, CMake pelo texto (antes da primeira configuração),
MSBuild pelos filtros declarados, e o agrupamento por extensão (que é o que o Visual Studio faria ao
criar um projeto numa pasta de código). O `detetar.py` já reconhece `cmake`, `msbuild`, `qmake` e
`make`; um `.pro` cai hoje na rede (Fontes/Cabeçalhos) até haver leitor próprio — é o próximo, quando
aparecer um projeto qmake a sério.

### A árvore desenha as guias como o Qt Creator

O explorer usava um `border-left` no contentor: uma linha contínua que atravessava tudo e nenhum
traço a ligar cada ficheiro à pasta-mãe. Agora desenha `|`, `|-` e o cotovelo `L` como o painel de
informações do projeto, com a mesma técnica — e é a técnica padrão da web para isto, porque **não há
especificação de CSS para ligações de árvore**: fio vertical num pseudo-elemento, traço horizontal
noutro, e o cotovelo desenhado pelo último filho.

Duas decisões que a medição impôs:

- **Percentagens, nunca pixeis fixos.** A linha mede 25.5px de verdade (fonte de 13px + 6px de
  padding), não os ~22 que se supõem. Com `top: 50%` no traço e `height: 50%` no cotovelo, os dois
  encontram-se exactamente no meio da linha, seja qual for a altura. O painel de projeto, que fixa
  `top: 11px`, acerta por sorte da altura da linha dele.
- **O fio alinha com o centro do ícone da pasta-mãe** (x=24 medido: padding de 8 + ícone de 16),
  nunca com a borda dela — é o que faz a linha parecer que "desce" do ícone.

Medido com `tool_medir_pintura` (cena com o caso difícil: o último filho é um grupo com filhos):
fio de 1px `#444444` (`--border-suave`), traço de 8px a acabar no início do ícone, cotovelo de
12.75px no último filho, e os traços por cima do fundo de hover.

### O ícone do nó de projeto: pasta, e a correcção de uma promessa

O nó de projeto andou com uma **caixa 3D que se lia como "pacote"** (`ICON_PROJETO`, commit
`32791c3`) — e a rodada que a introduziu descreveu-a ao utilizador como "uma janela mínima". Não
era: era o pacote, e o utilizador viu-o e disse que não gostou. O commit seguinte (`bd0771d`)
apagou a constante por acidente, e o que ficou foi o desenho certo pela regra dele: **pasta em
`--text-branco` a negrito** (o nível separa-se por COR e PESO, nunca por um glifo diferente). Fica
escrito para não voltar a nascer um pacote em nome de uma "janela".

### O que os nossos presets valem lá fora — e porque não declaram mais do que usam (2026-10-06)

Pergunta do utilizador: *"se eu carregar o cmake lá no Visual, era só clicar em compilar? e a pasta
módulos do cmake, quando for ninja muda de nome?"*

**O nó dos módulos só existe onde há CMake a lê-lo** — medido: DRAFTCAD (146 nós) tem 1
`Módulos do CMake`; Tibia74 (MSBuild, 157 nós) tem **zero**; a raiz do Axio, zero. O nome não é um
rótulo fixo do explorer: é emitido pelo módulo que montou aquela árvore, logo uma família nova emite
o nome dela. E o Ninja não é família nenhuma: é o **executor que o CMake chama** (`cmake --build`
corre o gerador — make, mingw32-make, nmake ou ninja, diz a doc do Qt), portanto um projeto Ninja
**é** um projeto CMake e o nó continua a chamar-se Módulos do CMake, com razão.

**Quem lê o que escrevemos:** o `CMakeUserPresets.json` é lido pelo Visual Studio e pelo Qt Creator,
os dois, mais o CMake pela linha de comandos — a doc da Microsoft di-lo à letra (*"configure, build,
and test options and share them with others: CMakePresets.json and CMakeUserPresets.json... Both
files are supported in Visual Studio 2019 version 16.10 or later"*) e a do Qt também. Como o
`CMakeUserPresets` inclui sozinho o `CMakePresets` do projeto, o que escrevemos nunca colide com
quem o escreveu.

**A versão declarada era 6 e passou a 3** — correcção, não gosto. A doc do CMake diz o que cada
versão acrescenta (a 6 só acrescenta `packagePresets` e `workflowPresets`, que não usamos; a 2 trouxe
os `buildPresets`; a 3 os `condition`/`toolchainFile`/`installDir`), e a da Microsoft diz até que
versão cada VS lê. Declarar acima do que se usa não dá nada e tira compatibilidade: um VS que não
conheça a versão **ignora o ficheiro todo** e volta aos presets de omissão (*"If either
CMakePresets.json or CMakeUserPresets.json is invalid, Visual Studio will fall back on its default
behavior and show only the default Configure Presets"*). Ficheiro que só tem presets nossos passa a
declarar a nossa versão; ficheiro com presets de outro dono, `include` ou test/package/workflow fica
com a versão que tem (baixá-la podia invalidar o que não é nosso). Provado em 4 cenários: ficheiro
novo -> 3; reescrito -> 3; com preset alheio -> 6 intacto; com `testPresets` -> 6 intacto.

**Medido nesta máquina:** o preset que o Axio escreveu para o DRAFTCAD usa o gerador *Visual Studio
17 2022*, x64, com `CMAKE_PREFIX_PATH` para o Qt 6.10.0 — e o build já produziu, em
`DRAFTCAD/build/axio-debug/`, um `DraftCAD.sln` com os `.vcxproj` e `.filters` (2026-09-25). O `.sln`
existe, mas **nasce do CMake**, dentro da pasta de build; nunca é escrito à mão ao lado do
`CMakeLists.txt`.

**O que viaja e o que não viaja:** o `CMakeLists.txt` (alvos, standard, defines, includes) e os
presets viajam; o **compilador/kit não** — vive na máquina, e é por isso que o mesmo projeto abre no
VS e no Qt Creator sem configuração nenhuma *nesta* máquina e precisaria de kit noutra.

Cuidado a ter com o Qt Creator: ele importa presets **na primeira abertura** do projeto, quando não
existe `CMakeLists.txt.user` (*"You can import the presets the first time you open a project, when no
CMakeLists.txt.user file exists or you have disabled all kits"*); se o `.user` já existir, o caminho
é **Build > Reload CMake Presets**. O DRAFTCAD não tem `.user` na pasta — a importação passa.

Fontes: [cmake-presets(7)](https://cmake.org/cmake/help/latest/manual/cmake-presets.7.html);
[CMake Presets no Visual Studio](https://learn.microsoft.com/en-us/cpp/build/cmake-presets-vs);
[CMake presets no Qt Creator](https://doc.qt.io/qtcreator/creator-build-settings-cmake-presets.html);
[build systems do Qt Creator](https://doc.qt.io/qtcreator/creator-reference-build-systems.html).

## O projeto é o texto; o IDE é uma vista dele (2026-10-06)

Pergunta do utilizador: *"um utilizador experiente consegue criar um projeto destes do zero sem o
Visual/Qt, ou precisa daquela infinidade de opções da interface? metade daquilo é poluição visual?"*

- **Tudo o que DEFINE o build é texto.** `CMakeLists.txt` (alvos, fontes, includes, defines, flags,
  ligações) mais `CMakePresets.json` (gerador, arquitetura, `toolset`, compilador por `CC`/`CXX`,
  `CMAKE_BUILD_TYPE`, `binaryDir`, `installDir`, `toolchainFile`, `environment` e `cacheVariables` —
  onde vivem o `CMAKE_CXX_FLAGS` e as definições). A cmake-presets(7) confirma-o campo a campo: é
  JSON, e nada do que define o build existe só no GUI.
- **Três coisas NÃO vivem no projeto** — e são a razão de o mesmo projeto pedir configuração noutra
  máquina: o **kit/compilador** (vive na máquina; no Qt Creator é a lista de kits, no VS vem do
  workload instalado); o **lançamento/depurador** (o VS guarda em `.vs/launch.vs.json`, que pode ser
  derivado dos presets); e o **índice/IntelliSense** (cache, recriado a cada configure).
- **O resto do GUI é conveniência, não requisito.** As property pages de um `.vcxproj` parecem
  infinitas porque o MSBuild **não tem linguagem própria**: cada switch do compilador é uma
  propriedade. Tudo é XML no próprio `.vcxproj` — editável à mão e ninguém o faz; o CMake existe
  precisamente para não se fazer. E num projeto **CMake** o VS não usa property pages: *"Visual
  Studio uses a CMake configuration file to drive CMake generation and build"*, e a manipulação de
  projeto (adicionar/remover/renomear ficheiros) reescreve o `CMakeLists.txt` com pré-visualização.
- **Prova no disco:** as "opções" que o VS mostraria neste projeto já estão lá como texto —
  `DRAFTCAD/build/axio-debug/DraftCAD.vcxproj` traz `<LanguageStandard>stdcpp17</LanguageStandard>` e
  os `AdditionalIncludeDirectories` com o Qt 6.10.0 e o Vulkan SDK. A interface é uma forma sobre
  essas linhas, e as linhas vieram do nosso preset.
- **Veredicto honesto:** um profissional faz tudo em texto — é assim que o CMake se usa — e não perde
  flag nenhuma. O que se perde sem IDE não é configuração: é depurador, profiler, refactor e
  navegação, que são características do IDE e não do projeto.

### As property pages, uma a uma — e a linha que as escreve (2026-10-06)

Segunda rodada da mesma pergunta, agora com os prints das property pages do Tibia74 (`.vcxproj`) à
frente, incluindo o campo que ele diz ter preenchido à mão: Linker → Input → Additional Dependencies
com `lua51.lib;libmysql.lib;libxml2.lib;ws2_32.lib;zlib.lib;iconv.lib;sqlite3.lib`.

| Página do VS | Linha de CMake |
|---|---|
| Linker → Input → Additional Dependencies | `target_link_libraries(alvo PRIVATE lua51 mysql ...)` |
| Linker → General → Additional Library Directories | `target_link_directories` |
| C/C++ → General → Additional Include Directories | `target_include_directories` |
| C/C++ → Language → C++ Standard | `set(CMAKE_CXX_STANDARD ...)` / `target_compile_features` |
| C/C++ → Preprocessor → Definitions | `target_compile_definitions` |
| C/C++ → Optimization / Code Generation | `CMAKE_CXX_FLAGS_<CONFIG>` / `target_compile_options` |
| General → Target Name / Configuration Type / Extension | `add_executable` / `add_library(STATIC/SHARED)` |
| General → Output / Intermediate Directory | `CMAKE_RUNTIME_OUTPUT_DIRECTORY` / `CMAKE_ARCHIVE_OUTPUT_DIRECTORY` |
| General → Target Platform Version | `CMAKE_SYSTEM_VERSION` |
| General → Platform Toolset | vem do compilador instalado (máquina, não projeto) |
| Debugging → Working Directory | `VS_DEBUGGER_WORKING_DIRECTORY` ou `launch.vs.json` |
| Build Events → Pre/Post-Build | `add_custom_command(TARGET ... PRE_BUILD/POST_BUILD)` |
| Build Events → Custom Build Step | `add_custom_command` / `add_custom_target` |
| Command Line / All Options | a leitura final: o que o compilador recebe |

O que **não** tem equivalente de primeira linha são nichos do MSVC — Embedded IDL (COM), Windows
Metadata (WinRT/UWP), Manifest Tool, XML Document Generator — e os `VC++ Directories`, onde o CMake
deliberadamente não deixa escrever: os includes vêm do `find_package`/`target_include_directories`.

**A prova que fecha o caso dele:** no Tibia74 aquela lista foi escrita à mão, campo a campo. No
DRAFTCAD está lá sem ninguém a ter escrito — `build/axio-debug/DraftCAD.vcxproj` linha 141 traz
`<AdditionalDependencies>` com `Qt6Core.lib`, `vulkan-1.lib`, `dxfrw.lib`, `d3d11.lib`, `ws2_32.lib`,
e as `<AdditionalIncludeDirectories>` (linha 113) com o Qt 6.10.0 e o Vulkan SDK. Veio do
`target_link_libraries` e do `find_package` do `CMakeLists.txt`: o mesmo campo, a mesma página, e a
diferença é quem o escreveu.

O compilador, esse, instala-se sozinho — a `learn.microsoft.com` dá o caminho por linha de comando
(`winget install -e --id Microsoft.VisualStudio.BuildTools`, componente
`Microsoft.VisualStudio.Component.VC.Tools.x86.x64`, ou o `vs_buildtools.exe` estável com um
`.vsconfig`), que é o que a mensagem de "falta compilador" passou a nomear.

Fontes: [CMake projects in Visual Studio](https://learn.microsoft.com/en-us/cpp/build/cmake-projects-in-visual-studio),
[CMake presets no VS](https://learn.microsoft.com/en-us/cpp/build/cmake-presets-vs) e
[Install the MSVC Build Tools](https://learn.microsoft.com/en-us/cpp/overview/acquire-msvc).

## O depurador e o resto do que um expert usa — medido na máquina (2026-10-06)

Pedido do utilizador: *"põe isso no plano e tudo o que for necessário para que um utilizador experiente
consiga fazer aqui qualquer coisa que faria lá, seja depurar ou qualquer coisa, levando em consideração
a não utilização ou a mínima de novas janelas ou botões."*

**O que existe nesta máquina** (procurado, não suposto):

| procurado | resultado |
| --- | --- |
| `OpenDebugAD7.exe`, `vsdbg.exe`, `gdb.exe`, `lldb-dap.exe`, `cppvsdbg.exe` | **zero**, em todas as pastas onde se costumam procurar |
| `cdb.exe` + `dbgeng.dll` | **existe** — `C:\Program Files (x86)\Windows Kits\10\Debuggers\x64\` (Windows SDK) |
| motor do Visual Studio | `vsdebugeng.dll` em Community 2022/2019 e Build Tools; `msvsmon.exe` para remoto |
| Qt Creator | `qtcdebugger.exe` — observador de crashes do próprio Qt, **não** é um depurador |
| Python | 3.14.2; `debugpy` **ausente** (última publicada 1.8.22, exige >=3.10 — instala-se) |
| Node | v24.13.0 — traz `--inspect` e fala **CDP**, o mesmo protocolo que já falamos no preview |

Ou seja: **para C++ não é preciso instalar depurador nenhum**. O `cdb` é o motor de depuração da
Microsoft em modo consola — breakpoint por ficheiro:linha, passo-a-passo, call stack, variáveis,
attach a um processo, dump — e é o mesmo motor que o VS usa por baixo. O que não existe é a
INTERFACE. (Precisa dos `.pdb`, que a configuração Debug do build já produz.)

**O depurador não se inventa, escolhe-se.** A lista oficial de adaptadores DAP
(https://microsoft.github.io/debug-adapter-protocol/implementors/adapters/) tem C/C++
(`vscode-cpptools`), `lldb-dap` (LLVM, servidor DAP autónomo), Python (`vscode-python`) e JavaScript
(`vscode-js-debug`). O protocolo é standard: o trabalho é **ligarmo-nos** a ele, nunca escrever um
motor de depuração.

**O desenho, com o mínimo de interface nova** — cada peça reusa o que já existe:

| peça do depurador | onde vive | o que é novo |
| --- | --- | --- |
| pôr/tirar breakpoint | **margem do Monaco** (a dos números de linha) | nada — é o gesto que o editor já tem |
| continuar / passo / entrar / sair | **a barra flutuante do find** (`findbar.js`), no topo do código | uma barra fina, com o padrão já feito |
| linha actual acesa | a marca de linha que o log e o diff já usam (`revelarLinhaComRolagem`) | nada |
| call stack + variáveis | **coluna 3**, na camada que já mostra código/histórico/git | a camada já existe |
| qual programa depurar | a deteção que os cards de sugestão já usam (escolhe o `DraftCAD.exe`, não o `dwg2dxf`) | nada |

**As fases** (a ordem não é arbitrária — cada uma prova o motor antes de lhe dar ecrã):

- [x] **Fase 6a — C++ por consola.** Correr o alvo sob `cdb` num **card do terminal** (o mecanismo do
      build), com os breakpoints por `ficheiro:linha` e uma lista de comandos. Não é gráfico: é
      depuração a sério, com zero janela nova, e serve primeiro para MIM, que sou quem procura o
      crash. Prova a exigir: parar no breakpoint, ler a stack, ler o valor de uma variável.
      **Feito (2026-10-06)** — `builds/depurar.py` + ação `depurar` de `tool_gerir_projeto`; prova
      (dois breakpoints, pilha e locais no DRAFTCAD) e a armadilha do `-c` na secção "O depurador: o
      que ficou provado". A sessão é conduzida pela própria ferramenta, com o parâmetro `comandos`.
- [ ] **Fase 6b — ligar o Monaco ao motor.** O clique na margem vira breakpoint, a barra de controlo
      entra, a linha actual acende e a stack/variáveis aparecem na coluna 3 — tudo por cima do motor
      que a 6a provou.
- [ ] **Fase 6c — Python e JS pelos adaptadores.** `debugpy` para Python e o inspector do Node
      (CDP); aqui o adaptador faz o trabalho todo e o frontend é o MESMO da 6b. É esta fase que prova
      que o ecrã não se repete por linguagem — e é a razão de o desenho ser este.
- [ ] **Fase 5 (clangd)** é o par natural disto: sem índice não há "ir à definição" nem erro
      enquanto se escreve.
- Fora do plano, dito em voz alta: **profiler** (VTune/perf), **depuração remota** (`msvsmon` existe,
      mas é outro desenho) e time-travel. Não se constroem a reboque.

## O clique no erro e a bolinha, provados na janela — e o defeito que isso revelou (2026-10-06, 2ª parte)

Testado A CORRER na janela do Axio, não em laboratório. Criou-se `gerados/prova-erros/`
(CMakeLists + `main.cpp` com um `;` em falta), construiu-se pela ferramenta, e o card do erro
apareceu com o caminho a azul. Clicar nele abriu `main.cpp` na **linha 6, coluna 1** — exactamente
onde o `cl` apontou. A bolinha foi provada no mesmo molde: clique real sobre a margem da linha 5
do `PLANO.md` -> `cldr ponto-paragem` no DOM, 9x9px a `rgb(229,72,77)`, guardado como
`PLANO.md:5`; o segundo clique tirou-o.

**O defeito que isto revelou (grave, e atingia TODOS os projetos).** O `RE_ALVO` do
`src/frontend/js/editor/diagnosticos.js` exigia segmentos de caminho sem espaços. A pasta base de
todos os projetos deste utilizador é `D:\Dropbox\2 - Startup\CODER` — com espaços. Nenhum erro
do compilador era clicável, em projeto nenhum, e não se notava porque o sintoma é o silêncio
(nada fica azul). O `fs.existsSync` que devia validar nunca era consultado: o caminho nem era
reconhecido como caminho.

Substituiu-se o regex único por ANCORA + RECOLHA PARA TRÁS (`_recolherParaTras`): procura-se a
posição (`(L,C)`, `:L:C`, `@ L`, `line L`) e recolhe-se o caminho caractere a caractere até um
delimitador forte. O espaço passa a ser parte legítima do caminho; o `:` só é recuperado quando é
a letra do drive. Ficou também reconhecido o **`[caminho @ L]` da stack do cdb** — clicar num
quadro da pilha abre o ficheiro na linha, que é o que faltava dentro de um depurador.

Medido depois: 2000 linhas de stack -> 2000 alvos em 6 ms; 2000 linhas de `ModLoad: ...dll` ->
ZERO falsos positivos em 2 ms; linha de 400 000 caracteres -> 0 ms.

**Armadilhas de teste que isto deixou** (custaram conclusões erradas a meio): (a) `_pintar(card)`
sai cedo se o card NÃO estiver aberto, logo procurar `.term-diag` com o card fechado dá ZERO e
isso não é avaria — é o desenho; (b) com o terminal escondido atrás do editor, a própria
`#term-cards` mede 0x0 e um clique por seletor cai em (0,0) — medir a caixa antes de clicar.

Limite aceite: `CMake Error at CMakeLists.txt:3 (project):` recolhe o prefixo e não resolve.
Cortar prefixos por heurística traria falsos positivos piores que a oportunidade perdida.

## Erros do compilador clicáveis — o que o compilador escreve, medido (2026-10-06)

Fecha a Fase 1. `builds/diagnosticos.py` lê a saída de um build e devolve cada erro com ficheiro,
linha, coluna, gravidade e código; `tools/builds.py` passa a pôr esse resumo À FRENTE da saída crua
(em `_configurar` e `_construir`), para quem lê o card e para o agente.

**Os formatos não foram adivinhados: compilou-se de propósito para os ver.** Amostras reais, do
`cl.exe` desta máquina e do CMake 4 desta máquina:

| o que se escreveu | forma real da linha |
| --- | --- |
| erro de identificador | `C:\...\erro.cpp(2): error C2065: 'nao_existe': identificador não declarado` |
| o mesmo com `/diagnostics:column` | `C:\...\erro.cpp(2,5): error C2065: ...` |
| include em falta | `C:\...\falta.cpp(1): fatal error C1083: Não é possível abrir arquivo incluir: 'nao_ha.h'` |
| fonte inexistente | `c1xx: fatal error C1083: ...` — **sem localização nenhuma** |
| erro do CMake | `CMake Error at CMakeLists.txt:3 (message):` e a mensagem na linha SEGUINTE, tudo isto em **stderr** |
| GCC/Clang | `src/main.cpp:12:34: error: use of undeclared identifier 'x'` |
| MSBuild | `C:\proj\app.vcxproj(15,7): error MSB1009: Arquivo de projeto não existe.` |

Dois factos que decidem o parser:

- **A coluna não existe por omissão.** O `cl` escreve `ficheiro(linha):`, só acrescenta `,coluna`
  com `/diagnostics:column`. Um parser que exija a coluna perde TODOS os erros do MSVC normal.
- **A palavra-chave fica em inglês mesmo com a mensagem traduzida** — medido: `error C2065:
  'x': identificador não declarado`. A âncora é o **código** (`C2065`, `MSB1009`), nunca a palavra.

Prova: 8 linhas reais reconhecidas (incluindo o `c1xx:` sem localização), 0 falsos positivos nas
linhas de progresso (`[ 50%] Building CXX object ...`, `BUILD SUCCESSFUL in 1s`) e no `10.5.3:12`.
Campainha que valeu: a mensagem do CMake **engolia a linha seguinte** (um erro do GCC logo a seguir
entrava dentro da mensagem) — a lista de padrões de "linha filha" tinha de incluir o formato do GCC.

### O clique no card (2026-10-06)

`src/frontend/js/editor/diagnosticos.js` marca, na saída de QUALQUER processo, cada `ficheiro:linha`
como um alvo clicável: o clique abre o ficheiro naquela linha no Monaco (`WorkspaceView.openFileAtLine`).
Não é só para C++ — vale para um traceback de Python, para o erro de um linter, para o que vier.

Três decisões que a medição impôs:

- **Só o que EXISTE fica clicável.** Antes de pintar, o caminho é resolvido contra o `cwd` do card e
  testado no disco (`fs.existsSync`). Um caminho partido pelo espaço de "Program Files" deixaria um
  azul a prometer um clique que não faz nada; assim fica texto normal. Medido: 2 de 5 linhas de uma
  cena viraram ligação (as que existiam) e o texto ficou byte a byte igual ao original.
- **O `cwd` do card passou a viajar.** `process_started` e `/api/processos` levam agora `cwd`: sem ele
  um caminho relativo (`src/main.cpp`) não tem contra o que ser resolvido. É informação que já
  existia no registo do processo — só não saía.
- **A saída é pintada por LINHA COMPLETA.** O que chega do processo chega em pedaços de 4096 bytes, e
  uma linha pode ser cortada a meio. O card guarda a cauda incompleta e só a desenha quando a quebra
  chega — senão metade de um `ficheiro:linha` ficava texto e a outra metade ligação. Provado com a
  linha partida em dois: `src/...py(10` não acende nada, `...4): error ...` acende inteira.

**Armadilha medida (custou um congelamento de 60 s a mim próprio).** A primeira versão da expressão
que apanha `caminho(linha)` era um `(?:[^separadores]+[\\/])*` a seguir a `[^separadores]+\.` — com
uma linha de 400 000 caracteres sem quebra (o caso de um `compile_commands.json` minificado, que é
exactamente o que aparece num card) o motor de expressões regulares entra em retrocesso catastrófico
e a interface **congela**. Não é hipótese: o meu primeiro teste de laboratório estourou os 60 s.
Correcção: `LIMITE_LINHA = 1000` — uma linha maior que isso não é um erro (é um ficheiro gerado numa
linha só) e sai como texto puro. Medido depois: a mesma linha de 400 000 caracteres custa **1 ms**.

## O depurador: o que ficou provado, e a porta que não abre (2026-10-06)

Fase 6a feita: `builds/depurar.py` (achar o `cdb`, formar a linha de comandos, ler os pontos de
paragem) + a ação `depurar` de `tool_gerir_projeto`, que abre o executável sob o depurador **num card
do terminal** — zero janelas novas, o mesmo mecanismo do build.

**A armadilha, medida e não suposta: o `-c` não serve.** A primeira tentativa foi a que a
documentação sugere — passar tudo na linha de comandos, com `-c` e a lista inteira de comandos
(`.lines`, `bp`, `g`, `k`, `dv`, `q`) separada por pontos e vírgulas.
Resultado, em VÁRIAS combinações (com e sem `-g`, com `-o`, e com `-logo` a gravar a sessão em
ficheiro para não depender da captura do stdout): **os comandos do `-c` não produziram uma única
linha de saída** e a sessão terminava logo (exit 42), sem parar em lado nenhum. O `ModLoad` do alvo
aparecia; os comandos, não.

**A porta que abre é o stdin.** Os MESMOS comandos, escritos no stdin do `cdb`, funcionaram à
primeira:

```
Breakpoint 0 hit
prova!main+0xc [C:\...\prova.cpp @ 8]
0:000> k
prova!main+0xc [C:\...\prova.cpp @ 8]
prova!invoke_main+0x22 [exe_common.inl @ 78]
...
0:000> dv
              x = 0n7
              y = 0n0
```

Ou seja: parou no ponto de paragem, a stack saiu com ficheiro e linha, e o valor da variável saiu.
E isto é a forma que o Axio já tem — o card escreve no stdin do processo. As três primeiras linhas
(`.lines`, `bp ...`, `g`) são escritas por nós no arranque; a partir daí a sessão é conduzida com
`k`, `dv`, `g`, `p` escritos no campo do terminal com o card selecionado.

Três cuidados que a prova fixou:

- **Nada de `-g`.** Ignorar o breakpoint inicial deixaria o programa a correr antes de os nossos
  pontos estarem marcados — os `bp` chegariam tarde.
- **`-y` e `-srcpath` apontam só a pastas locais** (a pasta do executável e a do projeto). Sem
  servidor de símbolos: é offline, é rápido, e o que interessa depurar é o código do projeto.
- **Pontos por `ficheiro:linha`**, com o nome reduzido ao basename (a forma provada); `modulo!ficheiro:linha`
  passa intacto para o caso de o nome se repetir.

**PROVADO a 2026-10-06, no DRAFTCAD.** Com o backend reiniciado, a sessão correu dentro do card,
contra o `DraftCAD.exe` de `DRAFTCAD/build/axio-debug/`: `Breakpoint 0 hit` em `main.cpp @ 14`, e
depois de `g`, `Breakpoint 1 hit` em `main.cpp @ 19`. A `k` deu a pilha com ficheiro e linha em cada
quadro; a `dv` deu as locais (`argc = 0n1`, `argv`, `jsonPath`, `format`, `engine`, `app` — `app` e
`engine` já construídos, porque já se passou por eles); a `?? argc` devolveu `int 0n1`; a
`x DraftCAD!main` achou o símbolo.

**O que o DRAFTCAD ensinou, e que passou a valer no código:**
- **`-lines` na linha de comandos do `cdb`**, mais `l+t` e `l+s` na preparação. Sem a flag, o `.lines`
  enviado pelo stdin chega tarde: a sessão para e mostra só assembly (`mov r9d,60A00h`). Com ela, o
  prompt mostra a origem — `>   14:     QGuiApplication app(argc, argv);`. Fonte oficial: "Enables
  source line debugging" (cdb-command-line-options). ARMADILHA: **sem `l+t` o `p`/`t` anda por
  INSTRUÇÃO, não por linha** — a lista de comandos dizia "passo a passo por linha" e mentia.
- **A lista de comandos estava pobre**: não tinha como ver ONDE se está (`l+s`) nem como avaliar uma
  expressão (`??`), que é o comando mais pedido de todos. Corrigida.
- **A sessão passou a ser conduzida pela ferramenta**: `acao='depurar'` aceita `comandos`
  (ex: `'k;dv /t /v;?? argc'`); sem `breakpoints`, vão para a sessão que JÁ está aberta. Antes disto,
  o agente não tinha por onde conduzir a sessão que ele próprio abria — só o utilizador, pelo campo
  do terminal do card.
- **ARMADILHA DE PROVA:** lançar o `cdb` pela rota `/api/terminal/exec` NÃO passa o PATH do kit, e o
  `DraftCAD.exe` sai logo (`|` responde `exited`) sem carregar as DLLs do Qt. A ferramenta passa
  `caminhos_extra` e não sofre disto; um teste à mão sofre — e foi o que aconteceu.

## O botão de depurar na barra do terminal e o ficheiro a abrir sozinho (2026-10-06)

O pedido: "colocar o icone do lado da borracha pra rodar o codigo manualmente no modo debug e abrir
automaticamente no monaco quando encontrasse" e "algo mais visual e intuitivo como um popup com os
controlos".

**O BOTÃO.** `#btn-debug` fica na barra do terminal, 8px à esquerda da borrachinha (levou o
`ml-auto` que era do `#btn-clear`; medido no preview: debug x=362, clear x=394). Ao clicar, manda o
ficheiro aberto no editor e os pontos marcados na margem para `POST /api/terminal/depurar`, que
chama `builds.abrir_depuracao`. Sem pontos marcados **corre o programa em modo de depuração e para
onde ele rebentar** — que era a versão real do "ícone que caça o indetectável". O motor decide-se
pelos pontos; sem eles, pela extensão do ficheiro aberto.

**O AVISO AO EDITOR.** Evento SSE novo `debug_stop` {pid, arquivo, linha} -> `openFileAtLine`. Quem o
emite é um VIGIA ligado ao processo (`process.seguir_saida_processo`), que lê cada linha nova à
medida que chega. Isto corrigiu um defeito de fundo: a leitura em português só aparecia quando eu
conduzia a sessão; agora sai sempre, mesmo que seja o utilizador a clicar nos botões do card.

**TRÊS DEFEITOS QUE O TESTE APANHOU** (todos medidos, todos corrigidos):
- o cdb diz a LINHA mas não o FICHEIRO; só um `k` traz os quadros com o caminho. O `k` passou a ir
  escrito depois do `g` na preparação. Sem isto o C++ encontrava a queda e não tinha o que abrir.
- num rebentamento o motivo chega ANTES da posição nova (`Uncaught exception` antes do
  `> ficheiro(linha)`): comparar o estado todo fazia emitir com a posição velha e o aviso apontava a
  linha 1 quando a queda era na 2. Passou a comparar só (arquivo, linha).
- uma sessão antiga a morrer escrevia leitura no card da sessão nova; o vigia sai cedo se já não for
  a sessão dele.

**A LEITURA DEIXOU DE SE REPETIR:** devolvia o bloco inteiro a cada mudança de uma linha; passou a
devolver só o que ainda não foi escrito.

**PROVADO** com sessões reais (não com dumps guardados): C++ sem pontos -> `main.cpp:17`; Python sem
pontos -> `quebra.py:2`; Python com ponto marcado na 5 -> `quebra.py:5`. Ficheiro E linha certos nos
três. O clique dentro da janela ainda não correu — o servidor a correr tinha o código velho (o POST
deu 404, o que provou a fiação toda; falta o reinício).

**O "99% DOS ERROS", COM FONTE.** Um agente que ache sozinho qualquer bug não existe: os erros
possíveis não têm fim e muitos não se decidem por cálculo. O degrau seguinte é documentado e tem
outro nome: **AddressSanitizer** do MSVC (`/fsanitize=address`, VS 2019 16.9+), que apanha
out-of-bounds, use-after-free e use-after-scope — erros que não rebentam e não dão erro. É uma opção
de COMPILAÇÃO, não um botão, e não está feito. Fonte:
https://learn.microsoft.com/en-us/cpp/build/reference/fsanitize?view=msvc-170

## O que falta (medido, não suposto)

- **Depurador:** a Fase 6a está feita e **provada no DRAFTCAD** (C++ pelo `cdb`, num card: pontos por
  `ficheiro:linha`, pilha, locais, e a sessão conduzida pela própria ferramenta com `comandos`).
  A **6b** já tem o clique na margem a marcar o ponto, os botões de controlo dentro do card
  (Continuar/Passo/Entrar/Sair/Pilha/Variáveis/Terminar), o botão de depurar na barra do terminal e
  o salto do editor para a linha onde parou (tudo feito e provado a 2026-10-06, ver as secções
  próprias). A linha ACESA no código entrou a seguir (ver "A linha do erro acesa no editor"); falta a
  stack na coluna 3; a **6c** (Python) já corre pelo `pdb`, no mesmo card e com os mesmos botões.
- **Instalar componentes da Qt** está bloqueado pelo próprio instalador nesta máquina (ver a secção
  "Instalar o que falta"): o passo seguinte é atualizá-lo (`MaintenanceTool update`), com o custo dito.
- **Pasta solta de `.cpp`/`.h`** sem ficheiro de projeto: o explorer já a arruma por tipo (Fontes /
  Cabeçalhos) e o retrato do contexto identifica-a (`C++ (pela extensao dos ficheiros)`). O que
  falta é o **motor de build**: `detetar.py` cai em "desconhecido" (os tipos são
  cmake/msbuild/qmake/python/npm/cargo/go/make), logo não há caminho de compilação para só código.
- **Dependências nativas atrasadas**: o bloco de manutenção do prompt mede PyPI/npm; vcpkg, Conan,
  NuGet e Cargo ainda não têm verificação de "está atrás do registo" (o manifesto já é lido, a
  versão publicada ainda não é comparada).

- **Erros do MSBuild/MSVC** já são lidos e resumidos (`builds/diagnosticos.py`) e cada linha com
  localização é clicável no card. A saída do MSBuild é **localizada em português** ("Arquivo de
  projeto não existe"); só os códigos ficam em inglês (`MSB1009`) — por isso o parser se agarra
  ao código, nunca à palavra.
- **`.pro`** (qmake) não tem leitor: sem API oficial de fontes, a resposta da ferramenta di-lo em vez
  de falhar em silêncio. O `.sln` já é lido para a árvore; falta-o para as flags.

- **Motor de jogo** (Unreal/Unity) fica de fora: tem pipeline próprio.

## O ponto de paragem na margem do editor — a 6b começou (2026-10-06)

Medido **antes** de escrever a peça, no editor real da janela a correr (`layoutInfo`): `contentLeft`
é **16** e vem TODO da faixa fina do folding (`lineNumbersWidth` 0, `glyphMarginWidth` 0,
`decorationsWidth` 16). Foi isso que decidiu o desenho — **não se ligou a margem de glifos**: ligá-la
acrescentaria ~20px e empurraria o código para a direita, num editor cujo recuo é uma escolha medida.

Com as duas larguras a zero, um clique nos 16px da margem **só pode** responder como
`MouseTargetType.GUTTER_LINE_DECORATIONS` (=4, lido na fonte instalada do monaco-editor 0.56.0) — a
faixa que já existe serve, sem um pixel novo. O ponto pinta-se por `linesDecorationsClassName`, o
irmão do glyph margin que desenha nessa mesma faixa; a bolinha é o `::after` do CSS (o
`background-color` de `.margin *` já era forçado a transparente por uma regra antiga, e o
pseudo-elemento não é atingido por ela).

Guardado **por projeto** (chave `state.rootPath`, localStorage `axio-pontos-paragem`): marcar pontos
no Axio não deixa nada no DRAFTCAD. O clique no chevron do folding é ignorado (`closest('.codicon')`),
tal como o clique na numeração de linha e no texto — os três provados.

Prova (`tool_executar_js`, módulo lido do disco e dirigido por um editor falso): 16 verificações —
dois cliques marcam dois pontos, o segundo clique no mesmo sítio tira, o gravado é
`{src/main.cpp: [14,19]}`, a troca de ficheiro pinta só as linhas dele e a troca de projeto limpa e
devolve os pontos do disco.

**Armadilha (minha, e do mesmo tipo da que abriu esta rodada):** a declaração era `projectoAnotado` e
um uso escreveu `projetoAnotado` — a sintaxe passa e o módulo rebenta em execução. Foi o teste
dirigido que o apanhou; é a razão de ele existir.

A lista sai por `pontosDeParagem()` (formato que o motor já lê: `nome:linha;nome:linha`) e
`window.__axioPontosDeParagem()` devolve-a ao vivo — é por aí que a sessão do `cdb` a recebe, sem
endpoint novo.

## O depurador em Python — o mesmo card, o motor que já vinha dentro do Python (2026-10-06)

O `app.py:62` estava marcado na margem e não fazia nada: o que estava montado era o `cdb`, que sabe
C++ e não sabe Python. Agora abrem-se os dois, e quem escolhe é **a linguagem do primeiro ponto
marcado**: ficheiro `.py` corre sob o **pdb**, C/C++ sob o `cdb`.

A decisão de não instalar nada foi medida, não suposta: o `pdb` vem dentro do Python, fala pelo mesmo
stdin que o `cdb` já usava (`escrever_stdin_processo`), devolve o mesmo tipo de card e não exige
adaptador nem protocolo nenhum. O `debugpy` faria o mesmo por um caminho muito mais caro (servidor
DAP mais cliente DAP no frontend) — fica para quando o ecrã o justificar; hoje valia era ter o motor
a funcionar no card que já existe.

O que muda por dentro (`src/backend/builds/depurar.py`): `motor()` escolhe o depurador,
`python_do_projeto()` pega o venv da pasta do projeto (`.venv`, `venv`, `env`) e só cai no do Axio
quando ele não existe, `comando_python()` monta `python -u -m pdb "<script>"`, `pontos_python()`
resolve cada ficheiro dentro da pasta do projeto e `preparacao_python()` escreve os pontos e o `c`
inicial. Em `src/backend/tools/builds.py` o `_depurar` passou a despachar para `_depurar_python`, com
texto de retorno próprio (`_texto_depuracao_py`).

### Os comandos não são os mesmos — e é aí que se erra

Em C++ o `p` **anda uma linha**; no pdb o `p` **imprime uma variável**, e andar uma linha é o `n`. A
lista de comandos do card passou a ser por linguagem (`LINHA_DO_CARD` / `LINHA_DO_CARD_PY`), e a mesma
correção foi feita na descrição do parâmetro `comandos` da ferramenta — era ela que me faria escrever
`p` a pensar em passo dentro de um card de Python.

### A armadilha que custou uma sessão inteira: nome curto contra nome longo

O primeiro teste **parecia** funcionar: o `b <caminho>:7` era aceite e o `Breakpoint 1 at …` aparecia —
e o `c` passava ao lado do ponto, direto ao erro. A causa está medida: o pdb guarda o ponto sob o
caminho que lhe damos e compara-o com o que a execução reporta; no Windows o mesmo caminho existe em
duas formas (a curta do 8.3, `C:\Users\RODRIG~1\…`, e a longa) e as duas **não casam como texto**. Um
caminho vindo do `tempfile` sai em forma curta, o que a execução reporta é longo. `os.path.realpath()`
normaliza as duas e o ponto dispara (provado: `abspath != realpath`; depois `Breakpoint 1 hit` na
linha 7, `p total` → 0, `n` → linha 6).

Pela mesma razão, **no ficheiro que vai correr o ponto vai pelo NÚMERO da linha** (`b 62`): o pdb
resolve-o contra o ficheiro aberto e não há caminho nenhum que possa divergir. Só os pontos de outros
ficheiros levam caminho — e aí real, completo.

### O que isto ainda não é

- Corre **o primeiro ponto**; uma lista com dois ficheiros abre uma sessão só. Os pontos da outra
  linguagem são nomeados no retorno ("Ficaram de fora, nao sao Python") em vez de falharem em silêncio.
- Não há barra de controlo: continuar/passo/entrar são escritos no card ou pedidos a mim, e os dois
  caminhos passam pelo mesmo `_conduzir_depuracao`.
- Depois de o programa morrer, o pdb **reinicia-o no `c`** ("Running 'cont' or 'step' will restart the
  program"): a saída do ciclo é o `q`.
- O `app.py` do próprio Axio é depurável, mas parar em `app.py:62` e seguir com `c` arranca uma
  SEGUNDA instância, com o `iniciar_vigia_do_envio` a correr por cima. Ver com `p`/`n`/`q`, nunca com `c`.

## O depurador a falar português — o texto cru fica, ao lado nasce a leitura (2026-10-06)

O utilizador olhou para o card e disse-o sem rodeios: "aparece isso tudo mas eu n entendi um caralho".
O dump do `cdb` tem cerca de trinta linhas e três interessam; o do `pdb` é igual. A resposta **não** é
traduzir o dump nem escondê-lo atrás de uma janela: o texto cru fica, porque quem sabe ler precisa dele
e escondê-lo camuflaria o problema. O que faltava era uma **leitura** ao lado do cru — e é isso que
existe agora, escrita no próprio card:

    [axio] parou em main.cpp:12  ->  total = somar(total, numeros[i]);
    [axio] porque: ponto de paragem 0
    [axio] valores: i = 0  ·  ponteiro = 0xcccccccccccccccc (padrao repetido - enchimento de memoria por usar)  ·  numeros = { size=3 }  ·  total = 0
    [axio] quem chamou: main.cpp:12 <- exe_common.inl:79

O leitor vive em `src/backend/builds/leitura_depurador.py` (só texto entra, só texto sai: não sabe o que
é um processo, e é isso que o torna testável contra qualquer dump), o estado da sessão em
`depurar.leitura_nova` e a escrita no card em `tools/builds.py:_mostrar_leitura`.

### O que a prova apanhou (e que sem ela ficava lá)

- **Cada prompt come a primeira linha da resposta.** O `cdb` escreve `0:000> ` antes da primeira linha e
  o `pdb` escreve `(Pdb) `. Como o padrão de cada linha é ancorado no princípio, a linha que interessa —
  a primeira — era a única que nunca casava: o `i = 0` desaparecia da lista e o `Breakpoint 0 hit` nunca
  era lido (e a leitura dizia "arranque do programa"). Uma regex resolve os dois.
- **A paragem de arranque do cdb não é avaria.** `Break instruction exception - code 80000003` é ele a
  parar uma vez ao carregar; dizê-la como uma queda seria assustar sem razão. Só o `c0000005`
  (Access violation) é levado a sério — e aí a leitura explica-o: "o programa mexeu numa memoria que não
  era dele".
- **O `0n0` do cdb é decimal.** O prefixo `0n` mostra-se como `0`, não como um número mágico.
- **O cdb não diz o ficheiro na linha da paragem** (`>   12:` só tem o número): o nome sai do quadro da
  pilha com a mesma linha. No pdb, quando não há um `w` na saída recente, a leitura diz "linha 62" sem
  ficheiro — honesto em vez de inventado.
- **O que se vê numa paragem não vale para a seguinte.** Uma paragem numa linha NOVA limpa as variáveis e
  a pilha, senão a leitura mostrava valores de três passos antes como se fossem de agora.
- **A leitura não repete nem se perde.** A mesma leitura não se escreve duas vezes (assinatura guardada) e
  a janela são as últimas 80 linhas do card, não só a resposta do último comando: foi uma prova que
  mostrou que um `w` que chega depois do tempo de espera se perdia por completo.

### O que ainda faltava quando isto foi escrito (já não falta)

Quando esta leitura nasceu, ela só saía quando **eu** conduzia a sessão. Feito depois: os botões de
controlo (primeiro dentro do card, depois numa barra acima do campo do terminal), o botão de depurar na
barra do terminal, o ficheiro a abrir sozinho na linha da paragem e a leitura a sair venha o comando de
onde vier. O que resta do depurador está em "O que falta (medido, não suposto)".

## A linha do erro acesa no editor e a barra de controlo arrumada (2026-10-06)

O utilizador correu a bateria numa pasta dele ("Nova pasta", em Downloads) e voltou com três queixas
medidas — não supostas: o erro só aparecia no card, o editor não pintava a linha, e a barra de controlo
estava encostada à esquerda e sem fundo.

**O QUE JÁ FUNCIONAVA.** O editor **abre mesmo**, sozinho, na linha certa: disparado o evento à mão na
janela a correr, em 400ms o `ws-status` dizia `editor: .../depurar.py` e o cursor estava na linha 30.
O que faltava era só o vermelho.

**A LINHA ACESA.** O evento `debug_stop` passou a levar `erro=True/False`; quem sabe se foi queda é
`leitura_depurador.e_queda(motivo)`, o módulo que escreve o motivo — a ligação fica lá, nunca numa
comparação de texto espalhada por dois ficheiros. No editor, `linha_depurador.js` pinta a linha inteira:
vermelha (`rgba(244,63,94,.15)` + barra sólida de 3px `#f43f5e`) quando foi queda, neutra quando foi só
um ponto de paragem. A marca sai quando a sessão acaba e volta sozinha ao trocar de aba
(`onDidChangeModel`).

**O CAMINHO DO FICHEIRO.** O `pdb` do Python 3.14 escreve o caminho em minúsculas (`os.path.normcase`)
e o explorador guarda-o na grafia real: comparados byte a byte davam **duas abas para o mesmo ficheiro**.
`caminhoDoDepurador` resolve o caminho contra o ficheiro aberto e as abas, sem distinguir maiúsculas nem
`\` de `/`.

**A BARRA.** Virou uma pill centrada sobre o campo do terminal (medido: centro 550.0 contra 550.0 do
campo), fundo `#3a3a3a`, canto arredondado, 8px acima do campo — e **0px quando recolhida**, medido, para
o truque do `grid-template-rows: 0fr` não deixar uma faixa de padding à vista. Sem bordas, como ele pede.

### O que a prova apanhou (pdb real, não exemplo inventado)

Seis variantes do mesmo ficheiro, cada uma corrida em `pdb` a sério e passada pelo vigia do card:

| o que se estragou | o card | o editor |
| --- | --- | --- |
| nada (programa bom) | nada | nada |
| `"Carla": []` | parou em teste.py:5 | linha 5, vermelho |
| falta a vírgula | não arrancou (SyntaxError) | linha 9 |
| aspas abertas | não arrancou (SyntaxError) | linha 10 |
| indentação trocada | não arrancou (IndentationError) | linha 5 |
| linhas apagadas (5 variantes) | não arrancou | linha certa nas 5 |

**O CASO QUE NÃO APONTA, e não é defeito:** apagar só o `return` deixa o programa correr e imprimir
`None`. Não há erro nenhum, logo não há nada a apontar: é a terceira gaveta (dá a resposta errada e não
se queixa) e a única que continua a exigir um ponto de paragem marcado à mão.

### Duplicação que já cá estava (alertada, não mexida)

`editor.js` tem dois blocos de 9 linhas iguais (`applyContent` contra `aplicar`) e `terminal_cards.js`
repete 11 linhas de `preview.js`. São de antes desta rodada; ficam como candidatos a mesclar.

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
