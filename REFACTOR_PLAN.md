# Plano de Refatoracao — Axio Coder

> **Estado: refatoracao estrutural FECHADA.** Este documento passou a ser o mapa do que existe e a
> lista curta do que fica em aberto (§2). Nao reescrever aqui fases concluidas: o historico nao decide
> nada. O que estava decidido (registry, god objects, clone de padrão) esta feito e provado.

## 1. Estado real (medido, nao estimado)

> **Medicao de 2026-09-12**: os numeros desta seccao sao o retrato daquele dia, nao o de hoje
> (a tabela envelheceu - ha mais modulos e ferramentas agora). Para o estado vivo use
> `tool_auditar_estrutura`; o que continua verdadeiro sao os DESENHOS e as decisoes, nao as contagens.

| Camada | Situacao |
|---|---|
| `src/backend/` | **56 modulos `.py`** (+6 `__init__.py`) / **13 941 linhas** · jscpd **0 clones** · 0 imports orfaos, faltantes ou dead code · **camadas: 21 arestas, 2 inversoes** (1 excepcao declarada, §2.7) |
| `src/backend/tools/` | **27 ficheiros** (26 modulos + `__init__.py`) · **52 ferramentas registadas** · 0 clones · auditoria estrutural **0 defeitos** (§2.6) |
| `src/frontend/js/` | 28 ficheiros JS (ESM) / 10 200 linhas · jscpd **1 clone** (0,05%, aceite — §2.2) |
| `src/frontend/css/` | `style.css` (363) + 5 folhas (`dock` 302, `contexto` 201, `workspace` 212, `editor` 814, `geral` 368) = **2260 linhas** — split por tema, §3.4 |
| `app.py` (raiz) | entry point do Flask, 44 linhas; na raiz **por design** (§3) |
| Carregamento | `index.html:597-608` — `<script type="module">`; **nenhum script classico** |

```
coder/
├── app.py                      # entry point Flask: env -> blueprints -> socketio.run
├── data/                       # icons, entities.json, glossary.json, mempalace.yaml, settings.json
├── src/
│   ├── main.js                 # Electron main
│   ├── backend/
│   │   ├── config.py           # APP_ROOT, DATA_DIR, carregar_env
│   │   ├── extensions.py       # instancias Flask/SocketIO
│   │   ├── state.py            # estado global + emit_event + .axio/ (no_diretorio_do_axio)
│   │   ├── ai/                 # base, gemini, deepseek, context, instructions, loop, atrito
│   │   ├── memory/             # store, vector, glossary, manutencao, mempalace_patch
│   │   ├── tools/              # registry + 26 modulos de ferramentas (§2.1)
│   │   ├── routes/             # chat, editor, files, session, terminal, settings, static (blueprints)
│   │   └── services/           # file_service, file_watcher, session, diff, process_manager,
│   │                           # settings, persistencia (gravacao atomica de JSON)
│   └── frontend/
│       ├── index.html, style.css + css/   # 5 folhas por tema: dock, contexto, workspace, editor, geral
│       └── js/{chat, editor}/  # 28 modulos ESM (nesta ronda: chat/col3_views.js, question_panel.js, attach.js)
└── REFACTOR_PLAN.md            # este ficheiro
```

## 2. O que fica em aberto (honesto)

### 2.1 Corte do `tools/filesystem.py` — CONCLUIDO
O maior ficheiro do backend (42,7 KB, 20 das 48 ferramentas) deixou de existir. Os 30 simbolos de topo
foram recortados **byte a byte** (AST, decoradores `@register` incluidos) para 6 modulos por dominio:

| Modulo | Ferramentas | Nota |
|---|---|---|
| `tools/browse.py` | 3 | listar pasta/arvore e pesquisar texto no projeto |
| `tools/read.py` | 5 | mapa, ficheiro, trecho, assinaturas, clangd |
| `tools/edit.py` | 3 | substituir (uma/todas), salvar; `gravar_edicao_com_diff` e o ponto unico de gravacao |
| `tools/plan.py` | 4 | planejar/iniciar/atualizar plano (+ etapa extra) |
| `tools/trash.py` | 2 | apagar (recuperavel) e listar lixeira |
| `tools/undo.py` | 3 | desfazer/refazer/consultar a pilha |

Prova: `_teste_fs.py` (ja na lixeira) num **processo Python novo** — 24/24 PASS, com **despacho real**
das 20 ferramentas movidas (leituras, escrita+undo+redo, recusa de caminho protegido, tools de plano,
clangd em falha graciosa) e o registo intacto em 48. Os imports de cada modulo foram deduzidos por uso
real e a auditoria apanhou os 2 `FALTANTE` antes de qualquer execucao.

