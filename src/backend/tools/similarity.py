"""Codigo duplicado entre ficheiros (jscpd)."""

import subprocess
from src.backend.tools.registry import register
from src.backend.services.file_service import resolver_caminho
from src.backend.state import emit_event
from src.backend.tools.process import run_com_timeout
@register(
    "tool_analisar_similaridade",
    'Analisa a similaridade de código em um arquivo ou pasta usando jscpd.',
    {
        'caminho_relativo': {"tipo": "STRING", "desc": 'Caminho do arquivo ou pasta a ser analisado', "obrig": True, "padrao": ""},
        'min_linhas': {"tipo": "INTEGER", "desc": 'Número mínimo de linhas para considerar como duplicado (padrão: 5)', "padrao": 5},
    },
    disponivel="edicao",
)
def tool_analisar_similaridade(caminho_relativo, min_linhas=5):
    emit_event("executing", function=f"Auditando similaridade: {caminho_relativo}")
    abs_path, erro = resolver_caminho(caminho_relativo)
    if erro:
        return erro

    cmd = f"npx --yes jscpd \"{abs_path}\" --min-lines {min_linhas} --reporters console"
    try:
        proc = run_com_timeout(cmd, timeout=120)
        saida = (proc.stdout or "").strip() + "\n" + (proc.stderr or "").strip()
        return f"Resultado da Análise de Similaridade (jscpd):\n{saida}"
    except subprocess.TimeoutExpired:
        return "ERRO: a analise de similaridade (jscpd) excedeu 120s e foi interrompida. Tente uma pasta menor ou verifique a conexao (primeira execucao baixa o pacote)."
    except Exception as e:
        return f"Erro ao executar jscpd: {e}"
