"""Copia e movimento de ficheiros e pastas, com o custo medido antes de comecar.

So usa a biblioteca padrao: o corredor do plano e um processo proprio (o card do
terminal, com a barra a encher) e importa este modulo sem arrastar o estado do Axio atras.
O progresso sai impresso como '[feitos/total]', que e o sinal que o Axio ja sabe ler.
"""

import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

RAIZ_DO_AXIO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

NOME_DA_PASSAGEM = "_axio_passagem"
FICHEIROS_DA_SONDA = 24
FIOS_DA_COPIA = 16
GANHO_MINIMO_DA_PASSAGEM = 1.3
BYTES_DA_AMOSTRA = 24 * 1024 * 1024
LIMITE_DE_FICHEIRO_GRANDE = 32 * 1024 * 1024
MARCAS_DE_SINCRONIA = (".dropbox", ".dropbox.cache")
NOMES_DE_SINCRONIA = ("dropbox", "onedrive", "google drive", "my drive", "iclouddrive", "icloud drive")


def contar(caminho):
    """(bytes, ficheiros, maior) de uma pasta ou de um ficheiro."""
    if os.path.isfile(caminho):
        tamanho = os.path.getsize(caminho)
        return tamanho, 1, tamanho
    total = ficheiros = maior = 0
    for base, _, nomes in os.walk(caminho):
        for nome in nomes:
            try:
                tamanho = os.path.getsize(os.path.join(base, nome))
            except OSError:
                continue
            total += tamanho
            ficheiros += 1
            maior = max(maior, tamanho)
    return total, ficheiros, maior


def pasta_sincronizada(caminho):
    """A raiz da pasta de sincronia (Dropbox, OneDrive...) que contem 'caminho', ou ''."""
    atual = os.path.abspath(caminho if os.path.isdir(caminho) else os.path.dirname(caminho))
    while True:
        if os.path.basename(atual).lower() in NOMES_DE_SINCRONIA:
            return atual
        for marca in MARCAS_DE_SINCRONIA:
            if os.path.exists(os.path.join(atual, marca)):
                return atual
        pai = os.path.dirname(atual)
        if pai == atual:
            return ""
        atual = pai


def ancestral_existente(caminho):
    """A pasta mais proxima de 'caminho' que ja existe - a sonda escreve la, sem criar nada."""
    atual = os.path.abspath(caminho)
    while not os.path.isdir(atual):
        pai = os.path.dirname(atual)
        if pai == atual:
            return atual
        atual = pai
    return atual


def duracao_texto(segundos):
    segundos = max(0.0, float(segundos or 0))
    if segundos < 10:
        return f"{segundos:.1f}s"
    segundos = int(segundos)
    if segundos < 60:
        return f"{segundos}s"
    if segundos < 3600:
        return f"{segundos // 60}m{segundos % 60:02d}s"
    return f"{segundos // 3600}h{(segundos % 3600) // 60:02d}m"


def _raiz_da_passagem(destino):
    """Uma pasta de trabalho no MESMO disco do destino e FORA da pasta de sincronia, ou ''."""
    unidade = os.path.splitdrive(os.path.abspath(destino))[0]
    if not unidade:
        return ""
    raiz = os.path.join(unidade + os.sep, NOME_DA_PASSAGEM)
    try:
        os.makedirs(raiz, exist_ok=True)
    except OSError:
        return ""
    return "" if pasta_sincronizada(raiz) else raiz


def pasta_de_passagem(destino):
    """A pasta desta transferencia dentro da area de passagem, criada e vazia."""
    raiz = _raiz_da_passagem(destino)
    if not raiz:
        return ""
    pasta = os.path.join(raiz, "t" + os.urandom(4).hex())
    try:
        os.makedirs(pasta, exist_ok=True)
    except OSError:
        return ""
    return pasta


def _tamanho(caminho):
    try:
        return os.path.getsize(caminho)
    except OSError:
        return 0