Maior ficheiro do backend agora: `comments.py` 31,8 KB (segue `refactor.py` 25,4 KB).

### 2.2 `messages.js` — startSSE partido; markdown extraido para `chat/markdown.js`
`startSSE` tinha **778 linhas** (um `onmessage` com 18 ramos `if/else if` + funcoes aninhadas). Agora:

- `chat/plan_cards.js` — construtores puros (cards de plano/stack, icones, formatacao de status): nao
  tocam no estado do turno nem em globais; recebem tudo por argumento.
- `chat/escape.js` — `escapeHtml`, ponto unico de escape. **`messages.js` continua a re-exporta-lo**,
  que e o que `files.js`, `history.js` e `inspect.js` importam (contrato mantido de proposito).
- `messages.js` — estado do turno promovido a nivel de modulo (ha um unico SSE por app) + **18 handlers**
  (`tratar_<evento>`) + mapa `HANDLERS` + `resetEstadoDoTurno()`. `startSSE` ficou com **26 linhas**.
- Ramo com duas condicoes (`tool_used || ai_thought`) virou um handler que o mapa aponta duas vezes.

Prova: ESLint **0 erros** na pasta `chat` (nenhum `no-undef` = nenhuma referencia quebrada) e jscpd 0
clones nos ficheiros novos.

**Fechado nesta ronda (2026-09-12):** o cluster de markdown
(`formatMessage`/`formatInlineText`/`processInlineBlock`/`renderTableBlock`/`isTableSeparator`/
`splitTableRow`/`formatInline`) saiu para **`chat/markdown.js`** por recorte verbatim (133 + 11 linhas),
com `escapeHtml` vindo de `chat/escape.js`; o `messages.js` importa-o e continua a re-exportar os mesmos
nomes. Prova: ESLint 0 erros na pasta `chat` e jscpd 0 clones novos (o unico clone da pasta continua a
ser o `messages.js` x `renderer.js` de §2.4).

**Numero corrigido:** o `messages.js` tem **1172 linhas** (nao 734). O 734 andou errado neste ficheiro
desde o inicio — nunca bateu com o clone em `messages.js:845` da §2.4. A versao real no disco tinha
**1303 linhas** antes desta ronda (144 sairam para o markdown). Continua a ser o maior ficheiro do
frontend; o candidato natural a proxima ronda e o par `addMessage`/`addImage` (DOM + listeners, nao
markdown, e por isso nao cabiam nesta extracao).

### 2.3 `ai/loop.py` — `loop_raciocinio_ia` 410 → 297 → **246 linhas**
5 helpers extraidos por recorte verbatim (nao redigitados): `_emitir_status_da_ferramenta`,
`_registar_resumo_da_ferramenta`, `_extrair_pensamentos_e_textos`, `_montar_bloco_continuidade`,
`_montar_config_do_turno`. Prova: `_teste_loop.py` (na lixeira) num processo novo — **17/17 PASS** com
objetos falsos (separacao pensamento/texto, `reasoning_content`, `<think>`, config nos 3 modos, status
por ferramenta, resumo truncado). O teste apanhou 1 defeito real antes do restart: a config usava
`instrucao` (variavel do chamador), que passou a ser parametro.

**Fechado nesta ronda (2026-09-12):** a coleta de contexto concorrente (as duas funcoes aninhadas
`_buscar_memoria`/`_coletar`, as 4 tarefas, as threads e a animacao de fases do status) saiu **verbatim**
(53 linhas, linhas 260-312 do ficheiro de entao) para **`ai/coleta.py`**:
`coletar_contexto(prompt_usuario, wing_atual, palace_path)` devolve
`{"projeto","memoria","ai_memory","codigo"}` e o `loop.py` chama-a numa linha. Os 6 imports que ficaram
orfaos foram removidos (a auditoria AST confirmou). Prova: `_teste_final.py` (na lixeira) num processo
novo — registo intacto em 48 ferramentas, `loop_raciocinio_ia` com 246 linhas e **chamada real** da
funcao, que devolveu as 4 fontes.

**Ainda em aberto (opcional):** o ciclo de `function_calls` (dispatch + `function_response` +
cancelamento a meio) continua dentro da funcao principal. Extrai-lo obriga a transformar 2 `return` de
cancelamento em sinal de retorno e a passar 3 variaveis mutaveis — risco real no motor da IA, sem o ganho
de clareza equivalente ao desta ronda.

