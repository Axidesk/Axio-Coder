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
- [ ] **Fase 1** — CMake File API: alvos, fontes e flags reais; árvore do explorer agrupada em
      Headers/Sources/QML/Resources (como o Qt Creator mostra, sem tocar no disco); erros do
      compilador clicáveis no Monaco.
- [ ] **Fase 3** — instalar sozinho o que faltar (MaintenanceTool CLI + vcpkg).
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

Prova medida no DRAFTCAD (77 ficheiros, 110 classes): a auditoria desceu de **191 apontamentos
para 1** — e esse 1 é real (`stb_truetype.h` inclui `stb_rect_pack.h`, que não está no projeto).
Refactor provado num **cópia descartável** dentro do projeto (nunca nos ficheiros dele):
mover para destino novo escreve o `#include` e o corpo verbatim; mover de volta não duplica o
include; função inline e protótipo sem corpo são recusados com o motivo; remover apaga o range
certo e a sintaxe fica limpa.

## O que falta (medido, não suposto)

- **Pasta solta de `.cpp`/`.h`** sem ficheiro de projeto: `detetar.py` cai em "desconhecido"
  (os tipos são cmake/msbuild/qmake/python/npm/cargo/go/make). Falta reconhecer só código.
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
