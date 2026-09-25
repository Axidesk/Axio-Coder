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
| `detetar.py` | que projeto é (por evidência no disco), vertentes, e o que EXIGE (lendo `find_package`/`find_program`/`CMAKE_PREFIX_PATH`) |
| `kits.py` | o que está NA máquina (Qt por kit, MSVC por `vswhere`, CMake, Ninja, `glslc`, Vulkan, vcpkg); nota cada kit contra o projeto e nomeia o que falta |
| `presets.py` | escreve o `CMakeUserPresets.json` LOCAL (schema 6/10) — nunca toca no do projeto |
| `construir.py` | decisões e comandos (não executa): `preparar` devolve `precisa_configurar` |
| `cmake_api.py` | a File API do CMake: escreve o pedido, lê a resposta e devolve os alvos com fontes, grupos e flags |
| `arvore.py` | a árvore agrupada para o explorer (só leitura) e os nós virtuais `@arvore/...` |
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
- [ ] **Fase 4** — o `.sln` do Tibia: leitura por `msbuild -getItem` e o retarget 2015→2022
      numa cópia, provado a compilar.
- [ ] **Fase 5** — clangd (opcional): ir à definição, erro enquanto se escreve.
- [ ] **Criar do zero** — esqueleto de projeto novo (CMake/Qt/Python) escolhido pelo tipo de
      programa que o utilizador pedir.
- [ ] **Captura ao vivo da janela no preview** (WGC, já pendente no plano).

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
- **Pasta solta de `.cpp`/`.h`** sem ficheiro de projeto: `detetar.py` (o motor de build) cai em
  "desconhecido" — os tipos são cmake/msbuild/qmake/python/npm/cargo/go/make. Já não mente sobre o
  kit (ver a secção "Qualquer linguagem") e o RETRATO do contexto já a identifica
  (`C++ (pela extensao dos ficheiros)`, medido 2026-10-06), mas o motor ainda não tem caminho de
  compilação para **só código**.
- **Dependências nativas atrasadas**: o bloco de manutenção do prompt mede PyPI/npm; vcpkg, Conan,
  NuGet e Cargo ainda não têm verificação de "está atrás do registo" (o manifesto já é lido, a
  versão publicada ainda não é comparada).
- **A árvore agrupada** por categoria no explorer: quem sabe os ficheiros de cada alvo é a
  CMake File API — uma versão por extensão de ficheiro seria palpite e foi descartada.
- **Erros do MSBuild/MSVC** chegam (ao card e a mim) mas ainda não são clicáveis no Monaco. A
  saída do MSBuild é **localizada em português** ("Arquivo de projeto não existe"); só os
  códigos ficam em inglês (`MSB1009`).
- **`.sln` e `.pro`** ainda não têm leitor (a resposta da ferramenta di-lo, em vez de falhar
  em silêncio).
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
- Portar/retarget de projetos Visual C++ — https://learn.microsoft.com/en-us/cpp/porting/overview-of-potential-upgrade-issues-visual-cpp