### 2.4 Duplicacao (aceite por decisao)
1 clone (0,08%): `messages.js:860` x `renderer.js:367` — so o esqueleto do `forEach` (iterar tools →
iterar chaves ordenadas). O corpo diverge por completo: um monta HTML, o outro monta texto de clipboard.
Extrair exigiria 2 callbacks para poupar 3 linhas de *estrutura*: abstracao prematura, nao copy-paste.
(O clone do rename inline em `editor.js` foi resolvido com `iniciarRenameInline`; um clone novo de
docstrings nos 6 modulos do corte foi eliminado na hora, com texto unico por modulo.)

### 2.5 Varredura final do backend (2026-09-12) — FECHADO
Varrimento modulo a modulo dos 54 ficheiros, sem leitura ficheiro a ficheiro: um script temporario
levantou, para cada modulo, itens de topo com linhas, nomes repetidos entre modulos, funcoes nunca
usadas fora do proprio modulo, **privados importados por outro modulo**, o grafo de imports
pasta-a-pasta, as 50 ferramentas registadas, wrappers de <=3 linhas e **corpos com AST identico**
(compara duplicacao que o jscpd deixa passar abaixo de 6 linhas).

Limpo: **0 nomes de topo repetidos entre modulos**, **0 funcoes publicas orfas**, **0 clones**,
**0 imports faltantes/orfaos/dead code**, 50/50 no registo. Nove defeitos reais, todos corrigidos:

| Achado | Correcao |
|---|---|
| `tools/scan.py` era um modulo de 16 linhas para **1 helper privado** importado por 2 auditores | o helper virou **`services/file_service.arquivos_recursivos`** (publico, junto de `entradas_diretorio`) e o `scan.py` foi apagado |
| `tools/lint.py` albergava `_run_com_timeout` e o `similarity.py` importava-o de la (um auditor a depender do modulo de linters) | desceu para **`tools/process.run_com_timeout`**, ao lado do `matar_arvore` que ele proprio usa: a dependencia `similarity -> lint` deixou de existir |
| `comments.py` importava **8 simbolos privados** do `comments_lexer` (a "camada pura" sem API desenhada) | API explicita: `detetar`, `montar_comentarios`, `resumo`, `sha`, `modo_de`, `linguagem_de`, `IGNORAR_PASTAS`, `TIPOS_DE_COMENTARIO` |
| `registry._resolver_kwargs` importado pelo `selfcheck` | **`registry.resolver_kwargs`** |
| `glossary._achar_linha_identificador` / `_caminho_do_arquivo` e `store._coletar_notas_knowledge` importados pelo `manutencao` | os tres passaram a publicos |
| `mempalace_patch._client_cache` / `_client_lock` importados pelo `vector` | **`client_cache` / `client_lock`** — o patch PARTILHA o `PersistentClient` com o vetor; o underscore escondia que era API |
| `routes/editor.py`: `undo` e `redo` com o mesmo corpo de 7 linhas | **`_undo_redo(aplicar)`**; cada rota ficou com 1 linha |
| `routes/static.py`: 5 rotas + `socket.io` a repetir `send_from_directory` | **`_servir_pasta(subpasta, alvo, mimetype)`**; as 6 rotas ficaram com 1 linha |
| `lint.py` com `import subprocess` orfao depois do movimento | removido (a auditoria AST apanhou-o) |

**Falsos positivos do detector de corpos identicos, aceites com motivo:** `settings.obter_settings` x
`static.glossary_list` (ambos `jsonify(load_X())`, mas de fontes diferentes) e
`comments_lexer.modo_de` x `linguagem_de` (dicionarios diferentes; mesclar para poupar uma linha
esconderia qual e qual).

**Licao:** o grafo de imports por PASTA nao denuncia nada disto — o sinal forte e o mapa de **simbolos
privados atravessando a fronteira do modulo**. Um "modulo puro" criado por split continua a ser um
modulo mal desenhado enquanto a API nao for declarada.

Prova: `_teste_varredura.py` (ja na lixeira) num **processo novo** — **59/59 PASS**: import dos 16
modulos tocados, presenca dos simbolos novos e ausencia dos antigos, `tools/scan.py` inexistente, 7
rotas estaticas + as 2 rotas mescladas respondendo **200 no `test_client` real**, 50/50 no registo e 3
ferramentas exercitadas por **despacho real** (comentarios listar+remover, imports js/py, codigo).

### 2.6 Varredura estrutural REPETIVEL (2026-09-12) — FECHADO
O script temporario de ~200 linhas que fez o §2.5 virou ferramenta permanente: **`tool_auditar_estrutura`**
(`src/backend/tools/structure.py`, registada por efeito de import em `ai/loop.py`). Varre uma pasta
(padrao `src/backend`) e devolve **veredito por modulo**, separando **DEFEITO** (contradiz o desenho:
orfa nunca usada, privado importado de outro modulo, corpo identico por AST, nome publico repetido) de
**AVISO** (decidivel: publica usada so dentro do modulo -> candidata a privada, wrapper de <=3 linhas,
corpo semelhante com literais diferentes).

