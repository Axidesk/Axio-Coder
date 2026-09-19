"""Linters externos: ESLint (JS/TS) e Ruff (Python)."""

from src.backend.tools.registry import register
from src.backend.services.file_service import resolver_caminho
from src.backend.state import emit_event
from src.backend.tools.process import run_com_timeout


@register(
    "tool_auditar_codigo",
    "Executa um linter (ESLint para JS/TS, Ruff para Python) e reporta variáveis não declaradas (no-undef) e código não usado (no-unused-vars). Exige 'linguagem'.",
    {
        'caminho_relativo': {"tipo": "STRING", "desc": 'Caminho do arquivo a ser auditado', "obrig": True, "padrao": ""},
        'linguagem': {"tipo": "STRING", "desc": 'Linguagem do código (ex: javascript, python etc)', "obrig": True, "padrao": "javascript"},
    },
    disponivel="edicao",
)
def tool_auditar_codigo(caminho_relativo, linguagem="javascript"):
    emit_event("executing", function=f"Auditando código: {caminho_relativo}")
    abs_path, erro = resolver_caminho(caminho_relativo)
    if erro:
        return erro

    linguagem = linguagem.lower()
    if linguagem in ("javascript", "typescript"):
        cmd = f"npx --yes eslint@8 --no-eslintrc --env browser,node,es2024 --global io --global hljs --parser-options sourceType:module --rule \"no-undef: error\" --rule \"no-unused-vars: warn\" \"{abs_path}\""
        try:
            proc = run_com_timeout(cmd)
            saida = (proc.stdout or "").strip() + "\n" + (proc.stderr or "").strip()
            if proc.returncode == 0 and not saida.strip():
                return "Auditoria concluída: Nenhum erro encontrado."
            return f"Resultado da Auditoria (ESLint):\n{saida}"
        except Exception as e:
            return f"Erro ao executar ESLint: {e}"

    elif linguagem == "python":
        try:
            proc = run_com_timeout(["ruff", "check", abs_path])
            if proc.returncode == 0 and not proc.stdout.strip():
                return "Auditoria concluída: Nenhum erro encontrado."
            return f"Resultado da Auditoria (Ruff):\n{proc.stdout.strip()}\n{proc.stderr.strip()}"
        except FileNotFoundError:
            return "ERRO: 'ruff' não encontrado no PATH. Instale-o ou use outra ferramenta."
        except Exception as e:
            return f"Erro ao executar Ruff: {e}"
    
    return f"Linguagem '{linguagem}' não suportada para auditoria automática."
