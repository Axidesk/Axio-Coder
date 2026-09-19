import { state } from './state.js';
import * as dom from './dom.js';
import { showAlert } from './ui.js';
import { carregarCofre, ligarEventosCofre } from './cofre.js';
import { SVG_OLHO, SVG_OLHO_RISCADO } from './icones.js';

const { btnRevealKeys, inputDeepseekKey, inputGeminiKey, inputTavilyKey } = dom;


    export function openSettingsModal() {
        if (!dom.settingsModal) return;
        dom.settingsModal.classList.remove('opacity-0', 'pointer-events-none');
        dom.settingsModal.classList.add('opacity-100', 'pointer-events-auto');
        if (dom.settingsModalContent) {
            dom.settingsModalContent.classList.remove('scale-95');
            dom.settingsModalContent.classList.add('scale-100');
        }
        loadSettingsData();
        const ativa = document.querySelector('[data-settings-tab].active');
        if (ativa && ativa.dataset.settingsTab === 'cofre') carregarCofre();
    }
    export function closeSettingsModal() {
        if (!dom.settingsModal) return;
        dom.settingsModal.classList.remove('opacity-100', 'pointer-events-auto');
        dom.settingsModal.classList.add('opacity-0', 'pointer-events-none');
        if (dom.settingsModalContent) {
            dom.settingsModalContent.classList.remove('scale-100');
            dom.settingsModalContent.classList.add('scale-95');
        }
    }
    export async function loadSettingsData() {
        try {
            const resp = await fetch('/api/settings');
            if (!resp.ok) return;
            const dados = await resp.json();
            const ds = dados.deepseek || {};
            const gem = dados.gemini || {};
            const tv = dados.tavily || {};
            if (dom.inputDeepseekKey) dom.inputDeepseekKey.value = ds.api_key || '';
            state.settingsDeepseekEnabled = !!ds.enabled || !!(ds.api_key || '').trim();
            state.settingsVertexMode = gem.mode === 'vertex';
            state.settingsStudioApiKey = gem.studio_api_key || '';
            state.settingsVertexJsonName = gem.vertex_json_name || '';
            state.settingsVertexJsonData = gem.vertex_json || null;
            state.settingsGeminiEnabled = !!gem.enabled || !!(gem.studio_api_key || '').trim() || !!gem.vertex_json;
            if (dom.inputGeminiKey) dom.inputGeminiKey.value = state.settingsStudioApiKey || '';
            if (dom.inputVertexKey) dom.inputVertexKey.value = state.settingsVertexJsonName || '';
            if (dom.inputTavilyKey) dom.inputTavilyKey.value = tv.api_key || '';
            state.settingsNavMode = false;
            atualizarCardGemini();
            aplicarEstadoToggleVertex(state.settingsVertexMode);
            aplicarEstadoToggleNav(false);
            aplicarEstadoToggleDeepseek(state.settingsDeepseekEnabled);
            aplicarEstadoToggleGemini(state.settingsGeminiEnabled);
            atualizarBotaoLimparVertex();
        } catch (e) {
            console.log('settings: servidor indisponivel', e);
        }
    }
    export function atualizarCardGemini() {
        if (dom.infoGemini) {
            const inner = dom.infoGemini.querySelector('.settings-info-text-inner');
            const conteudo = state.settingsVertexMode ? GEMINI_INFO_VERTEX : GEMINI_INFO_STUDIO;
            if (inner) inner.innerHTML = conteudo;
            else dom.infoGemini.innerHTML = conteudo;
        }
        if (dom.labelGemini) {
            dom.labelGemini.textContent = state.settingsVertexMode ? 'Vertex AI' : 'Google Gemini';
        }
    }
    export function aplicarEstadoToggleVertex(ativo) {
        state.settingsVertexMode = !!ativo;
        atualizarCardGemini();
        if (dom.btnSwitchModel) {
            dom.btnSwitchModel.setAttribute('aria-pressed', state.settingsVertexMode ? 'true' : 'false');
            dom.btnSwitchModel.title = state.settingsVertexMode ? 'Usar Gemini API' : 'Usar Vertex API';
        }
        if (dom.studioField) {
            dom.studioField.classList.toggle('active', !state.settingsVertexMode);
        }
        if (dom.vertexField) {
            dom.vertexField.classList.toggle('active', state.settingsVertexMode);
        }
        atualizarIndicadorModelo();
        atualizarBloqueioGemini();
    }
    export function aplicarEstadoToggleNav(ativo) {
        state.settingsNavMode = !!ativo;
        if (dom.btnNavToggle) {
            dom.btnNavToggle.setAttribute('aria-pressed', state.settingsNavMode ? 'true' : 'false');
            dom.btnNavToggle.title = 'Tavily';
        }
        if (dom.deepseekField) {
            dom.deepseekField.classList.toggle('active', !state.settingsNavMode);
        }
        if (dom.tavilyField) {
            dom.tavilyField.classList.toggle('active', state.settingsNavMode);
        }
        if (dom.labelDeepseek) {
            dom.labelDeepseek.textContent = state.settingsNavMode ? 'Tavily' : 'DeepSeek';
        }
        atualizarIndicadorGlobo();
        limparErroTavily();
    }
    export function aplicarEstadoToggleDeepseek(ativo) {
        state.settingsDeepseekEnabled = !!ativo;
        if (dom.btnDeepseekToggle) {
            dom.btnDeepseekToggle.classList.toggle('on', state.settingsDeepseekEnabled);
            dom.btnDeepseekToggle.setAttribute('aria-checked', state.settingsDeepseekEnabled ? 'true' : 'false');
            dom.btnDeepseekToggle.title = state.settingsDeepseekEnabled ? 'Desativar' : 'Ativar';
        }
        if (dom.inputDeepseekKey) dom.inputDeepseekKey.readOnly = state.settingsDeepseekEnabled;
        if (dom.inputTavilyKey) dom.inputTavilyKey.readOnly = state.settingsDeepseekEnabled;
        if (dom.btnNavToggle) {
            dom.btnNavToggle.classList.toggle('locked', state.settingsDeepseekEnabled);
        }
        atualizarIndicadorGlobo();
    }
    export function aplicarEstadoToggleGemini(ativo) {
        state.settingsGeminiEnabled = !!ativo;
        if (dom.btnGeminiToggle) {
            dom.btnGeminiToggle.classList.toggle('on', state.settingsGeminiEnabled);
            dom.btnGeminiToggle.setAttribute('aria-checked', state.settingsGeminiEnabled ? 'true' : 'false');
            dom.btnGeminiToggle.title = state.settingsGeminiEnabled ? 'Desativar' : 'Ativar';
        }
        if (dom.btnSwitchModel) {
            dom.btnSwitchModel.classList.toggle('locked', state.settingsGeminiEnabled);
        }
        atualizarBloqueioGemini();
        atualizarBotaoLimparVertex();
    }
    export function atualizarBotaoLimparVertex() {
        if (dom.btnVertexClear) {
            const temArquivo = !!state.settingsVertexJsonData;
            const bloqueado = state.settingsGeminiEnabled;
            dom.btnVertexClear.classList.toggle('show', temArquivo && !bloqueado);
        }
    }
    export async function salvarConfiguracoes(opcoes = {}) {
        const deepseekKey = dom.inputDeepseekKey ? dom.inputDeepseekKey.value.trim() : '';
        state.settingsStudioApiKey = dom.inputGeminiKey ? dom.inputGeminiKey.value.trim() : '';
        if (opcoes.validarVertex !== false && state.settingsVertexMode && !state.settingsVertexJsonData) {
            if (opcoes.alertar !== false) {
                showAlert('Selecione o ficheiro JSON da conta de serviço do Vertex AI antes de salvar.');
            }
            return false;
        }
        const geminiPayload = {
            mode: state.settingsVertexMode ? 'vertex' : 'studio',
            studio_api_key: state.settingsStudioApiKey,
            vertex_json_name: state.settingsVertexJsonName,
            vertex_json: state.settingsVertexJsonData,
            enabled: state.settingsGeminiEnabled
        };
        const tavilyKey = dom.inputTavilyKey ? dom.inputTavilyKey.value.trim() : '';
        const payload = {
            deepseek: { api_key: deepseekKey, enabled: state.settingsDeepseekEnabled },
            gemini: geminiPayload,
            tavily: { api_key: tavilyKey, enabled: state.settingsDeepseekEnabled && !!tavilyKey }
        };
        try {
            const resp = await fetch('/api/settings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const resultado = await resp.json();
            if (resp.ok && resultado.ok) {
                return true;
            }
            if (opcoes.alertar !== false) {
                showAlert('Erro ao salvar: ' + ((resultado && resultado.error) || 'resposta inválida'));
            }
            return false;
        } catch (err) {
            if (opcoes.alertar !== false) {
                showAlert('Erro ao salvar configurações: ' + err.message);
            }
            return false;
        }
    }
    
    const GEMINI_INFO_STUDIO = 'Para obter a chave API do Gemini, acesse o <a href="https://aistudio.google.com/apikey" target="_blank" rel="noopener">AI Studio</a>, insira os dados de faturamento, gere a chave, insira no campo abaixo e ative o botão. Opcionalmente, você pode criar a chave API do Vertex e ganhar um bónus inicial de $300. Para saber como, clique no ícone ao lado e siga as instruções.<br><br><em>O Gemini já usa grounding nativo. Não é necessário criar API para navegação web.</em>';
    const GEMINI_INFO_VERTEX = 'Para obter a chave API Vertex do Gemini, acesse o <a href="https://console.cloud.google.com" target="_blank" rel="noopener">Google Cloud Console</a>. Crie uma <a href="https://console.cloud.google.com/iam-admin/serviceaccounts" target="_blank" rel="noopener">conta de serviço</a>, ative a API buscando por <a href="https://console.cloud.google.com/apis/library" target="_blank" rel="noopener">Vertex AI API</a>.<br><br>No painel lateral, acesse IAM e administrador → Contas de serviço → Criar conta de serviço → No papel busque por Usuário do Vertex AI → Gere o arquivo JSON → Selecione o arquivio → Ative o botão. Após o pagamento inicial você receberá $300 de crédito gratuitamente.';
    
    export function atualizarBloqueioGemini() {
        if (dom.inputGeminiKey) {
            dom.inputGeminiKey.readOnly = state.settingsGeminiEnabled;
            dom.inputGeminiKey.classList.toggle('locked', state.settingsGeminiEnabled);
        }
        if (dom.inputVertexKey) {
            dom.inputVertexKey.classList.toggle('locked', state.settingsGeminiEnabled);
        }
    }
    function atualizarTipoInputs() {
        const revelar = state.settingsRevealKeys;
        if (inputDeepseekKey) inputDeepseekKey.type = revelar ? 'text' : 'password';
        if (inputTavilyKey) inputTavilyKey.type = revelar ? 'text' : 'password';
        if (inputGeminiKey) inputGeminiKey.type = revelar ? 'text' : 'password';
    }
    export function aplicarEstadoReveal(ativo) {
        state.settingsRevealKeys = !!ativo;
        if (btnRevealKeys) {
            btnRevealKeys.classList.toggle('on', state.settingsRevealKeys);
            btnRevealKeys.setAttribute('aria-pressed', state.settingsRevealKeys ? 'true' : 'false');
            btnRevealKeys.title = state.settingsRevealKeys ? 'Ocultar chaves' : 'Mostrar chaves';
            btnRevealKeys.innerHTML = state.settingsRevealKeys ? SVG_OLHO_RISCADO : SVG_OLHO;
        }
        const inputs = [inputDeepseekKey, inputTavilyKey, inputGeminiKey];
        const elegiveis = inputs.filter(Boolean);
        const ghosts = [];
        elegiveis.forEach((inp) => {
            if (!inp.value) return;
            const wrap = inp.parentElement;
            if (!wrap || !wrap.classList.contains('settings-input-wrap')) return;
            const ghost = document.createElement('div');
            ghost.className = 'settings-input-ghost';
            ghost.textContent = inp.type === 'password' ? '•'.repeat(inp.value.length) : inp.value;
            wrap.appendChild(ghost);
            ghosts.push(ghost);
        });
        atualizarTipoInputs();
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                ghosts.forEach((ghost) => ghost.classList.add('ghost-fade-out'));
                setTimeout(() => {
                    ghosts.forEach((ghost) => ghost.remove());
                }, 300);
            });
        });
    }
    export function limparErroTavily() {
        if (dom.inputTavilyKey) dom.inputTavilyKey.classList.remove('error');
        if (dom.tavilyError) dom.tavilyError.classList.add('hidden');
    }
    export function mostrarErroTavily() {
        if (dom.inputTavilyKey) dom.inputTavilyKey.classList.add('error');
        if (dom.tavilyError) dom.tavilyError.classList.remove('hidden');
    }
    export function mostrarErroDeepseek() {
        if (dom.inputDeepseekKey) dom.inputDeepseekKey.classList.add('error');
        if (dom.deepseekError) dom.deepseekError.classList.remove('hidden');
    }
    export function limparErroDeepseek() {
        if (dom.inputDeepseekKey) dom.inputDeepseekKey.classList.remove('error');
        if (dom.deepseekError) dom.deepseekError.classList.add('hidden');
    }
    export function mostrarErroGemini() {
        if (state.settingsVertexMode && dom.inputVertexKey) dom.inputVertexKey.classList.add('error');
        if (!state.settingsVertexMode && dom.inputGeminiKey) dom.inputGeminiKey.classList.add('error');
        if (dom.geminiError) dom.geminiError.classList.remove('hidden');
    }
    export function limparErroGemini() {
        if (dom.inputVertexKey) dom.inputVertexKey.classList.remove('error');
        if (dom.inputGeminiKey) dom.inputGeminiKey.classList.remove('error');
        if (dom.geminiError) dom.geminiError.classList.add('hidden');
    }
    export function validarChaveDeepseek(v) {
        return !!v && v.startsWith('sk-') && v.length >= 20;
    }
    export function validarChaveTavily(v) {
        return !!v && v.startsWith('tvly-') && v.length >= 20;
    }
    export function validarChaveStudio(v) {
        return !!v && (v.startsWith('AQ.') || v.startsWith('AIza')) && v.length >= 20;
    }
    export function atualizarIndicadorModelo() {
        if (!dom.btnSwitchModel) return;
        dom.btnSwitchModel.classList.toggle('on', state.settingsVertexMode || state.settingsGeminiEnabled);
    }
    export function atualizarIndicadorGlobo() {
        if (!dom.btnNavToggle) return;
        dom.btnNavToggle.classList.toggle('on', state.settingsNavMode || state.settingsDeepseekEnabled);
    }

export function mostrarAbaSettings(nome) {
    document.querySelectorAll('[data-settings-tab]').forEach((botao) => {
        botao.classList.toggle('active', botao.dataset.settingsTab === nome);
    });
    document.querySelectorAll('[data-settings-panel]').forEach((painel) => {
        painel.classList.toggle('hidden', painel.dataset.settingsPanel !== nome);
    });
    if (dom.btnCofreRevelar) dom.btnCofreRevelar.classList.toggle('hidden', nome !== 'cofre');
    if (nome === 'cofre') carregarCofre();
}

document.querySelectorAll('[data-settings-tab]').forEach((botao) => {
    botao.addEventListener('click', () => mostrarAbaSettings(botao.dataset.settingsTab));
});
ligarEventosCofre();