Veredicto medido nos **56 modulos / 13 941 linhas**: **0 defeitos**, 18 modulos so com avisos, 38 limpos.
As unicas "orfas" sao publicas usadas so dentro de casa (`raiz_repositorio`, `caminho_na_revisao`,
`aplicar_snapshot`, `caminho_original_lixeira`, `parar_watcher`, `carregar_shell_persistido`,
`reparar_json_truncado`, `primeira_aparicao_por_arquivo`, `indexar_codigo_incremental`,
`buscar_codigo_semantico`): **nao e dead code**, e API a mais — nenhuma foi renomeada.

**Falsos positivos que a 1a versao da ferramenta cometeu (e que a 2a corrige):** privado cruzado por
HOMONIMO (`_relatorio` em `graph.py` x `structure.py`; `_declaracoes` em `js_imports.py` x `selfcheck.py`
— cada modulo tem o seu) so conta com **import explicito**; corpos com literais normalizados davam
"identico" falso nos wrappers que chamam a mesma funcao com argumentos diferentes (`serve_index` x
`serve_style_css`) -> passou a haver hash **estrito** (defeito) e **tolerante** (aviso); referencias so
dentro de `src/backend` faziam orfas FALSAS de tudo o que o `app.py` chama -> o `app.py` entra agora nas
referencias; `len(texto)` e caracteres, nao linhas (a 1a versao dizia "14640l" para um ficheiro de ~146).

**Relatorio afinado (3 passagens, 2026-09-12):** o cabecalho passou a trazer os TOTAIS do projeto
(`56 modulos .py em 6 pastas | 13 941 linhas | N caracteres | F funcoes | K classes`) e cada pasta a
mesma quebra com o proprio total (`--- src/backend/tools/  (26 modulos, 6803 linhas, F funcoes,
K classes)`), respondendo "quantos modulos, pastas, linhas, caracteres, funcoes e classes" numa unica
chamada (contagem unica em `_contagem_de_itens`);
e a antiga `MODULOS DE tools/ SEM FERRAMENTA REGISTADA` virou **`MODULOS DE tools/ DE APOIO (sem
@register, por desenho)`**, sem despejar a lista de simbolos: os 2 casos (`registry.py`,
`comments_lexer.py`) sao infraestrutura e camada de leitura, e um modulo que ESQUECA o `@register`
continua a sair como **funcao orfa** (DEFEITO) — a suspeita nao se perde, o ruido sim. Medicao desta
passagem: **56 modulos / 13 941 linhas** (`ai` 1610, `memory` 1864, `routes` 1504, `services` 1956,
`tools` 6803, raiz do backend 204) e **0 defeitos, 18 avisos, 38 limpos**; maior ficheiro
`services/file_service.py` 789l. Provado por 12/12 PASS num processo novo (a contagem do relatorio casa
com a contagem direta do ficheiro, a soma das pastas fecha no total geral, a lista de maiores nao
truncou) — `_teste_relatorio.py`, ja na lixeira.

### 2.7 Dependencias entre camadas (2026-09-12) — FECHADO
Faltava fechar a unica parte do script do §2.5 que nenhuma ferramenta cobria: o **grafo de imports
entre pastas**. A `tool_auditar_estrutura` ganhou-o com uma **politica de camadas declarada** —
`raiz < services/memory < tools < ai < routes`. Importar de uma camada ACIMA da propria vira
**DEPENDENCIA INVERTIDA** (aviso no modulo consumidor); importar do mesmo nivel (`tools -> tools`,
`memory -> memory`) e desenho normal e nao gera achado nenhum. Sem politica declarada o grafo era so
uma tabela de contagens; com ela passa a acusar "peca no modulo errado".

Quatro inversoes reais encontradas, duas corrigidas:

| Achado | Correcao |
|---|---|
| `memory/glossary.py:5` importava `tools.registry.register` — a ferramenta `tool_gerenciar_glossario` vivia na camada de memoria | a ferramenta passou para **`tools/memory_tools.py`** (onde ja viviam as outras duas de memoria); `normalizar`, `normalizar_lista` e `identificador_concreto` passaram a API publica do glossario (eram privados, usados so pela ferramenta) |
| `services/process_manager.py:9` importava `tools.process.montar_env_processo` | **`montar_env_processo` desceu para `services/process_manager.py`** (usa `services.file_service.venv_projeto`, ja da mesma camada); `tools/process.py` e `routes/terminal.py` importam-no agora de services |

