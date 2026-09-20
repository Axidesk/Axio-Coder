"""Sugestao de mensagem de commit: a IA propoe, o clique decide."""

from src.backend.ai.deepseek import get_deepseek_client

_LIMITE_CONTEXTO = 1200
_LIMITE_FICHEIROS = 20
_LIMITE_MENSAGEM = 100

_INSTRUCAO = (
    "Escreve a mensagem de um commit de git que resuma a tarefa descrita abaixo. "
    "Uma unica linha, no imperativo, ate 72 caracteres, em portugues, sem ponto final, "
    "sem prefixo nem aspas. Responde APENAS com a mensagem."
)


def sugerir_mensagem(contexto, ficheiros):
    """Devolve (mensagem, erro) para o campo do commit."""
    pedacos = []
    if ficheiros:
        lista = "\n".join(f"- {f}" for f in ficheiros[:_LIMITE_FICHEIROS])
        pedacos.append(f"Ficheiros alterados:\n{lista}")
    limpo = (contexto or "").strip()
    if limpo:
        pedacos.append(f"O que se fez:\n{limpo[:_LIMITE_CONTEXTO]}")
    if not pedacos:
        return None, "Sem ficheiros nem contexto para sugerir uma mensagem"
    try:
        resp = get_deepseek_client().chat.completions.create(
            model="deepseek-flash",
            messages=[
                {"role": "system", "content": _INSTRUCAO},
                {"role": "user", "content": "\n\n".join(pedacos)},
            ],
        )
    except Exception as e:
        return None, f"A sugestao falhou: {e}"
    texto = (resp.choices[0].message.content or "").strip().strip('"').strip()
    if not texto:
        return None, "A sugestao voltou vazia"
    return texto.splitlines()[0].strip()[:_LIMITE_MENSAGEM], ""
