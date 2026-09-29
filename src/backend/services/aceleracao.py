"""Aceleracao por GPU para o que corre dentro do Python do Axio: registo das DLLs do
runtime CUDA, pre-carga do cuDNN e veredicto por inferencia real.
"""
import ctypes
import os
import re
import sysconfig
import threading
from pathlib import Path

MODELOS_DE_SONDA = ("PP-OCRv6_det_small.onnx", "PP-OCRv6_rec_small.onnx")

MAX_ERRO = 220

_ESTADO = {}
_PRE_CARGA = None


def _site_packages():
    return Path(sysconfig.get_paths()["purelib"])


def _pastas_bin():
    """As pastas bin/ do runtime CUDA instalado pelo pip, lidas do disco: a lista de
    subpacotes nao fica escrita aqui, para nao envelhecer com a versao."""
    raiz = _site_packages() / "nvidia"
    if not raiz.is_dir():
        return []
    return sorted(pasta for pasta in raiz.iterdir() if (pasta / "bin").is_dir())


def registar_dlls():
    """Regista as pastas bin/ do runtime CUDA instalado pelo pip. Devolve quantas existem."""
    registadas = 0
    for pasta in _pastas_bin():
        if not pasta.is_dir():
            continue
        try:
            os.add_dll_directory(str(pasta))
            registadas += 1
        except (OSError, AttributeError):
            pass
    return registadas


def _dlls_cudnn(pasta):
    """As DLLs do cuDNN: as sub-bibliotecas primeiro e o carregador no fim, que e quem as
    procura ao carregar. Os nomes saem do disco - o '_9' da versao nao fica no codigo."""
    carregador = re.compile(r"^cudnn\d+_\d+\.dll$")
    nomes = sorted(alvo.name for alvo in pasta.glob("*.dll"))
    return ([nome for nome in nomes if not carregador.match(nome)]
            + [nome for nome in nomes if carregador.match(nome)])

def precarregar_cudnn():
    """Carrega as sub-bibliotecas do cuDNN por ordem de dependencia. Devolve as que falharam."""
    pasta = _site_packages() / "nvidia" / "cudnn" / "bin"
    if not pasta.is_dir():
        return ["cuDNN ausente"]
    falhadas = []
    for nome in _dlls_cudnn(pasta):
        try:
            ctypes.CDLL(str(pasta / nome))
        except OSError:
            falhadas.append(nome)
    return falhadas


def _veredicto(registadas, falhadas):
    if falhadas:
        return (False, "DLLs do cuDNN que nao carregaram: " + ", ".join(falhadas[:3]))
    if not registadas:
        return (False, "runtime CUDA do pip ausente (pip install onnxruntime-gpu[cuda,cudnn])")
    return (True, f"{registadas} pasta(s) de runtime registadas")


def iniciar_preparacao():
    """Solta o arranque do servidor: regista as pastas (rapido) e carrega o cuDNN numa
    thread, que e a parte lenta (medido: 24s a carregar as DLLs antes de o socket abrir)."""
    global _PRE_CARGA
    if "preparado" in _ESTADO or _PRE_CARGA is not None:
        return
    try:
        _ESTADO["registadas"] = registar_dlls()
    except Exception as erro:
        _ESTADO["preparado"] = (False, f"falhou ao preparar as DLLs ({type(erro).__name__})")
        return

    def _carregar():
        try:
            _ESTADO["falhadas"] = precarregar_cudnn()
        except Exception:
            _ESTADO["falhadas"] = ["falha ao pre-carregar o cuDNN"]

    _PRE_CARGA = threading.Thread(target=_carregar, daemon=True, name="pre-carga-cudnn")
    _PRE_CARGA.start()