**Excepcao declarada (revista, nao corrigida):** `services/settings.py:68-69` importa, dentro de
`save_settings`, `ai.deepseek.reset_deepseek_client` e `ai.gemini.reset_gemini_client`. E import tardio
obrigatorio: `ai.gemini`/`ai.deepseek` leem as chaves de `services.settings`, logo um import no topo
seria um ciclo real. A alternativa (registo de callbacks na camada de IA) troca duas linhas de import
tardio por indireccao e estado de arranque — custo maior que o problema. E a UNICA inversao tolerada.

Veredicto re-medido depois dos movimentos (**55 modulos / 13 700 linhas**): **0 defeitos**, 18 modulos
so com avisos, 37 limpos, **21 arestas** entre pastas e **2** inversoes (a excepcao acima) — eram 23
arestas e 4 inversoes. O §2.6 media 17 avisos / 38 limpos.

Prova (`_teste_final.py`, processo novo): **30/30 PASS** — imports dos 6 modulos tocados, `memory.glossary`
sem QUALQUER import de `src.backend.tools`, os 3 helpers publicos presentes e os antigos removidos,
`tool_gerenciar_glossario` a responder pelo **despacho real** (listar 48 termos, filtro critico a recusar
identificador generico, remover inexistente sem escrever), `montar_env_processo` a ser o MESMO objecto
em `services.process_manager` e `tools.process` (que deixou de importar `venv_projeto`), o env com
`PORT`/`FLASK_RUN_PORT` e o venv no `PATH`, `_pty_env()` do terminal a responder, 51 ferramentas no
registo e a ferramenta exposta ao modelo. A `acao='verificar'` do glossario foi corrida no mesmo
processo: corrigiu 2 linhas (o seletor composto `3 -> 13` e `detectar_shell 45 -> 47`, deslocado pelos
imports novos) e, re-corrida, reporta **0** — o glossario ficou remedido contra o disco.

**Corolario que veio de fora do codigo:** a divisao do `style.css` (§3.4) tinha deixado 2 entradas do
glossario com o alvo mudado de ficheiro, e o glossario media mal os SELECTORES COMPOSTOS
(`#term-log .xterm > .scrollbar > .slider` era reduzido a `#term-log`, apontando para o ancestral).
`glossary._variantes_do_identificador` procura agora do mais especifico para o mais generico: remedidos
os 48 termos, 47 ja corretos e 1 corrigido (3 -> 13).

Prova: processo novo com o despacho REAL — despacho sem argumentos, cobertura 55/55 modulos (todos
nomeados por pasta), subpasta `services` (7 modulos), modo detalhado e caminho inexistente devolvendo
erro claro em vez de rebentar: **TODAS PASS**.

### 2.8 Auditoria de ROTAS HTTP (2026-09-12) — NOVO
As auditorias existentes veem codigo: imports, modularidade, dead code. Nenhuma via a **aplicacao a
responder** — e a prova disso e que a rodada anterior teve de o fazer com um script temporario
(`_teste_rotas.py`). Esse script virou ferramenta: **`tool_auditar_rotas`** (`src/backend/tools/rotas.py`,
registada por import em `ai/loop.py`).

Corre a app **num processo NOVO** (script gerado em `tempfile` no TEMP do sistema, apagado no `finally`;
`run_com_timeout` como cinto de seguranca) e faz `test_client().get()` em cada rota do `url_map` — logo
mede o **codigo do disco**, nao o que o Flask tem em memoria. Nunca invoca: rotas com parametro na URL,
rotas sem GET (POST/PUT/DELETE escrevem) e `/api/stream`, que e um `while True: yield` e penduraria a
ferramenta. Cada rota corre numa thread com `join(timeout)`: uma rota presa vira `PENDUROU` em vez de
bloquear a auditoria.

Semantica dos codigos (e o que faz o veredito ser util): **2xx/3xx = OK**, **4xx = RECUSA** (a rota
defende-se por falta de parametros, nao e avaria) e **5xx / excecao / PENDUROU = avaria**.

Medido no Axio: **52 rotas = 16 OK, 4 recusas, 0 avarias, 32 so listadas** (contagem igual ao `url_map`
real). Prova: 20 checks TODAS PASS num processo novo, incluindo os caminhos maus (sem pasta de projeto,
ficheiro sem `app`, caminho inexistente, timeout invalido) e nenhum `axio_rotas_*` deixado na raiz.

