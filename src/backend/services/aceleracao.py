"""Aceleracao por GPU para o que corre dentro do Python do Axio.

O onnxruntime-gpu sozinho nao chega: o cuDNN 9 e modular e o preload_dlls() do
onnxruntime nao carrega as sub-bibliotecas (engines_tensor_ir, engines_precompiled,
heuristic, ops, graph), o que faz a primeira convolucao falhar com
CUDNN_BACKEND_API_FAILED e cair para CPU EM SILENCIO - o provider aparece na lista
e a inferencia corre na mesma, so que devagar. Aqui as DLLs sao registadas e
pre-carregadas por ordem, e o veredicto sai de uma inferencia a SERIO, nunca da
lista de provedores.

Caso real medido a 2026-09-22 nesta maquina (GTX 1660 Ti Max-Q, driver 576.02):
sem este pre-carga o OCR ficava em 1,27 s por imagem e a VRAM nao mexia; com ele,
0,0154 s contra 0,2941 s na CPU - 19x, com a VRAM a subir de 1912 para 2124 MB.

O driver 576.02 tem como teto CUDA 12.9, logo a versao certa e onnxruntime-gpu
1.26.0 (build CUDA 12.8). Da 1.27 em diante os pacotes do PyPI sao CUDA 13.0 e
exigem driver >= 580 - instalar a mais recente dava erro de DLL.
"""
import ctypes
import os
import sysconfig
from pathlib import Path

SUBPACOTES_NVIDIA = ("cudnn", "cublas", "cufft", "curand", "cuda_runtime", "cuda_nvrtc", "nvjitlink")

DLLS_CUDNN_POR_ORDEM = (
    "cudnn_ops64_9.dll",
    "cudnn_cnn64_9.dll",
    "cudnn_graph64_9.dll",
    "cudnn_adv64_9.dll",
    "cudnn_heuristic64_9.dll",
    "cudnn_engines_precompiled64_9.dll",
    "cudnn_engines_runtime_compiled64_9.dll",
    "cudnn_engines_tensor_ir64_9.dll",
    "cudnn_ext64_9.dll",
    "cudnn64_9.dll",
)

MODELOS_DE_SONDA = ("PP-OCRv6_det_small.onnx", "PP-OCRv6_rec_small.onnx")

MAX_ERRO = 220

_ESTADO = {}


def _site_packages():
    return Path(sysconfig.get_paths()["purelib"])


def _pastas_bin():
    raiz = _site_packages() / "nvidia"
    return [raiz / sub / "bin" for sub in SUBPACOTES_NVIDIA]


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


def precarregar_cudnn():
    """Carrega as sub-bibliotecas do cuDNN por ordem de dependencia. Devolve as que falharam."""
    pasta = _site_packages() / "nvidia" / "cudnn" / "bin"
    if not pasta.is_dir():
        return ["cuDNN ausente"]
    falhadas = []
    for nome in DLLS_CUDNN_POR_ORDEM:
        alvo = pasta / nome
        if not alvo.is_file():
            continue
        try:
            ctypes.CDLL(str(alvo))
        except OSError:
            falhadas.append(nome)
    return falhadas


def preparar():
    """(ok, motivo): regista as pastas e pre-carrega o cuDNN uma so vez por processo."""
    if "preparado" in _ESTADO:
        return _ESTADO["preparado"]
    try:
        registadas = registar_dlls()
        falhadas = precarregar_cudnn()
    except Exception as erro:
        _ESTADO["preparado"] = (False, f"falhou ao preparar as DLLs ({type(erro).__name__})")
        return _ESTADO["preparado"]
    if falhadas:
        _ESTADO["preparado"] = (False, "DLLs do cuDNN que nao carregaram: " + ", ".join(falhadas[:3]))
    elif not registadas:
        _ESTADO["preparado"] = (False, "runtime CUDA do pip ausente (pip install onnxruntime-gpu[cuda,cudnn])")
    else:
        _ESTADO["preparado"] = (True, f"{registadas} pasta(s) de runtime registadas")
    return _ESTADO["preparado"]


def _resumir(erro):
    texto = " ".join(str(erro).split())
    for marca in ("Failed to initialize CUDNN Frontend", "Could not locate", "CUDA error", "CUDNN_BACKEND"):
        if marca in texto:
            resto = texto[texto.find(marca):texto.find(marca) + MAX_ERRO]
            return resto
    return texto[:MAX_ERRO]


def _modelo_de_sonda():
    pasta = _site_packages() / "rapidocr" / "models"
    for nome in MODELOS_DE_SONDA:
        alvo = pasta / nome
        if alvo.is_file():
            return alvo
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
