# Plano de Refatoração — Axio Coder

> Estado: **EM ANDAMENTO** — Fase 0 (esqueleto + registry), Fase 1a (state.py), Fase 1b/1c (services + tools), Fase 1d (memory), Fase 2a (ai/* folhas), Fase 2b (session + memory-mining), Fase 2c (ai/loop.py + ai/instructions.py), Fase 3a (memory/glossary.py), Fase 3b (extensions.py + routes/static.py blueprint), Fase 3c (services/process_manager.py + lixeira no file_service.py + helpers de sessão no services/session.py) e Fase 3d (routes → Blueprints: chat, terminal, editor, files, session) concluídas. **Fase 5a concluída (relocação física do frontend).**
>
> **BACKEND 100% MODULARIZADO.** A antiga "Fase 4 (services restantes)" foi **ABSORVIDA** nas fases 2b/3a/3c
> (session.py, glossary.py, process_manager.py e lixeira do file_service.py já foram entregues).
>
> **Fase 5b (em andamento — o fatiamento):** `workspace.js` (3799 linhas) **já fatiado** em 10 módulos
> (`workspace.js` orquestração + `terminal.js`, `explorer.js`, `monaco.js`, `findbar.js`, `highlight.js`,
> `themes.js`, `diff.js`, `editor.js`, `scroll.js`), todos em `frontend/js/editor/`, scripts clássicos (sem ES Modules).
> `static.py` ganhou a rota genérica `/editor/<path>`. **Falta:** fatiar `renderer.js` (5051 linhas) → `frontend/js/chat/*`.
>
> **⚠️ BLOQUEIO ESTRUTURAL (30/08, Fase 5b):** `renderer.js` NÃO pode ser fatiado como o `workspace.js`.
> Motivo: TODO o `renderer.js` (5051 linhas) está dentro de UM ÚNICO closure
> `document.addEventListener('DOMContentLoaded', () => { ... });`. As ~150 funções e ~40 `const/let`
> de estado vivem nesse closure → não são globais. O `workspace.js` tinha funções no escopo global
> (por isso o split verbatim em `<script>` tags clássicas funcionou). Fatiar o `renderer.js` da mesma
> forma quebraria o compartilhamento de estado entre arquivos.
> **Opções avaliadas (ver conversa):** (A) converter para ES Modules; (B) hoistar estado para escopo
> global + `window.*`; (C) manter `renderer.js` íntegro por ora. DECISÃO pendente do usuário.
> A relocação física (5a) já foi feita: `main.js` → `src/`, `index.html`/`style.css` → `src/frontend/`,
> `workspace.js` → `src/frontend/js/editor/`, `renderer.js` → `src/frontend/js/chat/`; `static.py` re-roteado.
>
> **✅ Fase 6 (concluída):** `data/` criado (glossario.json, entities.json, mempalace.yaml, icons/icon.ico); `mempalace_patch.py` → `backend/memory/`; `icons/` → `data/icons/` e `main.js` re-roteado. Dados por-projeto centralizados em `.axio/` (`chats/`, `memory/`, `index.json`, `bootstrap.json`) via helper `caminho_estado_projeto()` em `state.py`.
> + ajustar `package.json` `"main"` → `"src/main.js"` + limpar a raiz.
>
> **✅ LIMPEZA DA RAIZ (30/08):** órfãos excluídos com segurança — `main.js`, `index.html`, `style.css`,
> `workspace.js` e `renderer.js` (as cópias reais já vivem em `src/`; as rotas de `static.py` e o `package.json`
> `"main"` apontam para `src/`). **`app.py` PERMANECE na raiz de propósito:** é o entry point do Flask
> (`src/main.js` faz `spawn('python', ['app.py'])` com cwd na raiz), e é a única cópia — `src/backend/` não tem
> `app.py`. Mover para `src/backend/app.py` exigiria mudar o spawn + os imports `src.backend.*` (risco separado).
>
> **✅ DECISÃO (30/08):** `atualizar_metricas` e `carregar_log_arquitetura` foram **REMOVIDAS** de `state.py`
> (código morto — a barra RPM/TPM/RPD não existe mais na UI e não há `LOG_CONTEXTO.md` na raiz; o teto de
> contexto real vive em `ai/context.py` e segue ativo). Imports `os`/`time` removidos junto.
>
> **BUGFIX crítico (30/08):** a Fase 1c moveu `id_processo`, `matar_arvore`, `ler_saida_stream` e
> `montar_env_processo` para `tools/process.py`, mas `app.py` só importava os 3 `tool_*`. Esses 4 helpers
> eram usados por `terminal_exec`, `processo_parar` e `_pty_env` em `app.py` → `NameError` em runtime.
> Corrigido: import completo em `app.py:38`.
> Este documento é a fonte única do mapa de módulos e das etapas.
>
> **Fase 1a concluída (30/08):** extraído `estado` + `emit_event` + `notificar_mudanca_arquivos`
> + `MAX_UNDO` + `memoria_lock` + `mineracao_em_andamento` para `src/backend/state.py`.
> `app.py` agora importa esses símbolos de `src.backend.state` (mesma instância compartilhada, sem quebra).
>
> **Fase 1b/1c concluída (30/08):** criados e religados via import:
> - `src/backend/config.py` → `APP_ROOT` (raiz do projeto, corrige `__file__` dos módulos movidos).
> - `src/backend/services/file_service.py` → `dirs_leitura_extra`, `venv_projeto`, `_caminho_proibido`,
>   `resolver_caminho`, `resolver_caminho_arquivo`, `versao_pacote`, `entradas_diretorio`,
>   `normalizar_unicode`, `aplicar_snapshot`, `registrar_edicao`, `capturar_snapshot`.
> - `src/backend/services/diff.py` → `gerar_diff`.
> - `src/backend/tools/filesystem.py` → 12 tools + `_mapear_javascript`.
> - `src/backend/tools/refactor.py` → 3 tools + 5 helpers (`_localizar_funcao_py`, `_fim_funcao_js`,
>   `_localizar_funcao_js`, `_extrair_corpo_funcao`, `_colapsar_linhas_vazias`).
> - `src/backend/tools/process.py` → 3 tools + 17 helpers de processo.
> - `src/backend/tools/environment.py` → `tool_info_ambiente`.
> - `src/backend/tools/bootstrap.py` → `tool_gerenciar_bootstrap` + `_caminho_bootstrap`.
> - `src/backend/tools/web.py` → `tool_buscar_web` + `_conteudo_ilegivel` + `_get_tavily_client`.
>
> **Fase 1d concluída (30/08):** extraída a memória de longo prazo:
> - `src/backend/memory/store.py` → `garantir_pasta_knowledge`, `nome_arquivo_seguro`, `_normalizar_para_dedup`,
>   `_similaridade_jaccard`, `dedup_nota`, `_resumo_nota`, `carregar_indice_knowledge`.
> - `src/backend/memory/vector.py` → `garantir_patch_mempalace` (+ global `_patch_mempalace_aplicado`),
>   `wing_da_pasta`, `salvar_memoria_no_vetor`, `preaquecer_mempalace`,
>   `espelhar_notas_existentes` (+ global `_backfill_ai_memory_executado`).
> - `src/backend/tools/memory_tools.py` → `tool_gerenciar_memoria`, `tool_gerenciar_banco_vetorial`.
> - `app.py` religado via import de `memory.store`, `memory.vector` e `tools.memory_tools`; globais removidos da origem.

> **Fase 2a concluída (30/08):** extraídos os módulos-folha de IA:
> - `src/backend/ai/gemini.py` → `get_gemini_client` + globais `PROJECT_ID`, `LOCATION`,
>   `os.environ["GOOGLE_APPLICATION_CREDENTIALS"]`, `_gemini_client`.
> - `src/backend/ai/deepseek.py` → `get_deepseek_client` + globais `DEEPSEEK_API_KEY`, `_deepseek_client`.
> - `src/backend/ai/context.py` → `ErroContextoExcedido`, `eh_erro_contexto_limite`, `eh_erro_transitorio`,
>   `truncar_cabeca_cauda`, `compactar_historico`, `texto_de_content`, `texto_completo_de_content`,
>   `tokens_historico`, `obter_encoder_tokens`, `contar_tokens`, `resumir_com_llm`, `podar_historico_global`,
>   `texto_de_ferramentas`, `medir_contexto` + globais `LIMITE_TOKENS_HISTORICO_GLOBAL`, `MANTER_RECENTES_GLOBAL`, `token_encoder`.
> - `src/backend/ai/base.py` → `converter_schema_google_para_openai`, `chamar_api_com_retry` (com `MockResponse`).
> - **Bugfix:** `web.py` estava sem `import re` (usado por `_conteudo_ilegivel`) — corrigido.
> - **Bugfix:** `_carregar_env()` foi movido para o topo de `app.py` (antes dos imports de `src.backend.*`),
>   pois `web.py`/`gemini.py`/`deepseek.py` leem variáveis de ambiente no import; antes a chave Tavily viria vazia.
>
> **Fase 2b concluída (30/08):** extraídos os módulos que o loop dependia:
> - `src/backend/services/session.py` → `_caminho_checkpoint`, `carregar_checkpoint`, `salvar_checkpoint`,
>   `formatar_checkpoint` + global `CHECKPOINT_TTL_SEGUNDOS`.
> - `src/backend/memory/vector.py` → `minerar_em_segundo_plano`, `buscar_memorias_com_timeout`
>   (anexados; `vector.py` passou a importar `mineracao_em_andamento`).
> - `app.py` religado via import de `services.session` e `memory.vector`; resíduos removidos.
>
> **Fase 2c concluída:** `ai/loop.py` (contém `tool_aprovar_plano` + `loop_raciocinio_ia`) e
> `ai/instructions.py` (`build_system_instructions`). `app.py` importa `loop_raciocinio_ia` de `ai/loop.py`.

---

## 1. Estrutura final aprovada

```
axio-coder/
├── package.json
├── package-lock.json
├── requirements.txt
├── .env
├── .gitignore
├── README.md
├── start.bat                     # (hoje: iniciar.bat)
│
└── src/
    ├── main.js                   # (hoje: ./main.js)
    │
    ├── backend/                  # ── Python (Flask) ──
    │   ├── app.py                # create_app() factory + CORS + SocketIO + wiring
    │   ├── config.py             # .env + caminhos + constantes
    │   │
    │   ├── ai/                   # ── IA (provedores + orquestração) ──
    │   │   ├── base.py           # classe abstrata ProvedorIA + retry
    │   │   ├── gemini.py         # protocolo Gemini
    │   │   ├── deepseek.py       # protocolo DeepSeek
    │   │   ├── instructions.py   # system prompt + regras (único lugar)
    │   │   ├── loop.py           # loop_raciocinio_ia + dispatch de tools
    │   │   └── context.py        # tokens/compactação/truncamento
    │   │
    │   ├── memory/               # ── memória de longo prazo ──
    │   │   ├── store.py          # .ai_memory + dedup + resumo
    │   │   ├── vector.py         # mempalace/ChromaDB + preaquecimento
    │   │   └── glossary.py       # glossário
    │   │
    │   ├── tools/                # ── tools do LLM ──
    │   │   ├── registry.py       # TOOL_REGISTRY + @register
    │   │   ├── filesystem.py
    │   │   ├── process.py
    │   │   ├── web.py
    │   │   ├── memory_tools.py
    │   │   ├── refactor.py
    │   │   ├── environment.py
    │   │   └── bootstrap.py
    │   │
    │   ├── routes/               # ── endpoints HTTP (Blueprints) ──
    │   │   ├── __init__.py
    │   │   ├── chat.py
    │   │   ├── editor.py
    │   │   ├── files.py
    │   │   ├── session.py
    │   │   ├── terminal.py
    │   │   └── static.py
    │   │
    │   └── services/             # ── regra de negócio pura (sem Flask) ──
    │       ├── file_service.py
    │       ├── session_service.py
    │       ├── diff.py
    │       └── process_manager.py
    │
    └── frontend/                 # ── UI (Electron renderer) ──
        ├── index.html            # (hoje: ./index.html)
        ├── style.css             # (hoje: ./style.css)
        └── js/
            ├── chat/             # ── assistente (hoje: renderer.js) ──
            │   ├── app.js
            │   ├── chat.js
            │   ├── history.js
            │   ├── glossary.js
            │   ├── inspect.js
            │   ├── dock.js
            │   └── util.js
            └── editor/           # ── IDE (hoje: workspace.js) ──
                ├── workspace.js
                ├── monaco.js
                ├── editor.js     # inclui smooth scroll
                ├── diff.js
                ├── logmode.js
                ├── findbar.js
                ├── explorer.js   # inclui lixeira (trash)
                └── terminal.js
```

### Nota sobre o estado atual (importante)

Hoje os ficheiros de código estão **na raiz**, não em `src/`:

| Ficheiro atual | Destino |
|---|---|
| `./app.py` | `src/backend/app.py` (+ quebra nos módulos) |
| `./renderer.js` | `src/frontend/js/chat/*` |
| `./workspace.js` | `src/frontend/js/editor/*` |
| `./main.js` | `src/main.js` |
| `./index.html` | `src/frontend/index.html` |
| `./style.css` | `src/frontend/style.css` |
| `./iniciar.bat` | `./start.bat` |
| `./src/glossario.json` | `data/glossario.json` (fase 5) — dado, não código |
| `./src/mempalace_patch.py` | `src/backend/memory/mempalace_patch.py` |
| `./chats/`, `./icons/`, `./entities.json`, `./mempalace.yaml`, `./.ai_memory/` | `data/*` (fase 5) |
| `./emerald-*.json` | credencial (config) — manter na raiz ou `data/` (não versionar) |
| `./busca.txt` | arquivo temporário — adicionar ao `.gitignore` |

---

## 2. Mapa de funções → módulos

### 2.1 `app.py` (god object — será fatiado)

#### `config.py`
- `_carregar_env`

#### `ai/base.py`
- `get_gemini_client` → na verdade vai para `gemini.py` (ver abaixo)
- `converter_schema_google_para_openai`
- `chamar_api_com_retry`
- `eh_erro_transitorio`
- `MockResponse` (classe + `__init__`)

#### `ai/gemini.py`
- `get_gemini_client`

#### `ai/deepseek.py`
- `get_deepseek_client`

#### `ai/loop.py`
- `loop_raciocinio_ia`

#### `ai/context.py`
- `ErroContextoExcedido`
- `eh_erro_contexto_limite`
- `truncar_cabeca_cauda`
- `compactar_historico`
- `texto_de_content`
- `texto_completo_de_content`
- `tokens_historico`
- `obter_encoder_tokens`
- `contar_tokens`
- `resumir_com_llm`
- `podar_historico_global`
- `texto_de_ferramentas`
- `medir_contexto`

#### `memory/store.py`
- `garantir_pasta_knowledge`
- `nome_arquivo_seguro`
- `tool_gerenciar_memoria` → **fica na tool** (ver `tools/memory_tools.py`), a lógica pura de dedup/resumo vai aqui:
  - `_normalizar_para_dedup`
  - `_similaridade_jaccard`
  - `dedup_nota`
  - `_resumo_nota`
  - `carregar_indice_knowledge`
- `carregar_log_arquitetura`

#### `memory/vector.py`
- `garantir_patch_mempalace`
- `salvar_memoria_no_vetor`
- `espelhar_notas_existentes`
- `preaquecer_mempalace`
- `wing_da_pasta`
- `minerar_em_segundo_plano`
- `buscar_memorias_com_timeout`
- `_executar` / `_trabalho` / `_com_erro` (threads de mineração/prequecimento)

#### `memory/glossary.py`
- `_caminho_glossario`
- `_carregar_glossario`
- `_salvar_glossario`

#### `tools/registry.py`
- `TOOL_REGISTRY` + decorator `@register` (novo)

#### `tools/filesystem.py`
- `tool_listar_pasta`
- `entradas_diretorio`
- `tool_ler_arquivo`
- `tool_ler_trecho_arquivo`
- `normalizar_unicode`
- `_decod`
- `tool_substituir_texto`
- `tool_salvar_arquivo`
- `tool_deletar_arquivo`
- `tool_pesquisar_no_projeto`
- `tool_ler_assinaturas`
- `tool_indexar_projeto`
- `tool_analisar_simbolo`
- `tool_substituir_tudo`
- `_mapear_javascript`
- `tool_mapear_codigo`

#### `tools/process.py`
- `tool_executar_comando`
- `_tokenizar`
- `_validar_comando_processo`
- `tool_executar_processo`
- `tool_parar_processo`

#### `tools/web.py`
- `_get_tavily_client`
- `_conteudo_ilegivel`
- `tool_buscar_web`

#### `tools/memory_tools.py`
- `tool_gerenciar_memoria`
- `tool_gerenciar_banco_vetorial`

#### `tools/refactor.py`
- `_localizar_funcao_py`
- `_fim_funcao_js`
- `_localizar_funcao_js`
- `_extrair_corpo_funcao`
- `_colapsar_linhas_vazias`
- `tool_mover_funcao_verbatim`
- `_hash`
- `tool_verificar_integridade_refatoracao`
- `tool_mover_bloco_verbatim`

#### `tools/environment.py`
- `versao_pacote`
- `tool_info_ambiente`

#### `tools/bootstrap.py`
- `_caminho_bootstrap`
- `tool_gerenciar_bootstrap`

#### `services/file_service.py`
- `dirs_leitura_extra`
- `venv_projeto`
- `_caminho_proibido`
- `resolver_caminho`
- `resolver_caminho_arquivo`

#### `services/diff.py`
- `gerar_diff`

#### `services/session_service.py`
- `aplicar_snapshot`
- `registrar_edicao`
- `capturar_snapshot`
- `pasta_session_logs`
- `caminho_checkpoint_state`
- `ts_de_arquivo_log`
- `ler_log_sessao`
- `prune_session_logs`
- `criar_sessao_vazia`
- `summary_de_logs`
- `reconciliar_snapshot_com_disco`
- `marcar_delecoes_manuais`
- `snapshot_sessao_anterior`
- `arquivos_trackeados`
- `primeira_aparicao_por_arquivo`
- `criados_depois_de`
- `mover_para_lixeira`
- `enviar_para_lixeira_sistema`
- `propagar_rename_logs`
- `marcar_deletado_logs`
- `carregar_snapshot_restauracao`
- `_caminho_checkpoint`
- `carregar_checkpoint`
- `salvar_checkpoint`
- `formatar_checkpoint`

#### `services/process_manager.py`
- `id_processo`
- `_codepage_console_windows`
- `_decodificar_linha_processo`
- `ler_saida_stream`
- `_monitorar_processo_segundo_plano`
- `matar_arvore`
- `_porta_livre`
- `_eh_comando_web`
- `_ajustar_porta_comando`
- `_eh_servidor_http`
- `_porta_responde`
- `_abrir_navegador`
- `_registrar_linha_processo`
- `_abrir_quando_pronto`
- `montar_env_processo`

#### `routes/chat.py`
- `set_folder`
- `chat`
- `cancel`
- `clear_context`
- `stream`
- `event_stream`
- `glossario_listar`
- `glossario_adicionar`
- `glossario_validar`

#### `routes/editor.py`
- `undo_redo_status`
- `undo`
- `redo`
- `explorer`
- `file_content`
- `search_files`
- `file_original`
- `file_save`

#### `routes/files.py`
- `raiz_abs`
- `raiz_lixeira`
- `listar_lixeira`
- `limpar_dirs_vazios`
- `fs_create`
- `fs_rename`
- `fs_trash`
- `trash_list`
- `trash_restore`
- `trash_delete`
- `_excluir_em_segundo_plano`

#### `routes/session.py`
- `session_log_save`
- `_dia_do_grupo`
- `session_history`
- `session_detail`
- `session_log_toggle_save`
- `session_log_delete`
- `_remover_turnos_de_arquivo`
- `session_log_rename`
- `session_restore_preview`
- `checkpoint_state_get`
- `checkpoint_state_set`
- `session_restore`

#### `routes/terminal.py`
- `processos`
- `processo_parar`
- `env_info`
- `comando_inicia_axio`
- `shell_caminho`
- `detectar_shell`
- `_pty_env`
- `cwd_atual`
- `_pty_spawn_locked`
- `pty_kill_locked`
- `_pty_pump`
- `_pty_ensure_pump`
- `_pty_on_connect`
- `_pty_on_input`
- `_pty_on_restart`
- `terminal_cwd`
- `terminal_set_cwd`
- `terminal_shells`
- `terminal_set_shell`
- `terminal_exec`

#### `routes/static.py`
- `serve_workspace_js`
- `serve_socketio_client`
- `serve_monaco`
- `serve_index`
- `serve_renderer_js`
- `serve_style_css`

#### Glue (fica em `app.py`)
- `emit_event`
- `notificar_mudanca_arquivos`
- `atualizar_metricas`

#### Legacy (avaliar remoção)
- `tool_aprovar_plano` — não parece mais usado; manter em `tools/filesystem.py` ou remover após confirmar.

---

### 2.2 `renderer.js` → `frontend/js/chat/*`

#### `app.js`
- `selectFolder`, `restaurarPastaSelecionada`
- `setStopButton`, `resetSendButton`
- `setLogsLoading`, `fadeSwapLogs`
- `activateWorkspaceIcon`, `showWorkspaceView`, `toggleWorkspaceView`
- `syncMenuIcons`, `syncWorkspaceTopBar`

#### `chat.js`
- `setCodeViewContent`, `renderThoughts`, `applyThoughtClamp`, `renderQuestions`
- `setAiAnswerExpanded`, `renderTools`, `showQuestionPanel`
- `recolherContextPopup`, `openClearContextPopup`, `closeClearContextPopup`
- `clearContextMemory`, `updateClearContextButton`
- `resizeChatInput`
- `addMessage`, `formatMessage`, `formatInline`, `isTableSeparator`, `splitTableRow`
- `renderTableBlock`, `formatInlineText`, `attachCodeBlockListeners`, `createCopyButton`
- `dividirDiffEmLinhas`, `gerarSnippetHtml`, `atualizarIconeOlho`, `createChildBalloon`
- `renderImagePreviews`, `addImage`
- `sendMessage`, `startSSE`, `fmtTok`, `normalizeFsPath`, `allSessionGroups`

#### `history.js`
- `beginRenameRound`, `renameRound` (+ `commit`/`cancelar` internos)
- `selectFirstSessionLogCard`, `renderCurrentSessionLogs`
- `moveColsToHistory`, `openFilesPanel`, `updateActionButtons`, `updateShowButtonsState`
- `setHistoryActionButtonsVisible`, `selectHistoryTask`
- `closeConfirmDeletePopup`, `requestDeleteSelectedTask`, `performDeleteSelectedTask`
- `_openAlertPopup`, `showAlert`, `showAlertHtml`
- `countLabelHtml`, `roundMetaHtml`, `formatRoundDuration`
- `closeRestoreConfirmPopup`, `resetRestoreConfirmButtons`, `showRestoreLoading`
- `showRestoreResult`, `requestRestoreTask`, `performSessionRestore`
- `createLogGroupCard`, `serializeGroup`, `saveCurrentTurnSession`, `rebuildGroupFromSaved`
- `toggleSessionHistory`, `fetchSessionHistoryData`, `fetchCheckpointState`
- `saveCheckpointState`, `loadSessionHistoryList`, `renderHistoryCards`
- `collapseDay`, `expandDay`, `prefetchSessionDetails`, `preloadSessionHistory`
- `renderDayRoundCards`, `loadDayRoundCards`, `epochDeId`, `collectAllRoundIds`
- `marcarCheckpoint`, `createHistoryRoundCard`, `updateRoundCardSavedIcon`
- `updateRoundCardSavedIconByTurnId`, `updateRoundCardNameByTurnId`, `toggleSaveSelectedTask`
- `collectSavedRounds`, `renderSalvoCardIfNeeded`, `assignDisplayNamesByDay`
- `renderSalvoCard`, `loadSavedRoundCards`, `selectHistoryTaskInPile`
- `openHistorySearchInCol3`, `toggleHistorySearchInline`, `openHistorySearchPanel`
- `performHistorySearch`, `createHistorySearchResultCard`, `buildSearchSnippet`

#### `glossary.js`
- `normalizarTermo`, `carregarGlossario`, `esconderChip`, `encontrarMatchGlossario`
- `mostrarChipGlossario`, `aplicarChipGlossario`
- `acharCaixaInput`, `caixaInputAtiva`, `contextPopupVisivel`, `posicionarContextUsageUI`
- `posicionarIconTooltip`, `mostrarIconTooltip`, `esconderIconTooltip`

#### `inspect.js`
- `copiarTexto`, `obterElementoAlvo`, `gerarSeletor`, `descricaoDoGlossario`
- `suprimirTooltipNativo`, `restaurarTooltipsNativos`
- `posicionarInspectTooltipXY`, `posicionarInspectTooltip`
- `obterEditorMonaco`, `obterMonacoLib`
- `dentroDeParenteses`, `classificarPalavraChave`, `classificarIdentificador`
- `classificarPorHeuristica`, `classificarCodigoMonaco`
- `infoFonte`, `infoCor`, `renderizarInspect`
- `selecionarItemInspect`, `avancarItemInspect`, `atualizarHintInspect`
- `abrirArquivoNaLinha`, `feedbackInspect`, `colarNoInputText`
- `desativarInspect`, `executarItemInspect`, `ativarInspect`

#### `dock.js`
- `closePlusMenus`, `resetCol3State`, `syncDockButtons`, `syncLogDockFlex`
- `syncHistoryContainerWidth`, `openPanelCol`, `closePanelCol`, `toggleLogColumn`
- `closeCol3`, `isLogDockOpen`, `isCol3Open`, `openLogDock`, `closeLogDock`
- `isHistoryOpen`, `openHistory`, `closeHistory`, `closeHistoryAndResetDock`
- `openLogDockInWorkspace`
- `encontrarArquivoUndo`, `aplicarRiscadoUndo`, `encontrarFileDataPorCaminho`
- `selecionarDiffElement`, `carregarConteudoOriginal`, `rolarParaDestaque`, `rolarSuave`
- `selecionarArquivo`, `adicionarFileNaLista`, `expandir`, `recolher`, `marcarSelecionado`
- `sincronizarArquivosEmTempoReal`, `atualizarBotoesUndoRedo`, `normalizarCaminho`
- `atualizarEstadoBotoes`, `executarUndoRedo`
- `moveColsToDock`, `resetWorkspaceUI`

#### `util.js`
- `escapeHtml`, `countLines`
- `hit` (helper de path/evento)

---

### 2.3 `workspace.js` → `frontend/js/editor/*`

#### `workspace.js` (orquestração/estado global)
- `handleSSE`, `ensureMonacoReady`, `preloadMonaco`, `ensureWorkspaceReady`
- `activate`, `showEditor`, `setActive`
- `applyTopBarVisibility`, `applyTabsVisibility`, `setTopBarHidden`, `layoutAllEditors`
- `applyExplorerSize`, `collapseDockForFocus`, `expandDockForFocus`, `isDockCollapsedForFocus`
- `applyDockLayout`, `effectiveHorizontal`, `updateOrganizeButton`, `applyHorizontalLayout`
- `animateDock`, `animateExplorerReflow`
- `openFileFromLog`, `applyMode`, `showSingleViewLog`, `openFileAtLine`
- `getView`, `loadVenvName`, `showVenvPopup`, `toggleVenv`, `collapseVenv`
- `openFsContextMenu`, `closeFsContextMenu`
- `applyDockTheme`, `initDockTheme`, `scheduleEditorLayout`, `mountLogDockIntoWorkspace`

#### `monaco.js`
- `initMonaco`, `flushMonacoQueue`, `ensureEditor`, `updateEditorWatermark`
- `defineEditorTheme`, `defineLogTheme`, `defineDiffTheme`
- `clearHoverLineFor`, `clearHoverLine`, `hasNonEmptySelection`, `applyHoverLine`
- `installHoverHighlightFor`, `installEditorHoverHighlight`, `installUrlWordSelection`

#### `editor.js` (tabs + save + smooth scroll)
- `loadFileIntoEditor`, `showEditorImage`, `showEditorBinary`, `hideEditorImage`
- `updateExplorerToolbar`, `findTabElement`, `updateTabsActive`, `allTabPaths`
- `addTab`, `pinPreview`, `renderTabs`, `startTabRename` (+ `commit`)
- `openFileInEditor`, `closeTab`, `closeActiveTab`, `performRename`
- `saveFile`, `scheduleAutoSave`, `createFileFromTyping`, `scheduleExplorerReload`
- `fadeEditorSwap`, `fadeEditorIn`, `getEditorMargin`, `getScrollableElement`
- `fadeGutterSwap`, `fadeGutterIn`
- `smoothScrollEditor`, `isEditorLineVisible`, `smoothRevealLine`, `revealLineAtTop`
- `smoothScrollEditors`, `revealSnippet` (+ `frame` internos)

#### `diff.js`
- `computeLineDiff`, `buildScrollMap`, `getTopForFractionalLine`
- `syncDiffScrollFrom`, `installDiffScrollSync`, `disposeDiffScrollSync`
- `decorateDiffSide`, `applyDiffLineDecorations`, `computeHiddenRanges`
- `applyFocusMode`, `setFocusMode`, `enterDiffMode`, `exitDiffMode`
- `captureDiffExitScroll`, `revealDiffExitScroll`, `updateLogToggle`

#### `logmode.js`
- `applyLogDecorations`, `applyLineGutterState`, `updateLineNumbersButton`
- `applyLogEditorOptions`, `enterLogMode`, `enterLogModeWithLines`
- `exitLogMode`, `enterReadonlyLogMode`

#### `findbar.js`
- `wireMonacoFindPush`, `getFindWidget`, `getContentEl`, `getVScrollbar`
- `setVScrollbarOffset`, `getOverviewRuler`, `setOverviewRulerOffset`, `getMarginEl`
- `setMarginOffset`, `syncTabBar`, `relocateFindTooltip`, `stopCloseTimer`, `commitZone`
- `setContentTransform`, `open`, `close`, `resize`, `updateMatchesCountVisibility`
- `apply`, `ensure`, `fadeFindWidget`, `unfadeFindWidget`, `installFindToggle`

#### `explorer.js` (árvore + breadcrumbs + busca + lixeira)
- `buildExplorerSegments`, `handleCrumbClick`, `updateExplorerPath`
- `animateViewTransition`, `setView`, `loadExplorerOnce`, `reloadExplorer`, `loadExplorer`
- `renderExplorer`, `renderEmptyExplorer`, `renderEntry`, `staggerExplorerItems`
- `loadDirChildren`, `toggleDir`, `openFile`, `selectEntry`, `highlightSelection`
- `deselectEntry`, `currentDir`, `getLanguage`
- `revealPath`, `findExplorerRow`, `startRename` (+ `commit`), `createFs`
- `toggleExplorerSearch`, `performExplorerSearch`, `renderExplorerSearchResults`
- `createSearchResultCard`, `applyState`, `appendSearchHighlight`
- `initExplorerResizer` (+ `flush`, `onMove`, `onUp`)
- **Lixeira:** `loadTrash`, `openTrash`, `closeTrash`, `openFsConfirm`, `closeFsConfirm`
- `trashPath`, `doTrashSelected`, `doDeleteTrashPermanent`, `doRestoreTrash`

#### `terminal.js`
- `appendLine`, `appendCommand`, `appendSeparator`, `clearLog`, `stripAnsi`
- `isPromptLine`, `isBannerLine`, `formatBannerLine`, `emitPtyLine`, `handlePtyOutput`
- `connectTermSocket`, `runCommand`, `basename`, `joinPath`, `quotePath`, `cdCommandFor`
- `changeTerminalCwd`, `isAbsolutePath`, `enterDir`
- `loadShellInfo`, `setTerminalShell`, `openShellMenu`, `closeShellMenu`, `toggleShellMenu`

---

### 2.4 `main.js` (Electron main — permanece, só muda de pasta)

- `createWindow`
- `waitForFlask` (+ `tryConnect`)
- `killProcessOnPort`
- `startFlask`
- `setTema`

---

## 3. Etapas (fases commitáveis)

Cada fase termina com o app **funcionando igual a antes** e é testável isoladamente.

| Fase | Escopo | Ganho | Risco |
|---|---|---|---|
| **0** | Criar `src/backend/` + `src/frontend/` esqueleto, `config.py`, factory vazia. App segue intacto. | Base sem quebrar nada | Mínimo |
| **1** | `tools/` + `registry.py` (`@register`) + mover as `tool_*` e helpers. Substituir o `if/elif` do loop por leitura do `TOOL_REGISTRY`. | Maior ganho; menor risco (funções puras) | Baixo |
| **2** | `services/` (file_service, diff, session_service, process_manager) | Desacopla regra de negócio | Médio |
| **3** | `routes/` (Blueprints) + `app.py` vira factory | Fim do god object backend | Médio |
| **4** | `frontend/` — fatiar `workspace.js` (editor) primeiro, depois `renderer.js` (chat), `style.css` permanece único | Fim dos god objects frontend | Médio/Alto (ES Modules) |
| **5** | `data/` (chats, icons, .ai_memory, entities.json, mempalace.yaml, glossario.json) + `"main": "src/main.js"` + `start.bat` | Raiz limpa | Médio (caminhos persistidos) |

### Ordem recomendada dentro do backend
1. `tools/registry.py` (novo)
2. `tools/*` (mover tool_* + helpers privados)
3. `services/*` (mover helpers de negócio)
4. `memory/*` (store, vector, glossary)
5. `ai/*` (base, gemini, deepseek, instructions, loop, context)
6. `routes/*` + `app.py` factory

### Regra de ouro durante toda a refatoração
- Usar `tool_mover_funcao_verbatim` (funções Python/JS) e `tool_mover_bloco_verbatim` (blocos HTML/CSS) — **nunca redigitar**.
- Após mover, `tool_verificar_integridade_refatoracao` (hash byte a byte).
- Uma fase por commit; se quebrar, reverte só a fase.

---

## 4. Dependências cruzadas a respeitar (não quebrar)

- **`memory/`** é usada por `tools/memory_tools.py` **e** por `ai/loop.py`. Por isso é pasta própria, não dentro de `tools/` nem de `ai/`.
- **`services/`** é usado por `routes/` **e** por `tools/` (ex: `tools/filesystem.py` chama `resolver_caminho` de `services/file_service.py`).
- **`tools/registry.py`** é o único ponto que `ai/loop.py` conhece para descobrir tools (Open/Closed).
- **`ai/instructions.py`** é a única fonte das regras/system prompt (nunca duplicar em gemini/deepseek).

---

## 5. Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Acentos/codificação ao mover (NFC/NFD) | `tool_mover_*_verbatim` move bytes exatos; nunca redigitar |
| Caminhos persistidos (checkpoint, logs, memória) quebrarem na fase 5 | Fase 5 por último; `config.py` centraliza caminhos antes de mover `data/` |
| `"main"` do Electron apontando errado | Só mudar `package.json` na fase 5, junto do move do `main.js` |
| ES Modules no frontend (fase 4) | Migrar por módulo; testar com `node --check` + recarga Ctrl+Shift+R |
| `emerald-*.json` (credencial) vazar | Garantir no `.gitignore`; manter como config, não como código |

---

## 6. Definição de pronto (done) da refatoração

- Nenhum ficheiro de código com mais de ~400 linhas.
- `app.py` reduzido a factory (~80–150 linhas).
- Adicionar tool = 1 função + `@register` (sem tocar no loop).
- Adicionar IA = 1 ficheiro herdando `base.py` (sem tocar em instructions).
- Adicionar rota = 1 blueprint (sem tocar no `app.py`).
- Remover um módulo = apagar a pasta/ficheiro, sem quebrar os demais.

---

## 7. Arquivos da raiz — classificação (descoberto em 30/08)

### 7.1 O que fazer com cada item da raiz

| Item | Classificação | Destino na refatoração |
|---|---|---|
| `app.py`, `renderer.js`, `workspace.js`, `main.js`, `index.html`, `style.css` | Código (hoje na raiz) | Mover para `src/` (fases 1–4) |
| `src/` (`glossario.json`, `mempalace_patch.py`) | Código/dados | `glossario.json` → `data/` (fase 5); `mempalace_patch.py` → `backend/` |
| `chats/` | Dados runtime (logs de sessão) | `data/chats/` (fase 5) |
| `.ai_memory/` | Dados runtime (memória) | `data/.ai_memory/` (fase 5) |
| `.bim_index.json` | Cache gerado por `tool_indexar_projeto` | `data/` OU ignorar no git (regenerável) |
| `busca.txt` | Log gerado por `tool_buscar_web` | `data/` OU ignorar no git |
| `entities.json` | Dados runtime | `data/` (fase 5) |
| `mempalace.yaml` | Config de memória | `data/` (fase 5) |
| `.axio/bootstrap.json` | Estado do bootstrap (Supabase) | `data/.axio/` (fase 5) |
| `icons/` | Assets estáticos | `data/icons/` ou `frontend/` (verificar uso na fase 5) |
| `__pycache__/` | Cache Python | Ignorar (já no .gitignore) |
| `node_modules/` | Dependências npm | Ignorar (já no .gitignore) |
| `.env` | Config/secret | Manter na raiz, gitignored |
| `emerald-caster-*.json` | Credencial de serviço | Manter na raiz, **gitignored** (já está) — nunca commitar |
| `iniciar.bat` | Script de start | Renomear `start.bat` |
| `package.json`, `package-lock.json`, `requirements.txt`, `README.md`, `.gitignore` | Config | Manter na raiz |

### 7.2 `tool_aprovar_plano` — MANTER (não remover)

O usuário esclareceu: é o modo **semi-automático** (o agente só executa a tool após o usuário confirmar). **Não remover.** É tool legítima; ficará em `tools/` (módulo a definir na fase 1 — provável módulo próprio de controle/approval ou junto de `environment.py`). Não tocar até a fase 1.

### 7.3 Descoberta de implementação (insumo da fase 1)

- **Schemas:** declarados em `app.py` na lista `ferramentas_base` (~linha 2676), via `types.FunctionDeclaration(name=..., description=..., parameters=types.Schema(...))`.
- **Dispatch:** cadeia `if/elif nome_func == ...` em `loop_raciocinio_ia` (~linha 2897).
- A fase 1 substitui os dois: cada tool ganha `@register(nome, description, parameters)` (parameters como **dict puro**, desacoplado do SDK Gemini) e o loop lê `TOOL_REGISTRY` + `build_function_declarations(types)`.