**Licao (no mesmo dia):** o gate estrutural anunciou `FUNCAO(OES) NOVA(S): correr, testar` quando o
`rotas.py` foi criado — eram `def` escritos DENTRO da string que gera o script. `syntax._nomes_funcoes`
passou a ler a **AST** (como `_imports_locais` ja fazia, pelo mesmo motivo: docstrings e strings com
exemplos de codigo), com queda para a regex quando a sintaxe esta invalida a meio de uma edicao. Regex
sobre texto nunca mais decide o que e funcao.

### 2.9 Relatorios: que ferramenta responde a que pergunta (2026-09-12)
O script de varredura do §2.5 respondia, numa so corrida, a tudo o que se perguntava sobre o backend.
A cobertura foi transferida para ferramentas — o que antes exigia um script e hoje uma chamada:

| Pergunta | Ferramenta |
|---|---|
| quantos modulos, pastas, linhas, caracteres, funcoes e classes (no projeto ou por pasta)? | `tool_auditar_estrutura` (cabecalho + linha de cada pasta) |
| inventario item-a-item de um modulo (tipo, linha, n.º de linhas, args)? | `tool_auditar_estrutura(detalhado=True)` |
| funcao orfa / usada so dentro de casa / privado importado / corpo identico / nome repetido? | `tool_auditar_estrutura` |
| grafo de imports entre pastas e inversoes de camada? | `tool_auditar_estrutura` (§2.7) |
| ferramentas registadas, nome -> modulo, colisoes, modulos por carregar? | `tool_verificar_ferramentas(detalhado=True)` |
| ficheiros, pastas, contagens por extensao, stack, versoes de pacotes? | `tool_info_ambiente` |
| a aplicacao responde em todas as rotas? | `tool_auditar_rotas` (§2.8) |
| clones de codigo (>=6 linhas)? | `tool_analisar_similaridade` |
| imports orfaos/faltantes e dead code, com escopos reais? | `tool_auditar_imports_py` / `tool_auditar_imports_js` |
| dependencias internas de UM ficheiro (o que move junto)? | `tool_mapa_dependencias` |

Consequencia pratica: deixou de se escrever script de contagem. A unica coisa que continua a exigir
processo novo e a MEDICAO do codigo que acabou de ser editado (o Flask nao recarrega sozinho). Nesse
caso o caminho e Ctrl+Shift+B e chamar a ferramenta — nunca voltar ao script temporario.

## 3. Decisoes firmes (nao reverter sem motivo)

1. **`app.py` fica na raiz** e e um entry point magro: env → blueprints → `socketio.run`. Os ~120
   imports mortos do tempo em que era factory foram removidos (a registo das ferramentas vem do
   `routes/chat.py` → `ai/loop.py`, provado com `tool_verificar_ferramentas`).
2. **`tool_aprovar_plano` MANTEM-SE** (`ai/loop.py`) — destravador do modo semi-automatico.
3. **ES Modules no frontend**. Nao voltar a `<script>` classico.
4. **`style.css` DIVIDIDO por tema (reverte a decisao anterior, 2026-09-12).** O ficheiro tinha 2260
   linhas e ja trazia 12 seccoes nomeadas por comentario `/* ===== NOME ===== */`; o split segue ESSAS
   seccoes e nao reordena uma unica linha: `style.css` (TOKENS/BASE/CHAT/LOGS = 363) + `css/dock.css`
   (302) + `css/contexto.css` (201) + `css/workspace.css` (212) + `css/editor.css` (814, a maior e um
   so tema) + `css/geral.css` (368). A ORDEM dos `<link>` no `index.html` E a ordem da cascata: mexer
   na ordem muda quem ganha, nunca reordenar. A rota e `/css/<path:p>` (`routes/static.py`, mesmo molde
   do `/chat/<path:p>`). Prova: a cauda movida (linhas 364-2260) e **byte-identica** ao `git HEAD` e a
   soma das 6 partes tem as 2260 linhas do ficheiro. Corolario: o `git HEAD` NAO servia de baseline
   completa - havia 53 bytes de edicoes nao commitadas nas 363 linhas que ninguem moveu (comentarios
   das `--dur-3`/`--dur-5`, L74/L75), por isso a comparacao honesta e a da CAUDA movida, nao a do
   ficheiro inteiro.
5. **Mover codigo = verbatim.** `tool_mover_funcao_verbatim` **nao inclui os decoradores** (provado em
   preview: reporta o `def`, nao o `@register`): em ficheiros decorados o corte em lote tem de incluir
   os decoradores por AST, com `ast.parse` antes de gravar e copia do original em `%TEMP%` para rollback.
   Corolario (2026-09-12): a resolucao por chaves **recusa** funcoes cujo corpo tem template literals +
   regex com chaves (ex: `formatInline` -> "chaves desbalanceadas"). Nesses casos usa-se
   `tool_mover_bloco_verbatim` por linhas, confirmando o intervalo com uma leitura antes de mover.
