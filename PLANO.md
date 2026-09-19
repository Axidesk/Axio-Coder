# Plano — Axio Coder

> Fonte de verdade das fases em curso. O `REFACTOR_PLAN.md` cobre a refatoração estrutural
> (fechada); este cobre o produto. Atualizado a 2026-09-16.

## Onde estamos

**Fase 4 — a janela de preview.** A 4.1, a 4.2 e a 4.3 estão no ar e vistas pelo utilizador (o Axio
abre-se a si próprio no preview, com os botões a responder). A 4.4 está fechada: leio a consola e a
rede da página, localizo elementos pelo DOM, imprimo regiões exatas e clico/escrevo/teclo nela com
eventos reais — tudo pelo DevTools Protocol, por uma ponte entre o servidor Python e a janela. Com
a vista do preview à frente, um cursor desenhado na página mostra onde vou agir.
**O ciclo fechou-se em mim** (2026-09-16): carreguei o Axio dentro do próprio preview, li a consola e
a rede, localizei o `#btn-send` pelo DOM, cliquei num toggle (a vista do terminal alternou e voltou)
e escrevi num campo (o auto-resize do Axio reagiu ao evento `input`) — sem o utilizador tocar em nada.
**O utilizador vê o que eu faço** (2026-09-16): usar o preview acende o ícone dele, e se a barra onde
ele mora estiver fora do ecrã aparece um botão flutuante no mesmo lugar — clicar nele abre o preview.
Agir na página traz a vista para a frente sozinha; observar não rouba a vista. O aviso viaja pelo canal
`preview:uso`, com a classificação (agir / observar) decidida na ponte, ao lado das ações.

**A 4.5 arrancou (2026-09-17):** o UI Automation deixou de ser plano e passou a ferramenta
(`tool_operar_janela`, `src/backend/tools/janelas.py`). A verificação contra fontes oficiais
reescreveu a fase — a descrição que aqui estava ("três veículos") estava mal formulada. Ver abaixo.
**Próxima peça: o print por Windows.Graphics.Capture**, que é a única lacuna que ficou aberta.

Legenda: `[x]` feito · `[ ]` por fazer · `~~riscado~~` = concluído

---

## Fase 4 — a janela de preview

### [x] ~~4.1 — O preview que mostra~~  (FEITO)

Motor `WebContentsView` nativo do Electron, posicionado por cima do DOM.

- [x] ~~Motor do preview e IPC — `src/main.js`: `criarPreviewView`, `aplicarLimitesDoPreview`, `ACOES_DO_PREVIEW`~~
- [x] ~~Barra de endereço com voltar / avançar / recarregar / zoom / abrir ficheiro / abrir no navegador / fechar~~
- [x] ~~Regra de visibilidade: só aparece com a vista ativa **e** página carregada **e** nada por cima (`elementFromPoint`)~~
- [x] ~~Duplo clique num `.html` da árvore abre no preview~~
- [x] ~~Servir o projeto por HTTP (`/preview/<path>`) — sem isto o `.html` abria nu, porque por `file://` os caminhos absolutos (`/css/...`, `/editor/...`) resolvem contra a raiz do disco~~
- [x] ~~Permissões da view escolhidas pela classe do alvo: `file://` e `localhost` em modo Node (senão o `window.require` do `files.js` mata o módulo e a página fica sem botões), remoto em sandbox~~

### [x] ~~4.2 — O preview que arranca sozinho~~  (ESCRITO, POR VER AO VIVO)

Um card que arranca um servidor abre a página no preview sem intervenção.

- [x] ~~Deteção de endereço local no stdout — `src/backend/services/sugestoes.py`: `detectar_url_na_saida`~~
- [x] ~~A URL anexada ao evento `process_output` — `src/backend/tools/process.py`: `_emitir_saida_processo`~~
- [x] ~~Card ganha botão de globo no cabeçalho e dispara `axio-preview-open` — `src/frontend/js/editor/terminal_cards.js`: `_anunciarUrl`~~
- [x] ~~`0.0.0.0` normalizado para `localhost`; códigos ANSI cortados; `localhost.malicioso.com` recusado~~
- [x] ~~Uma vez por URL (dedup) — se o servidor reiniciar noutra porta, abre outra vez~~

### [x] ~~4.3 — O preview que fala comigo~~  (FEITO — POR VER AO VIVO)

O Chrome DevTools Protocol (`webContents.debugger`) ligado à view e alcançável pelas minhas
ferramentas.

- [x] ~~CDP ligado no nascimento da view — `src/preview-cdp.js`: `prepararDepurador` (Runtime, Log e Page activos)~~
- [x] ~~Erros de consola como **dado** (nível, origem, ficheiro:linha) — e os 404 de recursos entram pelo `Log.entryAdded`~~
- [x] ~~Print de uma região exata (`Page.captureScreenshot` com `clip`), da janela inteira ou de um elemento~~
- [x] ~~"Onde está o elemento X" respondido pelo DOM: caixa, centro, se está pintado e se está dentro da janela~~
- [x] ~~Ponte Python → Electron: servidor HTTP efémero em `127.0.0.1`, token aleatório por arranque, passado ao Flask por `AXIO_PONTE_PORTA`/`AXIO_PONTE_TOKEN`~~
- [x] ~~Ferramentas: `tool_observar_preview` (estado · consola · elemento · avaliar · print)~~

### [x] ~~4.4 — O preview que eu opero~~  (FEITO — POR VER AO VIVO)

Cliques e teclas a sério, pelo CDP — o equivalente ao computer use, com a localização a vir do
DOM em vez de adivinhada do pixel.

- [x] ~~Clique e teclado por `Input.dispatchMouseEvent` / `dispatchKeyEvent` — `tool_operar_preview`~~
- [x] ~~Leitura de rede (`Network.enable`): só os pedidos com problema — 404, 500, ligação recusada — com URL e tipo; `tool_observar_preview` acao='rede'. O cancelado (`canceled`) não conta como falha~~
- [x] ~~Cursor desenhado na página, para o utilizador ver o que eu faço — div de 14px com anel verde, que pulsa no clique. Só com a vista do preview à frente; a pausa de 150 ms antes do gesto só existe quando o gesto pode ser visto~~
- [x] ~~Formulários: focar o campo, substituir o que lá está e escrever (`Input.insertText`)~~
- [x] ~~O seletor é re-resolvido no instante do gesto: uma página que se mexa não desalinha o clique~~
- [x] ~~O gesto devolve o **efeito** dele: `clicar` / `escrever` / `teclar` comparam a página antes e depois (elementos, elementos sem caixa, classes do alvo, comprimento do valor do campo) e anexam os erros de consola e pedidos falhados que o gesto causou — sem precisar de uma segunda chamada. Uma navegação a meio do gesto é detetada e os registos recomeçam~~
- [x] ~~A interface mostra que estou a usar o preview: o ícone `#btn-preview` acende (verde `--oliva`, a pulsar) e, se estiver fora do ecrã, aparece um botão flutuante no lugar dele. Uma ação de **agir** (carregar / mostrar / clicar / escrever / teclar) traz a vista para a frente sozinha; uma de **observar** (estado / consola / rede / elemento / avaliar / print) só acende o ícone, sem roubar a vista~~

