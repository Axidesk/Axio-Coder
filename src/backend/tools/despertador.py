"""Ferramenta do despertador: o agente marca quando quer ser acordado e encerra a rodada.

Distinta de 'tool_aguardar_confirmacao', que espera AQUI dentro e gasta o tempo da
rodada: esta grava a intencao, devolve o controlo ao utilizador e faz o Axio voltar
sozinho, com a nota do agente como primeira mensagem da rodada nova.
"""

from datetime import datetime

from src.backend.services import despertador
from src.backend.tools.registry import register


@register(
    "tool_agendar_despertar",
    "Agenda um despertar: FECHA a rodada e o Axio volta sozinho quando a condicao se cumprir, "
    "com a 'nota' como primeira mensagem da rodada nova. SO SERVE PARA DUAS COISAS: operacao LONGA "
    "(30 min ou mais - um download de GB, um treino, uma copia enorme) ou EVENTO DO MUNDO (um email "
    "que vai chegar, um anuncio que so muda amanha). NUNCA para compilar, instalar, rodar um teste "
    "ou qualquer coisa que termine em minutos: isso resolve-se NA MESMA RODADA, com "
    "tool_executar_processo em modo 'aguardar' ou com tool_listar_processos - dormir 2 minutos "
    "gasta uma rodada inteira e nao adianta nada. Para o que ja esta a correr, arme em "
    "quando_processo=<pid>, nunca no relogio. Escolha UM gatilho: 'depois_de' (intervalo: '90' minutos, '45s', '30m', '2h', "
    "'1h30'), 'quando' (instante: 'HH:MM' ou 'AAAA-MM-DD HH:MM') ou 'quando_processo' (o pid que "
    "tool_executar_processo devolveu - acorda quando ele terminar) ou 'quando_ficheiro' (acorda "
    "quando o caminho aparecer). PARA UMA OPERACAO QUE ESTA A CORRER, ARME NO PROCESSO E NAO NO "
    "RELOGIO: 'depois_de' nao sabe se ela falhou, 'quando_processo' acorda assim que ela morre - "
    "com o codigo de saida e as ultimas linhas ja na nota. 'sinal' vigia a saida do processo e "
    "acorda MAIS CEDO, mesmo com ele vivo (ex: 'ERRO|Fatal|Traceback'): e o que evita dormir 10 "
    "horas sobre um download que rebentou aos 10 minutos. 'prazo' e o teto: acorda mesmo sem a "
    "condicao se cumprir, para nao dormir sobre um processo pendurado. A 'nota' e o que eu "
    "proprio vou ler ao acordar: escreva-a como uma instrucao a mim mesmo, com o que ja esta "
    "feito e o que falta (ex: 'O download do boost acabou em _baixar/boost.zip: descompactar e "
    "compilar'). acao='estado' mostra o agendamento em vigor, 'cancelar' desarma o que estiver "
    "marcado. O agendamento sobrevive a fechar o Axio.",
    {
        "acao": {
            "tipo": "STRING",
            "desc": "agendar | estado | cancelar",
            "enum": ["agendar", "estado", "cancelar"],
            "padrao": "agendar",
        },
        "depois_de": {
            "tipo": "STRING",
            "desc": "Intervalo ate acordar: '90' (minutos), '45s', '30m', '2h' ou '1h30'.",
            "padrao": "",
        },
        "quando": {
            "tipo": "STRING",
            "desc": "Instante de acordar: 'HH:MM' (hoje ou amanha) ou 'AAAA-MM-DD HH:MM'.",
            "padrao": "",
        },
        "quando_processo": {
            "tipo": "STRING",
            "desc": "Pid de um processo: acorda quando ele terminar (ex: 'proc_3' ou '8123').",
            "padrao": "",
        },
        "quando_ficheiro": {
            "tipo": "STRING",
            "desc": "Caminho que ainda nao existe: acorda quando ele aparecer.",
            "padrao": "",
        },
        "sinal": {
            "tipo": "STRING",
            "desc": "Texto ou expressao a vigiar na saida do processo de 'quando_processo': acorda MAIS "
                    "CEDO, com ele ainda a correr, quando a linha aparecer (ex: 'ERRO|Fatal|Traceback').",
            "padrao": "",
        },
        "prazo": {
            "tipo": "STRING",
            "desc": "Teto de espera: acorda mesmo sem a condicao se cumprir ('30m', '6h'). Serve para "
                    "nao dormir sobre um processo pendurado.",
            "padrao": "",
        },
        "nota": {
            "tipo": "STRING",
            "desc": "A instrucao que eu vou ler ao acordar: o que estava a esperar, o que ja esta feito e o que fazer a seguir.",
            "padrao": "",
        },
    },
)
def tool_agendar_despertar(acao="agendar", depois_de="", quando="", quando_processo="",
                           quando_ficheiro="", nota="", sinal="", prazo=""):
    acao = (acao or "agendar").strip().lower()
    if acao == "estado":
        return _texto_do_retrato(despertador.retrato())
    if acao == "cancelar":
        resultado = despertador.cancelar("o agente desarmou o despertador")
        if not resultado.get("cancelado"):
            return "Nao havia nada agendado."
        return f"Despertador desarmado ({resultado.get('id', '')})."
    resultado = despertador.agendar(
        quando=quando,
        depois_de=depois_de,
        quando_processo=quando_processo,
        quando_ficheiro=quando_ficheiro,
        nota=nota,
        sinal=sinal,
        prazo=prazo,
    )
    if resultado.get("erro"):
        return "ERRO: " + resultado["erro"]
    texto = (
        "Despertador armado: " + resultado.get("descricao", "") + ".\n"
        f"Nota que vou ler ao acordar: {resultado.get('nota', '')}\n"
        "A rodada pode encerrar agora - eu volto sozinho no momento marcado. "
        "O utilizador pode cancelar pelo botao na barra de status."
    )
    if resultado.get("aviso"):
        texto += "\nAVISO: " + resultado["aviso"]
    return texto


def _texto_do_retrato(dados):
    estado_atual = dados.get("estado")
    if estado_atual in ("nenhum", "", None):
        return "Nada agendado: nenhum despertador armado."
    if estado_atual == "armado":
        linhas = [
            f"Despertador ARMADO ({dados.get('id', '')}).",
            f"Gatilho: {dados.get('descricao', dados.get('descricao_do_gatilho', ''))}",
            f"Nota: {dados.get('nota', '')}",
        ]
        if dados.get("quando"):
            linhas.append(f"Instante marcado: {dados['quando']}")
        return "\n".join(linhas)
    if estado_atual == "disparado":
        return (
            "O despertador JA DISPAROU "
            f"({dados.get('disparado_em', '')}). Gatilho: {dados.get('descricao_do_gatilho', '')}\n"
            f"Nota: {dados.get('nota', '')}"
        )
    if estado_atual == "cancelado":
        cancelado_em = dados.get("cancelado_em", "")
        disparado_em = dados.get("disparado_em", "")
        quando = " as " + cancelado_em if cancelado_em else ""
        if disparado_em:
            return (
                "O despertador ja tinha DISPARADO as " + disparado_em +
                " e foi cancelado depois" + quando +
                f". Motivo: {dados.get('motivo') or 'nao registado'}."
            )
        return "O ultimo despertador foi cancelado" + quando + "."
    return f"Estado do despertador: {estado_atual} ({datetime.now().strftime('%H:%M')})."