6. **Auto-melhoria (regra 26) so vale na raiz do Axio**: gate `no_diretorio_do_axio()` (`state.py`),
   bloco `MODO PROJETO` na injecao (`ai/instructions.py`) e guard no radar de atrito (`ai/atrito.py`).
   O bloco `AUTO-MELHORIA` no relatorio final **so aparece quando houve melhoria de facto**.
7. **A validacao de sintaxe do proprio Axio nao depende de ferramentas externas** (`syntax.py`:
   `compile` para Python, tree-sitter para JS/JSON/CSS/TS). Corolario: `node --check` e **tolerante** a
   ficheiros com chavetas desequilibradas — a validacao que vale para ESM e o ESLint (`no-undef`) e o jscpd.
8. **As listagens nao escondem nada em silencio** (`resumo_entradas` devolve `(visiveis, ocultos)`).
9. **Corte de cadeia `if/else` para mapa de handlers: o PROLOGO e o que se perde.** O dispatcher SSE
   (`chat/messages.js`) tinha, antes do dispatch, 4 guardas que desapareceram no corte: heartbeat/payload
   vazio (`!event.data || trim() === ''`), `try/catch` no `JSON.parse`, filtro de `turn_id` atrasado
   (`data.turn_id !== state.currentTurnId`) e a ponte `window.WorkspaceView.onSSE(data)`. Sem a ponte o
   terminal dos processos ficava MUDO e o explorer nao recarregava em `files_changed`. Antes de fechar um
   corte destes, comparar com `git show HEAD:<ficheiro>` (o dispatch 19->19 tipos estava certo; o que
   faltava era o prologo). Nem `tool_validar_sintaxe` nem o ESLint apanham comportamento ausente.
   Corolario (ferramenta, 2026-09-12): `tool_ler_trecho_arquivo(..., revisao='HEAD')` e
   `tool_pesquisar_no_projeto(termo, revisao='HEAD')` leem/procuram dentro de uma revisao git, com a
   MESMA normalizacao e a MESMA politica de ignore da busca no disco — resolve isto numa chamada em vez
   dos 5 `git grep` improvisados. 10/10 PASS (`_teste_revisao.py`, ja na lixeira).
10. **Cada operacao tem UM nucleo, e as ferramentas sao cascas finas.** Vale para a gravacao
    (`gravar_edicao_com_diff`), para o restauro (`file_service.restaurar_item_lixeira`) e para a leitura na
    lixeira (`file_service.resolver_item_lixeira`). Quando a rota HTTP e a ferramenta precisam do mesmo
    comportamento, o comportamento desce para `services/` e as duas pontas passam a delegar. Foi assim que
    o `routes/files.py:trash_restore` deixou de ter a sua propria copia das validacoes de contencao — a
    duplicacao so se descobre comparando, nao se ve no `git diff` de um ficheiro so.

## 4. Definicao de pronto — checklist

| Criterio | Estado |
|---|---|
| Backend sem god object (`app.py` ~factory) | **cumprido** (blueprints + services; `app.py` 44 linhas) |
| Adicionar rota = 1 blueprint | **cumprido** |
| Adicionar IA = 1 modulo (sem tocar `instructions`) | **cumprido** (base/gemini/deepseek) |
| Remover modulo sem quebrar os outros | **cumprido** (services/tools/memory isolados) |
| Adicionar tool = 1 funcao + `@register` | **cumprido** (50 ferramentas, 0 colisoes; 3 novas nesta ronda na lixeira) |
| Nenhuma funcao god (>~250 linhas) | **cumprido** (`startSSE` 26, `loop_raciocinio_ia` 246, `action_diff` handler 114) |
| Nenhum ficheiro acima de ~400 linhas | **NAO cumprido por 1 ficheiro** — `messages.js` ~853 (era 1172), `comments.py` ~380 (era 733), `style.css` 363 (era 2260); resta `css/editor.css` 814, que e um tema unico (Monaco) e nao se divide sem partir a seccao (§3.4) |

## 5. Riscos vivos

- **`busca.txt`** na raiz e artefacto por design do `tool_buscar_web` (nao e lixo; nao apagar durante uso).
- **Ruff sem ruleset curado:** o `tool_auditar_codigo` roda o ruleset default e devolve centenas de
  achados dominados por `I001` (ordenacao de imports) e `BLE001` (`except Exception`, proposital em
  degradacao graciosa). O conserto certo e um `ruff.toml` curado, nao edicoes mecanicas.
