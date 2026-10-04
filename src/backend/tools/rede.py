import json
import socket
import subprocess
import threading
import time
import unicodedata
import urllib.request

from src.backend.state import emit_event
from src.backend.tools.registry import register

NOS_PADRAO = 4
ESPERA_DOS_NOS = 45

CABECALHOS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def ip_publico():
    for url in ("https://api.ipify.org", "https://ipinfo.io/ip"):
        try:
            return urllib.request.urlopen(url, timeout=8).read().decode().strip()
        except Exception:
            continue
    return ""


def _resolver(nome):
    try:
        return socket.gethostbyname(nome)
    except Exception:
        return ""


def _pedir_json(url):
    pedido = urllib.request.Request(url, headers=CABECALHOS)
    return json.loads(urllib.request.urlopen(pedido, timeout=20).read().decode())


def _nos_do_servico(ip, porta, quantos):
    inicio = _pedir_json(f"https://check-host.net/check-tcp?host={ip}:{porta}&max_nodes={quantos}")
    pedido = inicio.get("request_id")
    if not pedido:
        raise RuntimeError(f"check-host nao aceitou o pedido: {str(inicio)[:200]}")
    esperados = len(inicio.get("nodes") or {})
    limite = time.monotonic() + ESPERA_DOS_NOS
    while time.monotonic() < limite:
        time.sleep(2)
        resposta = _pedir_json(f"https://check-host.net/check-result/{pedido}")
        prontos = {no: valor for no, valor in resposta.items() if valor is not None}
        if prontos and len(prontos) >= esperados:
            return prontos
    return prontos if prontos else {}


def _resultado_do_no(valor):
    if not isinstance(valor, list) or not valor:
        return "sem resposta", False
    item = valor[0]
    if isinstance(item, dict) and item.get("error"):
        return item["error"], False
    if isinstance(item, dict) and item.get("time") is not None:
        return f"ligou em {float(item['time']) * 1000:.1f}ms", True
    return str(item)[:120], False


class _Ouvinte:
    def __init__(self, porta):
        self.porta = porta
        self.servidor = None
        self.chegaram = []
        self._parar = threading.Event()
        self._fio = None

    def abrir(self):
        servidor = socket.socket()
        servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        servidor.bind(("0.0.0.0", self.porta))
        servidor.listen(32)
        self.servidor = servidor
        self._fio = threading.Thread(target=self._aceitar, daemon=True)
        self._fio.start()

    def _aceitar(self):
        self.servidor.settimeout(1)
        while not self._parar.is_set():
            try:
                ligacao, quem = self.servidor.accept()
                self.chegaram.append(quem[0])
                ligacao.close()
            except socket.timeout:
                continue
            except OSError:
                break

    def fechar(self):
        self._parar.set()
        if self._fio:
            self._fio.join(timeout=2)
        if self.servidor:
            self.servidor.close()


def _regras_de_firewall(porta):
    candidatas = [r for r in _blocos_de_regras(_netsh(["name=all", "dir=in"]))
                  if str(porta) in _portas_da_regra(r)]
    ativas = []
    for regra in candidatas:
        nome = regra["nome"]
        detalhe = _blocos_de_regras(_netsh([f'name="{nome}"', "verbose"]))
        estado = detalhe[0] if detalhe else {}
        if estado.get("habilitado") == "Sim" and estado.get("acao") == "Permitir":
            ativas.append(nome)
    return ativas


def _portas_da_regra(regra):
    return [p.strip() for p in (regra.get("localport") or "").split(",") if p.strip()]


def _netsh(argumentos):
    try:
        resultado = subprocess.run(
            ["netsh", "advfirewall", "firewall", "show", "rule"] + argumentos,
            capture_output=True, timeout=40,
        )
    except Exception:
        return ""
    bruto = resultado.stdout or b""
    for codificacao in ("utf-8", "oem", "cp1252"):
        try:
            return bruto.decode(codificacao)
        except (UnicodeDecodeError, LookupError):
            continue
    return bruto.decode("utf-8", errors="replace")


def _blocos_de_regras(saida):
    regras, atual = [], None
    for linha in saida.splitlines():
        chave, separador, valor = linha.partition(":")
        if not separador:
            continue
        chave, valor = _sem_acento(chave), valor.strip()
        if chave == "nome da regra":
            if atual:
                regras.append(atual)
            atual = {"nome": valor}
        elif atual is not None:
            atual[chave] = valor
    if atual:
        regras.append(atual)
    return regras


def _sem_acento(texto):
    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    ).strip().lower()