### [~] 4.5 — Janelas nativas (EM CURSO — verificado 2026-09-17)

**Correção ao que aqui estava escrito (verificado 2026-09-17 contra fontes oficiais).** "Três
veículos distintos, que não se substituem" estava mal formulado: são **duas tarefas** e **três
técnicas**, e as duas de *mostrar* substituem-se uma à outra.

| Tarefa | Técnica | Veredito |
| --- | --- | --- |
| **MOSTRAR** (o utilizador ver a app dentro do Axio) | `DwmRegisterThumbnail` | espelho 2D ao vivo. A miniatura é composta **por cima** do conteúdo da janela de destino: não se desenha UI nossa sobre ela e os cliques não atravessam sozinhos. |
| **MOSTRAR** | `Windows.Graphics.Capture` (WGC) | **a via que a própria Microsoft recomenda hoje** para preview ao vivo. Custo medido: desenha uma borda colorida, que só sai com `IsBorderRequired=false` **e** consentimento do utilizador **e** a capacidade `graphicsCaptureWithoutBorder` num manifesto de app **empacotada**. |
| **OPERAR** (o agente agir) | **UI Automation** | por estrutura e por nome — é a capacidade genérica. |
| **OPERAR** | pixel / visão | fallback: só onde a árvore devolve um retângulo opaco (canvas de CAD, viewport 3D, jogo). |

**A frase que desata o nó: OPERAR NÃO PRECISA DE MOSTRAR.** O UI Automation fala com a janela pelo
*hwnd*, onde ela estiver — mesmo tapada por outra. Embutir uma app nativa dentro do Axio é, por isso,
100% **cosmético**: não desbloqueia nenhuma capacidade nova. E "dentro do preview" tem **um** caminho
legítimo: a app publicar-se em **web** — é o caso do *Pixel Streaming* da Unreal, que transmite
frames e input para um navegador, com o jogo a correr na máquina e a jogar-se dentro do Chromium.

**`SetParent` está fora, com prova oficial.** Resposta de moderadora da Microsoft
(learn.microsoft.com/answers, 23/04/2026): *"SetParent() across two separate processes was not
officially supported"*. Funciona em Windows 10, em VM e em Remote Desktop porque esses ambientes
renderizam por software ou por remoting GDI; no Windows 11 **local** o DWM continua a desenhar a
janela como top-level separada. Falha também por UIPI (app elevada vs. não elevada) e por
DPI-awareness diferente. Não é bug a contornar — é comportamento esperado.

- [x] ~~**UI Automation como ferramenta** — `tool_operar_janela` (`src/backend/tools/janelas.py`), com
  o mesmo vocabulário do preview: `janelas`, `mapa`, `elemento`, `clicar`, `escrever`, `teclas`,
  `print`. Alvo por `#AutomationId`, `n:<índice do mapa>`, `tipo:X` ou um trecho do nome.~~
- [x] ~~**Preferir sempre os verbos que NÃO injetam input**: `invoke` / `value.SetValue` / `toggle`
  operam por *padrões* e funcionam com o ecrã trancado e sem roubar o rato ao utilizador. O clique e
  as teclas injetam input e só entram quando nenhum padrão serve — e o retorno diz sempre qual dos
  dois caminhos foi usado.~~
- [x] ~~**Abrir e fechar programas** (`acao='abrir'` e `acao='fechar'`, 2026-09-17): `abrir` resolve
  por caminho escrito → `shutil.which` → App Paths → registo Uninstall (confirmado no disco) →
  **varredura de disco** com poda e teto de 8s; `fechar` envia WM_CLOSE e, se a app abrir um diálogo
  a pedir para guardar, o mapa mostra-o e a resposta é dada por `invoke` — provado no ciclo completo
  com o Paint (`Não salvar`).~~ — **nota:** isto responde ao limite da allowlist de executáveis,
  que governa **compilação** e não abrir uma app de GUI.