- **Imports por efeito de registo:** o bloco `# noqa: F401` do `ai/loop.py` e obrigatorio (22 imports);
  o `tool_auditar_imports_py` **honra** o marcador. Apagar uma dessas linhas desliga as ferramentas.
- **Caminhos por-projeto** vivem em `.axio/` (`chats/`, `knowledge/`, `code_index.json`, `atrito.json`,
  `bootstrap.json`): mudar esse layout quebra estados persistidos de sessoes antigas.
- **Glossario global vs projeto:** `data/glossary.json` e GLOBAL; `glossary.caminho_do_arquivo` procura
  na pasta do projeto e, em fallback, em `APP_ROOT` (sem isso, abrir outro projeto marca as entradas
  como "ausente" e injeta pendencias falsas).
- **`escapeHtml` vive em `chat/escape.js` mas continua re-exportado por `messages.js`**: quem importa
  deve preferir `./escape.js`; o re-export existe so para nao partir `files.js`/`history.js`/`inspect.js`.
- **Estado do turno e de modulo** em `messages.js` (era closure do `startSSE`): `resetEstadoDoTurno()`
  corre a cada (re)conexao. Dois SSE em simultaneo estao impedidos por construcao — `startSSE()` fecha o
  anterior (`state.eventSource.close()`) antes de criar o novo, logo nao ha estado partilhado entre
  conexoes. So deixa de valer se alguem criar um segundo `EventSource` fora desta funcao.
- **`gravar_json_atomico` escreve com temporario UNICO + lock por caminho** (`services/persistencia.py`).
  Nao voltar ao `caminho + ".tmp"`: dois saves concorrentes do mesmo log escreviam no MESMO ficheiro e o
  `os.replace` publicava bytes intercalados — JSON invalido e 500 no historico (o
  `sessionlog_1788985169540.json` de 9,4 MB). O lock vive no processo: ha um unico Flask; com mais de um
  teria de passar a lock de ficheiro.
- **A pasta dos logs de sessao vem SO de `services/session.pasta_session_logs()`** (hoje
  `.axio/logs/session_logs`). `routes/session.py` (save) e `file_service.raiz_lixeira` tinham ficado com o
  caminho antigo `.axio/chats/session_logs`: o save gravava onde ninguem lia e DENTRO do alcance do
  minerador do mempalace. Quem precisar desta pasta usa a funcao, nunca o literal.
- **Evento `error`: RESOLVIDO (2026-09-12).** Era o unico evento emitido sem consumidor (`ai/loop.py:332`,
  quando a API nao devolve resposta valida). O handler novo (`chat/messages.js:tratar_error`) NAO inventa
  interface: delega em `tratar_status`, que ja sabe pintar "Erro: ..." a vermelho na barra e marcar
  `lastStatusError` (a bandeira que impede o `done` seguinte de o apagar), e acrescenta uma mensagem
  `system` ao chat. Decisao mais barata e coerente: o payload do `error` e exatamente o mesmo `message`
  que o `status` ja recebe. Antes disto, um turno sem resposta da API terminava em silencio.
- **A lixeira do projeto tem porta de leitura propria — e so ela tem.** Vive em
  `.axio/logs/session_logs/.trash` (via `services/file_service.raiz_lixeira`), logo TODOS os varrimentos a
  ignoram por construcao: a busca (`tool_pesquisar_no_projeto`), o indice de codigo, o auditor de
  comentarios e as listagens saltam pastas que comecam por `.`. Efeito pratico: um ficheiro apagado nunca
  polui o contexto do agente, mas continua auditavel por 3 ferramentas: `tool_listar_lixeira` (com
  navegacao por `item_id`), `tool_ler_lixeira` (le SEM restaurar) e `tool_restaurar_lixeira`. O nucleo do
  restauro (`resolver_item_lixeira` / `restaurar_item_lixeira`, em `services/file_service.py`) e o MESMO
  que a rota `/api/trash_restore` usa. Prova: `_teste_lixeira.py` + `_teste_despacho.py` (na lixeira),
  40+ verificacoes, incluindo o controlo que mede que a pesquisa VE o ficheiro enquanto ele esta no
  projeto e deixa de o ver quando vai para a lixeira.
- **Rotulo de status congelado apos operacao pesada do vetor (aceite, cosmetico).** Quando a varredura ou
  a limpeza termina ja fora do turno, o `#lbl-status` fica com a ultima percentagem ate ao turno seguinte.
  Nao ha correcao barata e honesta: o SSE so transporta eventos dentro de um turno e a limpeza exigiria um
  poll novo (ou um evento sem `turn_id`, que apagaria o status de um turno vivo). Impacto em dados: zero;
  auto-cura-se no turno seguinte.
