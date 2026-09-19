export const FONTE_CODIGO = "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace";
export const FONTE_TAMANHO = 14;
export const ALTURA_LINHA = 20;
export const PADDING_TOPO = 16;
export const RECUO_LATERAL = 16;
export const RECUO_COLUNA_DIREITA = 12;
export function opcoesBase() {
    return {
        fontSize: FONTE_TAMANHO,
        fontFamily: FONTE_CODIGO,
        lineHeight: ALTURA_LINHA,
        padding: { top: PADDING_TOPO, bottom: 0 },
        wordWrap: 'off',
        minimap: { enabled: false },
        scrollBeyondLastLine: false,
        renderLineHighlight: 'none',
        smoothScrolling: true,
        mouseWheelScrollSensitivity: 1,
        stickyScroll: { enabled: false }
    };
}