- [x] ~~**Achar o programa e escolher a janela certa** (auto-melhoria 2026-09-17, depois de o GIMP
  custar ~6 chamadas a descobrir à mão): a resolução cai até à **varredura de disco** quando o PATH,
  os App Paths e o registo falham — o registo fica **órfão** quando a pasta muda de sítio (medido:
  apontava para `D:\Jogos e programas\GIMP 2\` depois de o GIMP passar para `D:\Programas`). Medido:
  `gimp` em 1.9s, `photoshop` em 1.1s, `notepad`/`mspaint` pelo PATH em 0.0s. E o `abrir` passou a
  entregar a **maior janela pronta** do processo, não a primeira: a versão anterior devolvia a
  *splash* (medido no GIMP: `GIMP Startup`, sem controlos) e **desistia com erro** nas apps que
  delegam a janela a outro processo (o `notepad.exe` do Windows 11 sai com código 0 enquanto a janela
  abre) — provado que escolhe a `Principal` e não a `Splash` (1 057 980 vs 125 580 px) e que o caso
  delegado devolve o Bloco de notas.~~ — o mapa passou também a **explicar-se sozinho**: com zero
  alvos mede a segunda via (MSAA) e diz se é a app a não se declarar, em vez de deixar a dúvida.
- [x] ~~**Gesto por coordenada** (`acao='arrastar'` e `acao='clicar'` com `ponto`, 2026-09-17): o
  agente desenha numa tela plana. Duas armadilhas medidas no Paint: (1) a app desenha a **reta
  entre o press e o release** e ignora os movimentos do meio → **um press/move/release por
  segmento**; (2) as ferramentas de **forma** só pegam no arrasto se ele durar → **20 ms entre
  eventos**.~~ — **e a fronteira, medida:** isto vale para **tela plana** (1:1 entre o píxel do ecrã
  e o do desenho); num **viewport com câmara** o mesmo píxel vale distâncias diferentes conforme o
  zoom, e aí o caminho continua a ser a API do próprio programa.
- [x] ~~**A app que NÃO se declara — medido no GIMP** (2026-09-17): o `mapa` devolveu **6 elementos** e
  são só a moldura do Windows (`Sistema`, `Minimizar`, `Maximizar`, `Fechar`) — **zero** controlos do
  GIMP. Confirmado por duas vias independentes: UI Automation (6 descendentes) e MSAA/win32 (0
  descendentes, classe `gdkWindowToplevel`). O GTK2 desenha numa superfície única do GDK e não declara
  nada. **Esta é a fronteira, com nome e prova**, e a ordem que fica: onde a app se declara opera-se por
  nome; onde não se declara mas tem linguagem própria, escreve-se; o pixel é o último recurso e só
  serve em tela plana. No GIMP o caminho é o **Script-Fu em batch**
  (`gimp-console-2.10.exe -i -b "<script>" -b "(gimp-quit 0)"`, lançado por subprocess com lista de
  argumentos), provado ao vivo: imagem 1000x700 com 11 formas em ~9s, aberta na instância já a correr.
  Armadilhas medidas: `gimp-selection-none` (não `gimp-image-select-none`); `file-png-save` tem 11
  argumentos; `gimp-image-select-polygon` quer 4. O **Python-Fu está quebrado** — o `.interp` aponta para
  o caminho velho `D:\Jogos e programas\GIMP 2\bin\pythonw.exe`, que já não existe.~~
- [x] ~~**A superfície de trabalho e o menu que se revela** (auto-melhoria 2026-09-17, depois de o
  foguete do Paint deixar uma lua com 12 lados): o `mapa` passou a listar as **superfícies** (`[sup]`)
  — as áreas grandes que **não respondem a gesto** (o canvas, a folha, o documento). Ficavam de fora
  justamente por não serem alvo, e a caixa delas tinha de ser medida por fora com o pywinauto: no
  Paint, `[sup] Group aid='image' (2238,631 1409x1059)` é exatamente a caixa que o `arrastar` precisa
  (a mais pequena das três; as maiores são o `scrollViewer` e a janela). E o `clicar` passou a
  devolver **os alvos que o próprio clique revelou**, com o índice já pronto: abrir o submenu `Formas`
  devolveu **49 formas** (Linha, Curva, Oval, Retângulo, Triângulo, Estrela…) em vez de custar uma
  segunda leitura da árvore. Enquanto o menu está aberto, os itens dele ficam no **início** da
  numeração do mapa.~~
- [ ] **Print por WGC** — o `capture_as_image()` do pywinauto usa `PrintWindow` e devolve **nada em
  silêncio** nas apps WinUI/DirectComposition (medido no Bloco de Notas). Hoje há segunda via (o
  ecrã, que exige a janela à vista e não tapada); a via certa é o WGC, que lê a superfície composta
  pelo DWM e funciona com a janela tapada.
- [ ] **Visão + pixel** como fallback, com Set-of-Mark (o modelo escolhe um número, não uma
  coordenada) — ver a secção de Set-of-Mark abaixo.
- [ ] **Antes de qualquer destes: código.** AutoCAD tem LISP/.NET, ArchiCAD tem GDL e API, Unreal tem
  Python do editor. O clique só entra onde a API acaba — e é sempre o caminho mais frágil.

### Ver ficheiros dentro do Axio — o visualizador e as abas (2026-09-17)

O IFC, o PDF, o Office e o DXF abrem no **preview**, e cada família tem o seu leitor carregado só
quando é preciso (`npm run build:viewer`, por esbuild). **Zero alteração no backend**: a página e os
bundles vivem em `src/frontend/vendor/viewer/`, servidos pela rota `/vendor/<path>` que já existia. O
núcleo são 5 KB; abrir um PDF não paga o Three.js (5,9 MB) nem o DXF o seu próprio Three (1,2 MB).

**As abas são da página**, não do Electron: `preview.js:abrirPreviewDoFicheiro` passou a apontar para
`/vendor/viewer/index.html#f=<caminho>` e o viewer escuta `hashchange` — o Chromium **não recarrega**
quando só muda o fragmento, logo abrir sete ficheiros dá **sete abas no mesmo Chromium**, com os
modelos em memória. Medido: 7 abas de 7 famílias, zero recarregamentos.

Três armadilhas, todas medidas (nenhuma em documentação):
1. **MIME**: o Flask serve `.mjs` como `text/plain` e o Chromium **recusa** um módulo ou worker com
   esse tipo — tudo o que o browser carrega tem de sair como `.js` (o worker dos fragments e o do
   pdf.js são copiados com esse nome).
2. **Node dentro do preview**: `alvoPrecisaNode` (`main.js:284`) devolve verdadeiro para loopback, logo
   as páginas do Axio correm com `nodeIntegration`. O web-ifc (build de browser) recusa-se a arrancar
   quando vê um `process` de Node — erro `not compiled for this environment`, que **não é bug da
   biblioteca** (o mesmo ficheiro funciona em qualquer site). A guarda que ele lê é
   `process.versions?.node`, por isso a página do viewer **esvazia só a `versions`**
   (`Object.defineProperty(process, 'versions', {value: {}})`). A primeira tentativa — `delete
   globalThis.process` — resolvia o web-ifc mas deixava `require`, `module` e `Buffer` vivos e fazia a
   maquinaria interna do Electron levantar **76 exceções não apanhadas**
   (`node:electron/js2c/renderer_init`), que passavam despercebidas: medido, 76 → **0**.
   **Alternativa estrutural, não aplicada**: fazer `alvoPrecisaNode` devolver falso para
   `/vendor/viewer/` exigiria tirar à página do viewer a capacidade de ler ficheiros do disco, que é
   dela por desenho. O que **já não** é obstáculo (corrigido a seguir, "duas views"): o modo Node
   deixou de destruir a view quando muda.
3. **Renderizadores preguiçosos** (pptx, listas com *windowing*) usam `IntersectionObserver` e não
   montam nada se a aba estiver escondida ao carregar — daí o contrato `aoAtivar()`/`aoMostrar()`. E
   uma falha de aba escondida ficava **engolida em silêncio**: `estadoDe()` recria o nó de estado.

Medições ao vivo: IFC real de **8,6 MB** desenhado em 3D com 8 recursos de rede e **zero unpkg** (wasm
e worker self-hosted); PDF a 1275×1804; XLSX com 2 folhas; DOCX com 4 parágrafos; PPTX montado; PNG e
texto. O **dxf-viewer** traz o próprio three (aviso benigno de duas instâncias) e o `SheetJS` do npm
está **parado em 0.18.5** — instalado do CDN oficial (0.20.3, em tarball). Amostras em `gerados/`.

**Não existe leitor universal**: a ODA cobre DWG/DXF/RVT/STEP mas é paga; o xeokit é AGPLv3 (copyleft
forte) e não lê DWG/SKP/RVT; SKP e PLN são fechados de propósito — aí o caminho é o programa dono do
formato (Fase 5). O universal não é a biblioteca, é o **despachante** por extensão
(`src/frontend/js/editor/familia_ficheiro.js`).

#### Medições que a implementação obrigou (2026-09-17)

- **O `title` do pywinauto casa por igualdade exata**, não por substring, e `descendants(**kwargs)`
  não aceita `found_index`. Logo a resolução do alvo é filtrada em Python sobre a lista devolvida.
- **Uma janela Electron expõe 12 elementos na primeira leitura e 1225 na segunda.** O Chromium
  constrói a árvore de acessibilidade **quando percebe que há um cliente de UIA** — ou seja, **não é
  preciso** o `--force-renderer-accessibility` que se pensava. A ferramenta já faz a segunda leitura.
- **Os `iface_*` do pywinauto LEVANTAM exceção** quando o padrão não existe, em vez de devolver
  `None` — um `getattr(..., None)` não os apanha.
- **O campo de texto de uma app pode não ter nome nenhum** (o `Document` do Bloco de Notas tem nome e
  AutomationId vazios): sem o incluir no mapa, não há como lhe chegar. Agora entra, com `(sem nome)`.
- **Quando o nome empata, ganha o que responde a um padrão.** O `_resolver` apanhava o
  `ListItem 'Oval'` (sem padrão) em vez do `Button 'Oval'` (toggle), a ferramenta **nunca era
  activada** e o desenho saía vazio — com o defeito a parecer estar no gesto.
- **A app declara o estado que interessa, se se souber perguntar.** O canvas do Paint é um `Group`
  com AutomationId `image` e o **nome dele diz a ferramenta activa** ("Usando a ferramenta Lápis no
  Canvas"): foi assim que se mediu que o `toggle` **activa mesmo** o Oval, em vez de se supor.
- **`print` com região: a região é relativa à JANELA, não ao ecrã** — o mapa mostra as caixas em
  coordenadas de ecrã, e passar essas dá um recorte deslocado (o `crop` do PIL não levanta erro fora
  dos limites: preenche de preto). E a captura por composição pode vir desactualizada em apps WinUI:
  quando isso decide alguma coisa, confirmar pelo `ImageGrab`.
- **A leitura do valor é `iface_value.CurrentValue`** — não `.Value`, não `.value()`.

#### Casos concretos do utilizador

- **Servidor de Tibia (consola C++)** — **já funciona e não precisa de nada disto**: o Axio tem PTY e
  um terminal que lê o stdout. Texto entra, texto sai. É o caso mais fácil, não o mais difícil.
- **App do Qt Creator** — janela nativa: opera-se por UI Automation, onde ela estiver. O suporte a Qt
  é *"Qt (partly)"* pelas palavras do próprio repositório, logo **mede-se antes de prometer**.
- **Jogo da Unreal** — Pixel Streaming, quando houver um para testar.
- **3ds Max, Blender, SketchUp, ArchiCAD, Photoshop** — sem caminho web. **Ver** é que não se
  resolve; opera-se a interface por UIA e escreve-se na linguagem que o programa já tem (Fase 5).

---

## Fase 5 — operar software por código

Não é uma janela: é uma competência que se acumula. O caminho do Codex não é clicar no
SketchUp — é escrever Ruby. Não é clicar no Archicad — é escrever GDL. Não é clicar no Unreal —
é escrever C++.

- [ ] Memória por programa (APIs do SketchUp, Blender, Unreal) — o que o Codex não tem
- [ ] Verificação: o programa exporta ou renderiza, e eu leio o resultado
- [ ] Cresce com o uso; não se "implementa" de uma vez
- [ ] **No Unreal o alvo é o Python do editor** (`unreal`), não clicar nos nós: a Epic expõe em Python
  quase tudo o que expõe a Blueprint e corre em modo comando (`-run=pythonscript`), mas **não** tem API
  para criar ou ligar nós do grafo — o clique só entra no que não tem API (viewport, jogos)

### O IFC não precisa da Fase 5 — medido a 2026-09-17

O IFC é um **formato aberto** (ISO 16739), não uma app: escreve-se o ficheiro diretamente e não há
janela nenhuma para operar, logo não há UI Automation, nem clique, nem pixel. É o caso mais puro da
tese do CAD — declarar relações, calcular coordenadas por código, e **ler de volta para medir**.

Provado de ponta a ponta com o `ifcopenshell` 0.8.5: IFC4 com `IfcProject` → `IfcSite` →
`IfcBuilding` → `IfcBuildingStorey` (por `aggregate.assign_object`), 4 `IfcWall` com eixo
`IfcPolyline`, cada uma ligada ao piso por `spatial.assign_container`. Lido de volta do disco:
**perímetro 18,0 m exato ao bit** contra o declarado, e conferido por um PNG projetado das próprias
coordenadas lidas (nada de pixel adivinhado).

O sólido já não falta: `geometry.add_wall_representation` monta o `IfcExtrudedAreaSolid` (perfil +
profundidade) sozinho, e o volume lido de volta do disco fecha ao bit (3,000000000 m³ medidos com
`ifcopenshell.geom`). Continua por fazer o resto da parede a sério: vãos (`IfcOpeningElement` +
`IfcRelVoidsElement`), portas/janelas (`IfcDoor`/`IfcWindow`) e `IfcSpace`.

### IFC e STEP — um parâmetro, dois ficheiros (2026-09-17)

O IFC serve o **Archicad**, não o **SolidWorks**. O help oficial da Dassault lista o IFC nos File Types
do Import/Export (2019 e 2027), mas o **3D Interconnect** — o caminho associativo — cobre ACIS,
Inventor, CATIA V5, IGES, JT, PTC, Solid Edge, **STEP (AP203/AP214/AP242)** e NX, e nele o IFC não
está. O corpo da página do IFC no SolidWorks não foi extraível (o scraper traz só o índice), logo o
**modo** de importação do IFC no SW (malha *vs* sólido B-rep) fica por verificar — não se afirma.
Do lado oposto, o Archicad importa e exporta `.ifc`, `.ifcXML` e `.ifcZIP` (help AC27).

A decisão é o que o teste mostrou: **o mesmo parâmetro escreve os dois ficheiros**. Medido com
L=5,0 / A=3,0 / E=0,2 — o IFC sai com `IfcExtrudedAreaSolid` e o STEP sai AP214; o volume de ambos,
lido de volta do disco, é 3,000000000 m³ e a diferença entre eles é 4,4e-16. Nenhum dos dois serve
para os dois destinos: o IFC perde a precisão de sólido no import do SW e o STEP perde a semântica
toda no Archicad. O STEP sai do **cadquery** 2.8.0 sobre o kernel OpenCASCADE (`cadquery-ocp`, wheels
cp314) — é o único caminho **livre**, porque o Parasolid `.x_t`, que seria o nativo do SolidWorks, é
proprietário da Siemens e não tem escrita aberta.

**Aviso que tem de ir com o pedido:** o detalhe não serve para cálculo. A árvore importada inteira dá
centenas ou milhares de corpos e a Simulation do SolidWorks fica inutilizável. O modelo de cálculo é um
**LOD estrutural** (membros principais), separado do modelo detalhado da pele.

O caminho dos documentos de entrada também está aberto: a pasta lê-se, a imagem de referência vê-se
(`tool_ver_imagem`) e o PDF lê-se em texto **e** em imagem (`pymupdf` — texto extraído e página
renderizada a 110 dpi, ambos medidos). Antes de dizer que um formato não é suportado, o
`tool_info_ambiente` responde isso numa chamada, com o pacote pip candidato para o que falta.

**Ver o IFC dentro do Axio é biblioteca, e as peças já cá estão (verificado 2026-09-17 contra o
registo npm e a doc oficial).** Não é uma app nativa nem uma caixa de vidro: mostra-se no **preview**,
que já é um Chromium. A stack atual é `web-ifc` (parser em WebAssembly, MPL-2.0, 0.0.77) com
`@thatopen/components` (MIT, 3.4.8) — os `web-ifc-viewer` e `web-ifc-three` do IFC.js estão
**DEPRECATED** a favor deste —, e a doc deles exige que `three`, `web-ifc`, `camera-controls` e
`@thatopen/fragments` batam certo com o que a lib usa. O que já existe e serve: o `/preview/<path>`
serve página, `.js` e `.wasm` da mesma origem, e o caminho "abrir um ficheiro no preview em vez do
editor" já funciona para os `.html` (`explorer.js` → evento `axio-preview-open`) — um `.ifc` entra no
mesmo caminho, com a barra a apontar à página do viewer em vez do ficheiro. O custo não é o desenho
(o `IfcLoader` e a câmara resolvem-no em ~30 linhas): é juntar as peças num bundle, porque o pacote é
ESM e importa `three`, `jszip` e `three-mesh-bvh` por nome. **Ver e navegar não é operar**: a operação
continua a ser o `ifcopenshell`.

### O gerador paramétrico e o fan-out de formatos (2026-09-18)

A tese que fecha o desenho é esta: **um modelo fonte paramétrico → N exportadores pequenos**. Converter
ficheiros *acabados* é o caminho mau — perde-se semântica em cada salto e cada par de formatos é uma
conversão nova. Aqui acontece o inverso: a geometria escreve-se uma vez e há vários exportadores pequenos.

O núcleo genérico está de pé e auditado. `geometry/pecas.py` é o modelo **neutro** — um `Perfil` em 2D
mais uma operação (`Extrusao` ou `Revolucao`) e três eixos — e traz o `volume_previsto()`, que calcula
por Pappus e serve de **validação independente do exportador**. `exportador_ifc.py` (entidades escritas
à mão, porque não há API pronta para `IfcRevolvedAreaSolid`) e `exportador_step.py` (cadquery) **medem o
que escreveram, a ler o ficheiro de volta**. `geometry/catalogo.py` guarda o registo `MODELOS` — hoje
**vazio**, e é o ponto de extensão onde o próximo modelo se inscreve.

**A ferramenta é uma só e não nomeia nenhum modelo**: `tool_gerar_modelo` lê o catálogo e tira os
formatos de uma tabela `EXPORTADORES`. Sem o argumento `modelo` devolve o catálogo inteiro — modelos,
variantes e cada parâmetro com o valor de partida; com ele aceita ajustes pontuais
(`parametros='altura_total=32; numero_costelas=24'`), validados contra a dataclass.

**A primeira prova em escala foi reprovada e apagada (2026-09-18).** A árvore de Natal de 30 m saiu
medida ao bit — o STEP fechava em 277 de 277 peças, o IFC ficava 0,0117 % abaixo pela tesselagem — e
mesmo assim estava errada, porque era um erro de **desenho**, não de ficheiro: o corpo era a revolução
de um cone liso onde a referência tem painéis planos facetados, a estrela era um perfil plano extrudado
onde a referência tem uma estrela 3D multiponta, e não havia flocos nenhuns. Medir o volume prova que a
geometria saiu como foi pedida; **não** prova que foi pedido o que se queria. `arvore.py`,
`parametros.py` e os ficheiros gerados foram para a lixeira, e a lição entrou no método: **gerar →
olhar → corrigir**, e só depois entregar. O olho existe sem dependência nova — o `cadquery` exporta
vistas SVG de linhas escondidas de qualquer sólido, e o viewer do preview desenha o IFC em 3D para uma
captura.

Acrescentar um destino novo custa **um exportador**, não um projeto — é isso que a `EXPORTADORES`
(modelagem.py) já encena. O Blender, o SketchUp, o 3ds Max e o Unreal não precisam de SDK nenhum:
comem glTF/OBJ/STL, que o `trimesh` escreve a partir da mesma triangulação. O `.skp` mesmo (com as
tags e grupos do SketchUp) tem C SDK gratuito mas exige registo de developer e compilação nativa — é
caminho de Fase 5, e só se valer a pena.

### O caso AutoCAD — porque falhou o agente antigo

A pasta `cad/` (o plugin que o utilizador escreveu antes do Axio: C# / .NET Framework 4.8, máquina de
estados Idle → AnalyzingContext → Thinking → Executing → Idle, resposta do Gemini executada por
Roslyn) **foi removida do projeto em 2026-09-16** — o utilizador trouxe-a só como amostra do que *não*
quer repetir. Fica a lição, que não depende dos ficheiros. O plugin **não falhou por falta de
ferramentas nem por falta de um canal de clique**. Falhou por três coisas, e só uma delas é técnica:

1. **O modelo era a calculadora.** O system prompt mandava literalmente *"Use variáveis nomeadas
   (x0, x1, x2... y0, y1...) para o grid de paredes. Derive portas/janelas dessas variáveis. NUNCA
   hardcode números soltos."* — ou seja, pedir coordenadas a um modelo de linguagem, disfarçado de
   disciplina. É o caminho que a Microsoft mediu em **25,7 %** de acerto (ver abaixo).
2. **Nada media o resultado.** O contexto enviado (`GetCurrentContext`) trazia camadas, blocos,
   limites do desenho e a seleção — **nada de geometria**. E o único controlo de erro era a exceção:
   `ErrorRecoveryState` apanhava o *throw* e voltava a Idle. **Uma parede no sítio errado não lança
   exceção** — é geometria perfeitamente válida no lugar errado. Logo o ciclo nunca corrigia nada.
3. **O vocabulário estava certo** — e é o que se aproveita. `IAutoCadService` tem ~30 métodos de
   intenção (`InserirPortaPorPonto`, `InserirJanela`, `DrawLinearStair`, `AddDimension`,
   `CleanWallIntersections`, `GetRoomBoundaries`). Constrager o modelo a um vocabulário pequeno de
   operações é exactamente o desenho certo; o que estava errado era **quem calculava os números**.

O que muda na Fase 5, e é a regra que não se repete:

- **O modelo declara relações, não coordenadas.** "quarto 3×3 a norte da sala, porta de 0,80
  centrada na parede comum" — e um **solver determinístico** (Python puro, sem modelo) calcula os
  números. Aritmética é trabalho de código; um modelo a fazer contas em token é um erro de desenho.
- **Verificar é medir o desenho, não olhar para o ecrã.** Eu leio as entidades de volta (DXF/base de
  dados) e comparo distâncias — aí o erro é um número, e um número corrige-se. Sem isto não há ciclo.
- **A base de dados do CAD é o DOM do CAD.** Para saber onde está a parede 3, pergunta-se ao
  desenho (precisão de 16 casas decimais); o viewport é *espaço de ecrã*, com zoom e pan pelo meio —
  um píxel em (400, 300) tanto pode ser (4,50 m, 2,30 m) como (45,0 m, 23,0 m). Medir píxel **não**
  dá noção espacial: é ambíguo por construção.

### Ver sem saber apontar: Set-of-Mark

O nosso modelo não faz *grounding* — não sabe devolver a coordenada de um alvo visual. A técnica que
resolve isso não o obriga a aprender: **marca-se a imagem** com números sobre cada região/controlo e
o modelo passa a responder *"o 7"* em vez de *"x=847, y=612"*. Medido no paper da Microsoft
(arXiv 2310.11441): pedir coordenadas ao GPT-4V dá **25,7 %**; com as marcas, **86,4 %** — sem
treinar nada. Escolher entre opções etiquetadas é uma tarefa de leitura; é isso que um modelo de
linguagem faz bem. E as etiquetas são feitas por **nós**, com UI Automation (exacto) — a parte
difícil sai do modelo e passa para o nosso código.

### UI Automation — o "DOM do Windows" (verificado 2026-09-17)

O equivalente nativo do CDP existe, vem com o sistema, e a Microsoft **publica-o para agentes**. O
CLI `winapp ui` descreve-se textualmente como *"Inspect and interact with running Windows
applications from the command line. Used by AI agents and developers for UI testing, debugging, and
automation."* — e o formato é o mapa que se lê no preview:

    btn-minimize-d1a0 "Minimize" (1222,206 48x48)
    btn-close-d1a2    "Close"    (1318,206 48x48)

Nome, caixa e selector. Os selectores têm três qualidades, por ordem: **AutomationId** (posto pelo
programador; sobrevive a layout, tradução e reestruturação — o preferido), **slug** gerado
(`btn-close-d1a0` = tipo + nome normalizado + hash de 4 chars do RuntimeId, que ao mesmo tempo serve
de deteção de obsolescência: elemento substituído dá *"Element may have changed. Re-run inspect."*)
e **texto** (substring em Name/AutomationId). Quando a pesquisa cai num elemento não invocável, o CLI
sobe ao **antepassado invocável** mais próximo e mostra-o — a mesma ideia do `closest()` no DOM.

**DUAS FAMÍLIAS DE VERBOS, e a distinção é decisão de desenho:**

| Família | Verbos | Preço e limites |
| --- | --- | --- |
| Padrões UIA | `inspect`, `search`, `get-property`, `get-value`, `wait-for`, `set-value`, `invoke`, `scroll --direction/--to`, `screenshot` | **Não injeta input.** A doc marca-os como *headless/locked-session friendly* e recomenda-os em CI |
| Injeção de input | `click`, `hover`, `drag`, `touch`, `pen`, `send-keys --via send-input`, `scroll --wheel` | Exige **desktop interativo e desbloqueado** com a janela em primeiro plano. Falha explicitamente: `no_interactive_desktop`, `foreground_not_target`, `no_target`, `target_moved` |

`invoke` tenta os padrões por ordem: InvokePattern -> TogglePattern -> SelectionItemPattern ->
ExpandCollapsePattern. Os verbos de gesto **re-resolvem o alvo imediatamente antes do clique** e
falham com `target_moved` em vez de acertar no vazio — a mesma regra que o `caixaDoPedido` do
`preview-cdp.js` já aplica no CDP. E o `screenshot` lê pela **Windows.Graphics.Capture (WGC)**, a
superfície composta pelo DWM: **funciona com a janela tapada por outra**, o que o `tool_capturar_print`
atual não faz (ele lê o ecrã, logo uma janela tapada não aparece). Tem ainda `screenshot <seletor>`,
que corta pela caixa do elemento.

**CORREÇÃO AO QUE SE DIZ SOBRE ISTO:** a árvore **não** está "sempre a correr em segundo plano". A doc
diz o contrário — *"Parts of the UI Automation tree are built as a client needs them, and the structure
of the tree changes as elements are added, moved, or removed"* — e acrescenta que raramente se vê a
árvore inteira porque pode ter milhares de elementos. O que está sempre presente é o **motor**
(`UIAutomationCore.dll`); a árvore constrói-se por pedido, através dos *providers* de cada programa.
Daí a hierarquia real: só expõe estrutura quem implementa provider (WPF, WinForms, Win32, WinUI 3,
Electron, Qt com plugin). **Tkinter com Tcl 8.6 não expõe nada** (ver TIP 733) e um controlo desenhado
à mão é, para a árvore, um retângulo — exatamente o limite do canvas. E "precisão de 100%" também não:
a *medição* é exata, mas a *ação* pode falhar por elevação (UIPI), foco ou alvo em movimento — está na
tabela acima, nos códigos de erro.

### Porque é que isto não se confunde com o computer use

A API do Gemini tem hoje uma ferramenta `computer_use` (ambientes browser/mobile/desktop) que devolve
`click`/`type`/`press_key`/`drag_and_drop`/`scroll`/`take_screenshot` com coordenadas **normalizadas
0-999** e um campo `intent` a explicar cada ação. É real e é bom — mas é uma capacidade **do modelo**
(grounding), não um harness, e não se cola ao DeepSeek: para a usar teríamos de passar a rotear o
agente por um modelo Gemini.

O que interessa reter é o **vocabulário**, porque é genérico e implementável por nós: é a mesma lista
de verbos da tabela acima. A diferença está no alvo — eles resolvem-no **por píxel normalizado**
(adivinha), nós resolvemo-lo **por nome** (mede). Note-se que no ambiente desktop deles não existe
`inspect` nem árvore: é o mesmo caminho dos 25,7 %.

Fica como **opção futura registada, não como dívida**: se um dia for preciso grounding a sério (um
canvas sem API, um jogo), a única via honesta é um modelo que o tenha — e isso é uma decisão de
*provider* (o `google-genai` já está nas dependências para o provider Gemini das Configurações), não
uma ferramenta nova. O que **não** se faz é prometer grounding que o modelo não tem.

### A ordem, agora que os três veículos estão nomeados

1. **Código** (IFC, DXF, bpy, Ruby do SketchUp, Python do Unreal) — faz o efeito; verifico medindo.
2. **Estrutura** — CDP/DOM onde há página, **UI Automation onde há moldura nativa**. Alvo por nome,
   zero adivinhação, e — nos verbos de padrão — sem sequer injetar input.
3. **Píxel + marca** — só onde a árvore devolve um retângulo opaco (canvas de CAD, viewport 3D, jogo).

---

## Decisões que não se desfazem

- **Localizar pela estrutura, não pelo pixel.** O preview é Electron, logo tem o Chromium dentro,
  logo tem o CDP: o DOM responde com a coordenada exata, ninguém adivinha. Do lado nativo o
  equivalente existe e tem nome — **UI Automation** —, por isso "app nativa" **não** significa
  "clicar por pixel": significa que o veículo da estrutura muda. O pixel só entra onde não há
  estrutura nenhuma (jogos, canvas de CAD, viewport 3D).
- **Preferir sempre os verbos que NÃO injetam input.** Em UI Automation, `invoke`/`set-value`/
  `get-value` operam por *padrões* e funcionam com o ecrã trancado e sem roubar o rato ao utilizador;
  `click`/`drag`/`send-keys` injetam input no sistema e exigem desktop desbloqueado em primeiro plano.
  O gesto sintético é o último recurso, pela mesma razão que o pixel: rouba o rato ao utilizador e
  depende de um estado que não controlamos (janela em primeiro plano, sessão desbloqueada). Note-se
  que ele **falha de forma explícita**, não em silêncio — `foreground_not_target`, `target_moved` —,
  o que é bom desenho e o que o torna aceitável como último recurso. Vale igualmente no CDP, onde o
  `Input.dispatchMouseEvent` só entra quando o `DOM` e o `Runtime.evaluate` não resolvem.
- **Uma capacidade genérica, zero ferramentas por software.** Não existe (nem vai existir) um
  `tool_desenhar_parede_autocad` ou um `tool_modelar_blender`. As ferramentas são poucas e universais
  — correr código, ler a estrutura, verificar o resultado, lembrar — e o que é **por software é a
  MEMÓRIA**: as APIs, as convenções e os erros de cada programa acumulam-se em notas por programa e por
  projeto. É menos código e mais conhecimento. O plugin antigo do AutoCAD tinha ~30 métodos escritos à
  mão para *um* programa; aqui o equivalente é uma nota que cresce, serve qualquer IFC, Blender,
  SketchUp ou Unreal, e não precisa de ser escrita por ninguém.
- **Nunca pedir coordenadas ao modelo.** É o erro original do plugin do AutoCAD (25,7 % medidos).
  O modelo declara **relações e intenção**; quem calcula os números é código determinístico. E onde a
  estrutura existe, o modelo não aponta: **escolhe** — a imagem leva marcas numeradas feitas por nós
  (Set-of-Mark, 86,4 %), e responder "o 7" é leitura, não geometria.
- **Verificar é medir o resultado, não olhar para ele.** Um "terminei" não é prova (aviso da própria
  OpenAI) e geometria no sítio errado não lança exceção. Lê-se o resultado de volta — DXF, DOM,
  imagem renderizada — e compara-se com o que se pediu.
- **`WebContentsView`, nunca `BrowserView`** — este morreu no Electron 29. O projeto está em 44.3.0.
- **O preview sabe o que o ficheiro é.** É isso que o distingue do preview do Codex: ele deteta o
  ponto de entrada e lê a porta do próprio processo, em vez de obrigar o utilizador a escrever o endereço.
- **Canal IPC que manda numa view nativa filtra por `sender`.** O Axio pode estar a correr dentro do
  próprio preview — e os canais IPC são globais no processo principal. Foi isto que fez o preview
  sumir-se a si mesmo.
- **Texto local nunca entra no buffer do PTY** (regra do terminal, mantém-se).
- **A ponte é um servidor HTTP local com token, não IPC.** O Python não fala IPC com o Electron: as
  ferramentas escrevem num servidor efémero que o processo principal abre em `127.0.0.1` no
  arranque, com token aleatório por sessão e só a aceitar pedidos de casa. É de mão única (o Python
  pergunta, o Electron responde), por isso não guarda estado nenhum. A porta e o token viajam no
  ambiente do Flask, que é o próprio `main.js` quem o spawna.
- **O depurador e o DevTools do preview não coexistem** no mesmo `webContents`: abrir o DevTools
  desliga o canal, e o evento `devtools-closed` volta a ligá-lo.

## Limites conhecidos (não são bugs)

- Um ficheiro **fora** da raiz do projeto carrega por `file://`, mas continua nu (a rota `/preview/`
  só serve o que está dentro da pasta do projeto).
- Em modo Node (necessário para o Axio funcionar dentro do preview), uma página **remota**
  maliciosa teria acesso ao Node. É por isso que existe a classificação por classe de alvo.
- A view nativa **tapa o DOM**: um balão de contexto que caia sobre a área do preview não se vê.
  O código esconde o preview; não põe o DOM por cima. Anotado para o 4.3.
- Uma app de **janela nativa** não é embutida por `SetParent` no Windows 11 local (o compositor
  derrota a operação). O caminho é o `DwmRegisterThumbnail`, na 4.5.
- O `Runtime.evaluate` corre na página **viva**: se ela navegar a meio de um pedido, o comando falha
  ("contexto inválido") em vez de responder com dados de outra página. Pedir de novo chega.
- Uma página carregada **sem a vista do preview à frente** mantém o tamanho da janela, não 1×1: com
  um viewport de 1×1 o layout colapsa e o DOM responde com coordenadas negativas — o CDP ficava a
  medir uma página que não existe. É para isso que serve `main.js:limitesDeArranque`.
- A consola e a rede são **esvaziadas a cada navegação**: o que fica é sempre da página que está lá.
- O cursor desenhado só aparece com a vista do preview à frente (é para os olhos do utilizador) e não
  sobrevive a uma navegação — é um elemento da página, e a página nova não o tem.
- Um print de uma região **fora da área visível** não é capturado — o `clip` é relativo à janela.
  Role a página primeiro (`avaliar` com `window.scrollTo`).
- As ferramentas do preview dependem da ponte: um Flask nascido antes desta mudança responde com o
  aviso de "feche e reabra o Axio", em vez de falhar em silêncio.

## Dívida aberta (fora do plano, à espera de decisão)

- **~~A interface dependia de CDNs externos~~ (RESOLVIDO a 2026-09-17).** Os três recursos que vinham
  pela rede saíram. O highlight.js e o seu tema estão vendorizados em `src/frontend/vendor/highlight/`
  e são servidos pela rota nova `/vendor/<path:p>` (`routes/static.py:serve_vendor`); o Tailwind
  passou a **CSS estático compilado no build**: `src/frontend/css/tailwind.entrada.css` + `tailwind.config.js` →
  `src/frontend/css/tailwind.css`, por `npm run build:css`.
  As medições que decidiram o desenho: (a) o `cdn.tailwindcss.com` era o **Tailwind 3.4.17**, logo a
  versão foi **fixada em 3.4.17** — o v4 muda defaults (a cor das bordas passa a `currentColor` e o
  `ring` de 3px para 1px) e isso deslocaria o layout **sem aviso**; (b) o scan não perde nada porque
  em todo o frontend há **uma única** classe construída em tempo de execução (`markdown.js:23`, e é
  HTML literal); (c) o `<style>` do Play CDN entra na **posição 17 do `<head>`, depois de todos os 12
  stylesheets** — o `<link>` do CSS compilado tem de ficar no mesmo lugar, senão a cascata inverte.
  Prova: com o CSS servido do disco, **0 divergências em 20 elementos** (geometria, cor, display,
  padding, z-index) contra a página a correr com o CDN. Custo: 407 KB de JS → **21 KB** de CSS.
  Ficou **zero `https://`** no `index.html` (a única ligação externa é documentação, para clicar, não
  um recurso). O `paint.py` continua a avisar na `_classes_fora_do_css` que uma medida vinda de uma
  classe que o CSS compilado não tem mente em silêncio — agora há um sítio onde a confirmar.

- **A porta deixou de estar cravada no frontend (FEITO a 2026-09-17).** Eram **32 sítios em 12
  ficheiros** a escrever `http://127.0.0.1:5000` à mão; hoje fala com a **própria origem**:
  `state.API = location.origin` (`editor/state.js:3`) é a origem única dos caminhos que se calculam
  (Monaco, workers, `io()` do socket.io) e as URLs literais passaram a relativas (`/api/...`) — 0
  ocorrências da porta no frontend e nenhum `const API` local. O `EventSource` do chat
  (`messages.js`) segue pela mesma regra. `index.html:7-8` carrega Monaco e xterm por `/monaco/...` e
  `/xterm/...`.
  PROVA AO VIVO (pelo preview, sem reiniciar nada): na 5000, 30 pedidos, todos a
  `http://localhost:5000`, consola limpa; **servida de outra porta (5123)**, o módulo responde
  `state.API === location.origin === http://localhost:5123` e todos os pedidos passam a levar 5123
  (404, porque ali não há backend). É essa a prova que interessa: seguem a origem, não uma porta.
  ARMADILHA: há **dois** módulos `state` — `chat/state.js` (estado do chat) e `editor/state.js` (este,
  com o `API`). `state.API` só existe no segundo; usá-lo a partir do chat escreve
  `/undefined/api/...` e a interface fica meio muda sem gritar (foi o que a prova ao vivo apanhou).
  O que falta para a 2.ª instância funcionar a sério: `app.py:54` continua `port=5000` (precisa de
  aceitar uma env var) e o arranque (`limpar_temporarios_orfaos`, `preaquecer_mempalace`) precisa de
  guarda, senão dois processos mexem nos mesmos temporários e no mesmo vetor.

## Como testar (após reiniciar o Axio)

O `main.js` é o processo principal: **Ctrl+R e Ctrl+Shift+B não chegam — fechar e reabrir o Axio.**

1. Ícone do preview na barra de cima → escrever `localhost:5000` (o Axio a ver-se a si próprio).
2. Duplo clique num `.html` da árvore.
3. **4.2:** abrir um projeto com servidor e dar play no card dele — a página deve nascer no preview
   sozinha, e o card ganha um globo no cabeçalho.
4. **4.3 / 4.4 (o meu ciclo de teste, sem passar por si) — provado a 2026-09-16, ampliado a 2026-09-18:**
   carregar `localhost:5000` com `tool_operar_preview` e **começar por `acao='mapa'`** — devolve numa só
   chamada o índice de tudo o que responde a um gesto (seletor, rótulo, coordenada), já sem os que estão
   tapados por outro elemento, fora da janela ou sem nome: é o "dicionário" da página, e evita andar a
   perguntar elemento a elemento. Depois ler `acao='consola'` (erros da página com ficheiro e
   linha), `acao='rede'` (pedidos que falharam), `acao='elemento'` com um seletor (`#btn-send`) e
   `acao='print'` de um retângulo estreito; depois `acao='clicar'` / `acao='escrever'` no seletor que
   o `elemento` devolveu — com a vista do preview à frente, o gesto aparece com o cursor verde. Para
   esvaziar um campo: `acao='escrever'` com `limpar=true`. Para **substituir** o conteúdo, mande
   `limpar=true` com o `texto` novo; sem `texto`, esvazia-o (o Delete cai sobre a seleção). A seleção
   sai de `select()`/range quando o campo é nativo ou `contenteditable` e de um **Ctrl+A despachado
   pelo CDP** quando não é — o caso dos editores com EditContext (o Monaco), onde o `select()` do DOM
   não existe: sem o Ctrl+A o texto novo entrava no cursor, a somar ao antigo (medido a 2026-09-17). Um alvo com caixa 0x0 só é recusado quando **não** é superfície de
   entrada (`document.activeElement`, `INPUT`/`TEXTAREA`/`SELECT`, `contentEditable` ou `editContext`) — o campo do Monaco mede 0x20 de largura e era recusado por engano. Há ainda
   um caminho **sem seletor**: `acao='escrever'` só com `texto` escreve no elemento que está em foco e di-lo. Se `acao='estado'` disser que não há ponte, o Axio foi aberto
   antes desta mudança.
   **Lote (a via rápida):** quando a sequência já é conhecida de antemão, `acao='roteiro'` com `passos`
   (JSON) corre vários gestos numa só chamada — ex.: `[{"acao":"clicar","seletor":"#btn-workspace"},
   {"acao":"escrever","seletor":"#term-input","texto":"echo oi","limpar":true},{"acao":"teclar","tecla":"Enter"}]`.
   Cada passo passa pelo mesmo caminho de um gesto isolado (alvo recalculado no instante, recusa se
   tapado ou 0x0, efeito medido) e o roteiro **para no primeiro que falhar**, para os seguintes não
   agirem sobre uma página que já não está no estado previsto. Máximo de 12 passos por roteiro.
5. **Verificar frontend acabado de editar:** `tool_operar_preview` com `acao='recarregar'` — recarrega
   **ignorando a cache** (`Page.reload {ignoreCache: true}`), para eu não estar a medir uma versão
   velha. A cadeia de reinícios que fica: JS/CSS/HTML → eu verifico no preview sozinho, o `Ctrl+R` é
   só para a sua janela apanhar o novo; backend Python → `Ctrl+Shift+B` (mata a rodada em curso, logo
   é sempre seu); `main.js` e `preview-cdp.js` → fechar e reabrir, porque nada dentro do processo o
   recarrega.