def preparar():
    """(ok, motivo): regista as pastas e pre-carrega o cuDNN uma so vez por processo.
    Se a pre-carga estiver a decorrer em segundo plano, espera por ela - o veredicto
    nunca sai antes de as DLLs estarem carregadas."""
    if "preparado" in _ESTADO:
        return _ESTADO["preparado"]
    if _PRE_CARGA is None:
        try:
            _ESTADO["registadas"] = registar_dlls()
            _ESTADO["falhadas"] = precarregar_cudnn()
        except Exception as erro:
            _ESTADO["preparado"] = (False, f"falhou ao preparar as DLLs ({type(erro).__name__})")
            return _ESTADO["preparado"]
    else:
        _PRE_CARGA.join()
    _ESTADO["preparado"] = _veredicto(_ESTADO.get("registadas", 0), _ESTADO.get("falhadas") or [])
    return _ESTADO["preparado"]


def _resumir(erro):
    texto = " ".join(str(erro).split())
    for marca in ("Failed to initialize CUDNN Frontend", "Could not locate", "CUDA error", "CUDNN_BACKEND"):
        if marca in texto:
            resto = texto[texto.find(marca):texto.find(marca) + MAX_ERRO]
            return resto
    return texto[:MAX_ERRO]


def _modelo_de_sonda():
    """O det do OCR (uma convolucao - e isso que falha sem o cuDNN completo) e, quando ele
    nao existe nesta maquina, um exemplo que viaja dentro do proprio onnxruntime."""
    pasta = _site_packages() / "rapidocr" / "models"
    for nome in MODELOS_DE_SONDA:
        alvo = pasta / nome
        if alvo.is_file():
            return alvo
    try:
        from onnxruntime.datasets import get_example

        return Path(get_example("logreg_iris.onnx"))
    except Exception:
        return None


def provar():
    """(ok, motivo): corre uma inferencia REAL na GPU. A lista de provedores nao prova nada,
    porque o onnxruntime cai para CPU em silencio quando uma DLL do cuDNN falta."""
    if "prova" in _ESTADO:
        return _ESTADO["prova"]
    pronto, motivo = preparar()
    if not pronto:
        _ESTADO["prova"] = (False, motivo)
        return _ESTADO["prova"]
    modelo = _modelo_de_sonda()
    if modelo is None:
        _ESTADO["prova"] = (False, "sem modelo de sonda no disco para provar a GPU")
        return _ESTADO["prova"]
    try:
        import numpy
        import onnxruntime

        opcoes = onnxruntime.SessionOptions()
        opcoes.log_severity_level = 3
        sessao = onnxruntime.InferenceSession(
            str(modelo), sess_options=opcoes, providers=["CUDAExecutionProvider"])
        entrada = sessao.get_inputs()[0]
        forma = [1 if not isinstance(d, int) else d for d in entrada.shape]
        if len(forma) != 4:
            forma = [1, 3, 64, 64]
        else:
            forma[0] = 1
            forma[2] = forma[3] = 64
        sessao.run(None, {entrada.name: numpy.zeros(forma, dtype=numpy.float32)})
        _ESTADO["prova"] = (True, f"inferencia real na GPU com {modelo.name}")
    except Exception as erro:
        _ESTADO["prova"] = (False, _resumir(erro))
    return _ESTADO["prova"]


def provedores():
    try:
        import onnxruntime
        return list(onnxruntime.get_available_providers())
    except Exception:
        return []


def versao_onnxruntime():
    try:
        import onnxruntime
        return getattr(onnxruntime, "__version__", "")
    except Exception:
        return ""


def resumo():
    """Uma linha para o relato de hardware, com o veredicto da sonda e nao da lista."""
    ok, motivo = provar()
    versao = versao_onnxruntime() or "ausente"
    if ok:
        return f"Aceleracao por GPU no Python: SIM - onnxruntime {versao}, {motivo}."
    return (f"Aceleracao por GPU no Python: NAO - onnxruntime {versao}; {motivo}. "
            "Tudo o que se importa aqui (OCR, visao, malhas) corre na CPU.")