@register(
    "tool_verificar_porta_externa",
    "Responde 'esta porta esta aberta para quem vem da internet?' - a pergunta de qualquer servidor que tenha de receber ligacoes de fora (um jogo, um site, uma API). Pergunta a nos espalhados pelo mundo (check-host) se conseguem ligar ao IP:porta e, por omissao, abre um ouvinte temporario na propria maquina para PROVAR se as ligacoes de fora chegam mesmo la dentro - a diferenca entre 'o roteador nao encaminha' e 'a maquina recusa'. Diz tambem o IP publico medido e, quando nada chega, se existe regra no firewall do Windows a permitir essa porta de entrada (sem regra, a culpa pode ser do firewall e nao do roteador). Nao substitui o servidor: para testar a aplicacao a correr, com o servidor no ar, use escutar=false.",
    {
        "porta": {
            "tipo": "INTEGER",
            "obrig": True,
            "desc": "Porta TCP a testar (ex: 7171).",
        },
        "host": {
            "tipo": "STRING",
            "obrig": False,
            "padrao": "",
            "desc": "Nome ou IP a testar. Vazio = o IP publico desta maquina.",
        },
        "escutar": {
            "tipo": "BOOLEAN",
            "obrig": False,
            "padrao": True,
            "desc": "Abrir um ouvinte temporario na porta para provar se a ligacao de fora chega a esta maquina. Use false quando o servidor verdadeiro ja estiver a correr nessa porta.",
        },
        "nos": {
            "tipo": "INTEGER",
            "obrig": False,
            "padrao": NOS_PADRAO,
            "desc": "Quantos servidores espalhados pelo mundo devem tentar a ligacao (padrao 4).",
        },
    },
)
def tool_verificar_porta_externa(porta, host="", escutar=True, nos=NOS_PADRAO):
    emit_event("executing", function=f"A testar a porta {porta} de fora")

    publico = ip_publico()
    alvo = (host or "").strip()
    if alvo:
        ip = _resolver(alvo)
        if not ip:
            return f"O nome {alvo} nao resolve em endereco nenhum - sem endereco nao ha o que testar."
    else:
        ip = publico
        alvo = publico
        if not ip:
            return "Nao consegui medir o IP publico desta maquina (sem ligacao a internet?)."

    linhas = [f"Alvo testado: {alvo}" + (f" -> {ip}" if ip != alvo else "")]
    if publico:
        linhas.append(f"IP publico desta maquina: {publico}")
        if ip != publico:
            linhas.append("  (o alvo nao e esta maquina - o ouvinte local nao se aplica)")

    ouvinte = None
    proprio = (not host) or (ip == publico)
    if escutar and proprio:
        ouvinte = _Ouvinte(porta)
        try:
            ouvinte.abrir()
            linhas.append(f"Ouvinte temporario aberto em 0.0.0.0:{porta}")
        except OSError as erro:
            linhas.append(f"Sem ouvinte (a porta {porta} ja esta ocupada nesta maquina: {erro.strerror}). "
                          "A leitura passa a ser so a dos nos de fora.")
            ouvinte = None

    try:
        try:
            resultados = _nos_do_servico(ip, porta, nos)
        except Exception as erro:
            linhas.append(f"Nao consegui falar com o servico de teste externo: {type(erro).__name__} {erro}")
            resultados = {}

        ligaram, falharam = [], []
        if resultados:
            linhas.append("De fora, cada no respondeu:")
            for no, valor in sorted(resultados.items()):
                texto, ligou = _resultado_do_no(valor)
                linhas.append(f"  - {no}: {texto}")
                (ligaram if ligou else falharam).append(no)

        chegaram = list(ouvinte.chegaram) if ouvinte is not None else None

        if chegaram:
            linhas.append(f"PROVA: {len(chegaram)} ligacao(oes) de fora chegaram mesmo a esta maquina "
                          f"({', '.join(sorted(set(chegaram)))}).")
            linhas.append("VEREDITO: ALCANCAVEL de fora. O caminho roteador -> maquina esta aberto.")
        elif chegaram == [] and ligaram:
            linhas.append("PROVA: a porta estava aberta a escuta nesta maquina e NENHUMA ligacao chegou.")
            linhas.append(f"VEREDITO: os nos ({', '.join(ligaram)}) dizem que ligaram, mas nada entrou - "
                          "o mais provavel e um equipamento pelo caminho a responder no lugar do teu servidor.")
        elif chegaram == []:
            linhas.append("PROVA: a porta estava aberta a escuta nesta maquina e NENHUMA ligacao chegou.")
            regras = _regras_de_firewall(porta)
            if regras:
                linhas.append(f"Firewall do Windows: ha regra de entrada ativa a permitir a porta ({', '.join(regras)}).")
                linhas.append("VEREDITO: BLOQUEADO no caminho - com o firewall limpo, quem barra e o roteador "
                              "(sem encaminhamento desta porta) ou o operador (CGNAT, endereco partilhado).")
            else:
                linhas.append("Firewall do Windows: nenhuma regra de entrada ativa permite esta porta (pode haver "
                              "uma regra por programa, que nao se le pelo numero da porta).")
                linhas.append("VEREDITO: BLOQUEADO. Pode ser o roteador (sem encaminhamento) OU o firewall desta "
                              "maquina - sem regra a permitir a porta, a ligacao morre antes de chegar ao servico.")
        elif ligaram and len(ligaram) > len(falharam):
            linhas.append(f"VEREDITO: ALCANCAVEL de fora pela maioria dos nos ({len(ligaram)} de {len(resultados)} "
                          "ligaram). Leitura indireta: para prova direta, corra com o servidor parado e escutar=true.")
        elif resultados:
            linhas.append(f"VEREDITO: BLOQUEADO para quem vem de fora ({len(falharam)} de {len(resultados)} nos "
                          "nao conseguiram ligar).")
        else:
            linhas.append("VEREDITO: sem leitura - o servico de teste externo nao respondeu.")
        return "\n".join(linhas)
    finally:
        if ouvinte is not None:
            ouvinte.fechar()