def amostra(origem, quantos=FICHEIROS_DA_SONDA):
    """Ficheiros ESPALHADOS pela arvore (passo constante, nao os primeiros) para representar o todo."""
    if os.path.isfile(origem):
        return [origem]
    todos = []
    for base, _, nomes in os.walk(origem):
        for nome in nomes:
            todos.append(os.path.join(base, nome))
    if not todos:
        return []
    passo = max(1, len(todos) // quantos)
    escolhidos = []
    bytes_ = 0
    for caminho in todos[::passo]:
        tamanho = _tamanho(caminho)
        if tamanho > LIMITE_DE_FICHEIRO_GRANDE:
            continue
        escolhidos.append(caminho)
        bytes_ += tamanho
        if len(escolhidos) >= quantos or bytes_ >= BYTES_DA_AMOSTRA:
            break
    return escolhidos


def _sonda_real(pasta_destino, ficheiros, passagem=""):
    """(segundos por ficheiro, segundos totais, ficheiros) a COPIAR DE VERDADE a amostra e limpa-la.

    Nao e uma tabela de velocidades: e a operacao certa, nos ficheiros certos, entre os dois
    sitios certos, e com os MESMOS fios da copia a serio - logo apanha o que o antivirus e o
    filtro da sincronia custam aqui e agora, que muda de disco para disco e de hora para hora.
    """
    if not ficheiros:
        return 0.0, 0.0, 0
    marca = os.urandom(4).hex()
    pasta_da_copia = passagem or pasta_destino
    pares = [(fonte, os.path.join(pasta_da_copia, f"_axio_sonda_{marca}_{indice}.tmp"))
             for indice, fonte in enumerate(ficheiros)]
    os.makedirs(pasta_da_copia, exist_ok=True)
    inicio = time.perf_counter()
    erros = _copiar_pares(pares)
    if passagem:
        for _, caminho in pares:
            if os.path.exists(caminho):
                os.replace(caminho, os.path.join(pasta_destino, os.path.basename(caminho)))
    decorrido = time.perf_counter() - inicio
    copiados = len(pares) - len(erros)
    for _, caminho in pares:
        for alvo in {caminho, os.path.join(pasta_destino, os.path.basename(caminho))}:
            try:
                os.remove(alvo)
            except OSError:
                pass
    return (decorrido / copiados if copiados else 0.0), decorrido, copiados


def _pares_de_copia(origem, destino):
    """[(ficheiro de origem, ficheiro de destino)] de uma arvore, com as pastas ja criadas."""
    if os.path.isfile(origem):
        os.makedirs(os.path.dirname(os.path.abspath(destino)), exist_ok=True)
        return [(origem, destino)]
    pares = []
    for base, _, nomes in os.walk(origem):
        relativo = os.path.relpath(base, origem)
        alvo = destino if relativo == "." else os.path.join(destino, relativo)
        os.makedirs(alvo, exist_ok=True)
        for nome in sorted(nomes):
            pares.append((os.path.join(base, nome), os.path.join(alvo, nome)))
    return pares


def _copiar_pares(pares, ao_progredir=None, operacao=None):
    """Copia os pares em PARALELO. O custo por ficheiro neste disco e' latencia (o antivirus e o
    filtro da sincronia a inspecionarem cada ficheiro novo), e sobrepor essa espera e' o que
    faz a diferenca: medido 217 ms por ficheiro a 1 fio contra 93 ms a 16.
    """
    erros = []
    if not pares:
        return erros
    fios = max(1, min(FIOS_DA_COPIA, len(pares)))
    fazer = operacao or shutil.copy2
    with ThreadPoolExecutor(max_workers=fios) as poola:
        futuros = {poola.submit(fazer, origem, destino): destino for origem, destino in pares}
        for futuro in as_completed(futuros):
            try:
                futuro.result()
            except OSError as erro:
                erros.append(f"{futuros[futuro]}: {erro}")
            if ao_progredir:
                ao_progredir()
    return erros


def planear(origem, destino, acao="copiar", raiz_do_projeto=""):
    """Mede origem e destino e devolve o plano: por onde copiar e quanto tempo deve custar.

    O modo escolhe-se por MEDICAO entre as duas maneiras de escrever no destino - direto
    ou por uma area de passagem no mesmo disco, com entrada por rename - e nunca por
    suposicao: e a sonda que decide qual das duas e mais barata neste disco, hoje.
    """
    bytes_, ficheiros, maior = contar(origem)
    plano = {
        "origem": os.path.abspath(origem),
        "destino": os.path.abspath(destino),
        "acao": acao,
        "raiz_do_axio": RAIZ_DO_AXIO,
        "raiz_do_projeto": raiz_do_projeto,
        "bytes": bytes_,
        "ficheiros": ficheiros,
        "maior": maior,
        "modo": "direto",
        "passagem": "",
        "sincronizada": pasta_sincronizada(destino),
        "custo_por_ficheiro": 0.0,
        "s_direto": 0.0,
        "s_passagem": None,
        "amostra": 0,
        "segundos_da_sonda": 0.0,
        "estimativa": 0.0,
    }
    if not ficheiros:
        return plano
    mesma_unidade = (os.path.splitdrive(plano["origem"])[0].lower()
                     == os.path.splitdrive(plano["destino"])[0].lower())
    if acao == "mover" and mesma_unidade:
        plano["modo"] = "renomear"
        return plano
    pasta_do_destino = ancestral_existente(os.path.dirname(plano["destino"]))
    ficheiros_da_amostra = amostra(plano["origem"])
    direto, segundos, quantos = _sonda_real(pasta_do_destino, ficheiros_da_amostra)
    plano["s_direto"] = direto
    custo = direto
    if plano["sincronizada"] and mesma_unidade:
        passagem = pasta_de_passagem(plano["destino"])
        if passagem:
            com_passagem, segundos_p, quantos_p = _sonda_real(pasta_do_destino, ficheiros_da_amostra,
                                                              passagem)
            if com_passagem and com_passagem * GANHO_MINIMO_DA_PASSAGEM < direto:
                plano["modo"] = "passagem"
                plano["passagem"] = passagem
                plano["s_passagem"] = com_passagem
                custo, segundos, quantos = com_passagem, segundos_p, quantos_p
            else:
                limpar_passagem(passagem)
    plano["custo_por_ficheiro"] = custo
    plano["amostra"] = quantos
    plano["segundos_da_sonda"] = segundos
    plano["estimativa"] = custo * ficheiros
    return plano


def limpar_passagem(passagem):
    """Apaga a pasta de passagem desta transferencia - e a raiz dela, se ficar vazia."""
    if not passagem:
        return
    raiz = os.path.dirname(os.path.abspath(passagem))
    shutil.rmtree(passagem, ignore_errors=True)
    try:
        if os.path.basename(raiz) == NOME_DA_PASSAGEM and not os.listdir(raiz):
            os.rmdir(raiz)
    except OSError:
        pass


class _Anuncio:
    """Imprime '[feitos/total] faltam ~X' - o formato que o Axio le para encher a barra."""

    def __init__(self, total):
        self.total = max(1, int(total or 0))
        self.feitos = 0
        self.inicio = time.perf_counter()
        self.ultimo = 0.0
        self.cada = max(1, self.total // 200)

    def passo(self):
        self.feitos += 1
        agora = time.perf_counter()
        if self.feitos < self.total and self.feitos % self.cada and agora - self.ultimo < 2.0:
            return
        self.ultimo = agora
        print(f"[{self.feitos}/{self.total}] {self._falta()}", flush=True)

    def _falta(self):
        decorrido = time.perf_counter() - self.inicio
        if self.feitos <= 0 or decorrido < 1:
            return "a copiar"
        restante = decorrido / self.feitos * (self.total - self.feitos)
        return f"faltam ~{duracao_texto(restante)}"

    def fechar(self, texto):
        print(f"[{self.total}/{self.total}] {texto}", flush=True)


def _copiar(origem, destino, anuncio):
    return _copiar_pares(_pares_de_copia(origem, destino), anuncio.passo)


def _entrar_da_passagem(conteudo, destino):
    """Entra no destino por rename (metadados, sem reescrever bytes) - o que a torna barata."""
    if not os.path.exists(destino):
        os.makedirs(os.path.dirname(os.path.abspath(destino)), exist_ok=True)
        os.replace(conteudo, destino)
        return _copiar_pares([], None, os.replace)
    return _copiar_pares(_pares_de_copia(conteudo, destino), None, os.replace)


def _renomear(origem, destino):
    if os.path.isdir(origem) and os.path.isdir(destino):
        _entrar_da_passagem(origem, destino)
        _apagar(origem)
        return
    os.makedirs(os.path.dirname(os.path.abspath(destino)), exist_ok=True)
    os.replace(origem, destino)


def _apagar(caminho):
    if os.path.isdir(caminho):
        shutil.rmtree(caminho, ignore_errors=True)
    elif os.path.exists(caminho):
        try:
            os.remove(caminho)
        except OSError:
            pass


def conferir(plano):
    """Os ficheiros que faltam no destino (ou que la estao com outro tamanho) - lista vazia = ok."""
    faltam = []
    origem = plano["origem"]
    destino = plano["destino"]
    if os.path.isfile(origem):
        try:
            certo = os.path.isfile(destino) and os.path.getsize(destino) == os.path.getsize(origem)
        except OSError:
            certo = False
        return [] if certo else [destino]
    for base, _, nomes in os.walk(origem):
        relativo = os.path.relpath(base, origem)
        alvo = destino if relativo == "." else os.path.join(destino, relativo)
        for nome in nomes:
            fonte = os.path.join(base, nome)
            copia = os.path.join(alvo, nome)
            try:
                if not os.path.isfile(copia) or os.path.getsize(copia) != os.path.getsize(fonte):
                    faltam.append(copia)
            except OSError:
                faltam.append(copia)
    return faltam


def executar(plano):
    """Corre o plano. A origem so e apagada depois de a copia inteira ter sido conferida."""
    total = max(1, plano.get("ficheiros") or 0)
    modo = plano.get("modo")
    if modo == "renomear":
        print(f"[0/{total}] a renomear no mesmo disco", flush=True)
        _renomear(plano["origem"], plano["destino"])
        print(f"[{total}/{total}] pronto", flush=True)
        return
    anuncio = _Anuncio(total)
    if modo == "passagem":
        conteudo = os.path.join(plano["passagem"], "conteudo")
        erros = _copiar(plano["origem"], conteudo, anuncio)
        if not erros:
            anuncio.fechar("a entrar no destino por rename")
            erros = _entrar_da_passagem(conteudo, plano["destino"])
        _apagar(plano["passagem"])
    else:
        erros = _copiar(plano["origem"], plano["destino"], anuncio)
        if not erros:
            anuncio.fechar("copiado")
    if erros:
        print(f"[{total}/{total}] ERRO: {len(erros)} ficheiros nao chegaram ao destino "
              f"(ex: {erros[0]}). A origem NAO foi apagada.", flush=True)
        raise SystemExit(1)
    faltam = conferir(plano)
    if faltam:
        print(f"[{total}/{total}] ERRO: {len(faltam)} ficheiros nao chegaram ao destino "
              f"(ex: {faltam[0]}). A origem NAO foi apagada.", flush=True)
        raise SystemExit(1)
    print(f"[{total}/{total}] conferido: {total} ficheiros com o tamanho certo no destino", flush=True)
    if plano.get("acao") == "mover":
        print(f"[{total}/{total}] a apagar a origem", flush=True)
        _apagar(plano["origem"])
