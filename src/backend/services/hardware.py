import importlib.util
import os
import re
import shutil
import subprocess

_SEM_JANELA = 0x08000000
_ESTATICO = {}

_CARGAS_CONHECIDAS = (
    ("OCR e deteccao leve (RapidOCR, YOLO pequeno)", 1.0),
    ("Depth Anything V2 (profundidade a partir de uma foto)", 1.5),
    ("SAM 2 (segmentacao assistida)", 2.4),
    ("Hunyuan3D-2mv (malha a partir de frente/lado/costas)", 6.0),
    ("TRELLIS.2 (imagem -> 3D, o melhor aberto)", 24.0),
)


def _sem_janela():
    return _SEM_JANELA if os.name == "nt" else 0


def _wmi(classe, campos, onde=""):
    import win32com.client

    localizador = win32com.client.Dispatch("WbemScripting.SWbemLocator")
    servico = localizador.ConnectServer(".", "root\\cimv2")
    consulta = f"SELECT {', '.join(campos)} FROM {classe}" + (f" WHERE {onde}" if onde else "")
    itens = []
    for bruto in servico.ExecQuery(consulta):
        itens.append({campo: getattr(bruto, campo, None) for campo in campos})
    return itens


def _inteiro(valor):
    """O WMI devolve inteiros grandes como texto (Capacity, Size): isto forca o tipo."""
    try:
        return int(valor)
    except (TypeError, ValueError):
        return 0


def _gb(bytes_):
    if not bytes_:
        return 0.0
    return round(float(bytes_) / (1024 ** 3), 1)


def _consumir_wmi(classe, campos, onde=""):
    try:
        return _wmi(classe, campos, onde)
    except Exception:
        return []


def _gpus_nvidia():
    exe = shutil.which("nvidia-smi")
    if not exe:
        return [], ""
    base = "name,memory.total,memory.free,driver_version,utilization.gpu,temperature.gpu"
    placas, cuda = [], ""
    for campos in (f"{base},compute_cap", base):
        try:
            r = subprocess.run(
                [exe, f"--query-gpu={campos}", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=20, creationflags=_sem_janela(),
            )
        except Exception:
            continue
        if r.returncode != 0 or not r.stdout.strip():
            continue
        nomes = [c.strip() for c in campos.split(",")]
        for linha in r.stdout.strip().splitlines():
            valores = [v.strip() for v in linha.split(",")]
            placas.append(dict(zip(nomes, valores)))
        break
    try:
        r = subprocess.run([exe], capture_output=True, text=True, timeout=20, creationflags=_sem_janela())
        achado = re.search(r"CUDA Version:\s*([\d.]+)", r.stdout)
        cuda = achado.group(1) if achado else ""
    except Exception:
        pass
    return placas, cuda


def _aceleracao():
    from src.backend.services.aceleracao import provedores, versao_onnxruntime

    dados = {"onnxruntime": versao_onnxruntime(), "providers": provedores(),
             "torch": "", "torch_cuda": False, "cv2": "", "cv2_cuda": 0}
    if importlib.util.find_spec("torch") is not None:
        try:
            import torch
            dados["torch"] = torch.__version__
            dados["torch_cuda"] = bool(torch.cuda.is_available())
        except Exception:
            pass
    try:
        import cv2
        dados["cv2"] = cv2.__version__
        dados["cv2_cuda"] = int(cv2.cuda.getCudaEnabledDeviceCount())
    except Exception:
        pass
    return dados


def _medir_estatico():
    if _ESTATICO:
        return _ESTATICO
    estatico = {"cpu": {}, "pentes_ram": [], "placas_nvidia": [], "cuda_max": "",
                "adaptadores": [], "discos": [], "aceleracao": {}}
    for item in _consumir_wmi("Win32_Processor",
                              ["Name", "NumberOfCores", "NumberOfLogicalProcessors", "MaxClockSpeed", "AddressWidth"]):
        estatico["cpu"] = {
            "nome": (item.get("Name") or "").strip(),
            "nucleos": _inteiro(item.get("NumberOfCores")),
            "threads": _inteiro(item.get("NumberOfLogicalProcessors")),
            "mhz": _inteiro(item.get("MaxClockSpeed")),
            "bits": _inteiro(item.get("AddressWidth")),
        }
        break
    for item in _consumir_wmi("Win32_PhysicalMemory", ["Capacity", "Speed"]):
        estatico["pentes_ram"].append({"bytes": _inteiro(item.get("Capacity")), "mhz": _inteiro(item.get("Speed"))})
    for item in _consumir_wmi("Win32_VideoController", ["Name", "AdapterRAM", "DriverVersion", "AdapterCompatibility"]):
        estatico["adaptadores"].append({
            "nome": (item.get("Name") or "").strip(),
            "vram_wmi": _inteiro(item.get("AdapterRAM")),
            "driver": item.get("DriverVersion") or "",
            "fabricante": (item.get("AdapterCompatibility") or "").strip(),
        })
    placas, cuda = _gpus_nvidia()
    estatico["placas_nvidia"] = placas
    estatico["cuda_max"] = cuda
    for item in _consumir_wmi("Win32_LogicalDisk", ["DeviceID", "Size", "FreeSpace"], "DriveType=3"):
        estatico["discos"].append({
            "letra": (item.get("DeviceID") or "").strip().rstrip(":"),
            "total": _inteiro(item.get("Size")),
            "livre": _inteiro(item.get("FreeSpace")),
        })
    estatico["aceleracao"] = _aceleracao()
    _ESTATICO.update(estatico)
    return _ESTATICO


def _ram():
    for item in _consumir_wmi("Win32_OperatingSystem", ["TotalVisibleMemorySize", "FreePhysicalMemory"]):
        return (_inteiro(item.get("FreePhysicalMemory")) * 1024,
                _inteiro(item.get("TotalVisibleMemorySize")) * 1024)
    return 0, 0


def medir_maquina():
    estatico = _medir_estatico()
    ram_livre, ram_visivel = _ram()
    placas, _ = _gpus_nvidia()
    if placas:
        vivo = {
            "vram_total": int(float(placas[0].get("memory.total") or 0)),
            "vram_livre": int(float(placas[0].get("memory.free") or 0)),
            "uso": placas[0].get("utilization.gpu", ""),
            "temperatura": placas[0].get("temperature.gpu", ""),
        }
    else:
        vivo = {"vram_total": 0, "vram_livre": 0, "uso": "", "temperatura": ""}
    dados = dict(estatico)
    dados["vivo"] = vivo
    dados["ram_livre"] = ram_livre
    dados["ram_visivel"] = ram_visivel
    return dados


def _linhas_base(dados):
    linhas = []
    cpu = dados.get("cpu") or {}
    if cpu:
        linhas.append(f"CPU: {cpu['nome']} | {cpu['nucleos']} nucleos / {cpu['threads']} threads "
                      f"| {cpu['mhz']} MHz | {cpu['bits']} bits")
    pentes = dados.get("pentes_ram") or []
    if pentes:
        total = _gb(sum(p["bytes"] for p in pentes))
        mhz = sorted({p["mhz"] for p in pentes if p["mhz"]})
        velocidade = f" @ {mhz[0]} MHz" if mhz else ""
        linhas.append(f"RAM: {total} GB ({len(pentes)} pente(s) de {_gb(pentes[0]['bytes'])} GB{velocidade})")
    return linhas


def _linhas_placas(dados, com_vivo):
    linhas = []
    placas = dados.get("placas_nvidia") or []
    vivo = dados.get("vivo") or {}
    if not placas:
        linhas.append("GPU: nenhuma placa NVIDIA detetada pelo nvidia-smi (sem CUDA nesta maquina)")
    for i, p in enumerate(placas):
        rotulo = "GPU" if i == 0 else "GPU extra"
        parte = f"{rotulo}: {p.get('name')} | {p.get('memory.total')} MB VRAM"
        if com_vivo and i == 0:
            parte += f" ({vivo.get('vram_livre', '?')} MB livre agora)"
        parte += f" | driver {p.get('driver_version')} | compute {p.get('compute_cap', '?')}"
        if com_vivo and i == 0:
            parte += f" | uso {vivo.get('uso', '?')}% | {vivo.get('temperatura', '?')} C"
        linhas.append(parte)
    if placas:
        linhas.append(f"CUDA maxima que o driver suporta: {dados.get('cuda_max') or '?'} "
                      "(teto do driver, NAO diz qual versao esta instalada)")
    return linhas


def _linhas_adaptadores(dados):
    placas = dados.get("placas_nvidia") or []
    nomes_reais = [p.get("name", "").split(" with ")[0].strip().lower() for p in placas]
    outros = []
    for a in dados.get("adaptadores") or []:
        nome = a["nome"]
        if any(nome_real and nome_real in nome.lower() for nome_real in nomes_reais):
            continue
        if a["vram_wmi"] < 0:
            vram = f"{a['vram_wmi']} bytes (campo estourado - o WMI nao serve para VRAM)"
        elif a["vram_wmi"] > 4 * 1024 ** 3:
            vram = f"{_gb(a['vram_wmi'])} GB (acima do teto de 32 bits do WMI: desconfie)"
        else:
            vram = f"{_gb(a['vram_wmi'])} GB"
        outros.append(f"  {nome} | {vram} | driver {a['driver']}")
    if outros:
        return ["Outros adaptadores de video (WMI, para ecra - nao para computacao):"] + outros
    return []


def _linhas_aceleracao(dados):
    ac = dados.get("aceleracao") or {}
    providers = ac.get("providers") or []
    gpu, motivo = _veredicto_gpu()
    linhas = [f"Aceleracao por GPU no Python do Axio: {'SIM' if gpu else 'NAO'} - "
              f"onnxruntime {ac.get('onnxruntime') or '?'}; {motivo}."]
    if gpu:
        if ac.get("torch_cuda"):
            linhas.append(f"  torch {ac.get('torch')} com CUDA disponivel")
        if ac.get("cv2_cuda"):
            linhas.append(f"  OpenCV {ac.get('cv2')} com {ac['cv2_cuda']} dispositivo(s) CUDA")
        linhas.append("  O OCR e a visao que correm por onnxruntime usam a placa; o que nao tiver "
                      "caminho CUDA continua na CPU.")
        return linhas
    threads = (dados.get("cpu") or {}).get("threads", "?")
    linhas.append(f"  Provedores declarados: {providers or 'nenhum'} - a lista NAO e prova: o onnxruntime "
                  "cai para CPU em silencio quando falta uma DLL do cuDNN.")
    linhas.append(f"  Consequencia: qualquer modelo de IA importado aqui (OCR, visao, malhas) corre na CPU ({threads} threads).")
    return linhas


def _veredicto_gpu():
    """O veredicto sai de uma inferencia real (services/aceleracao.provar), nunca da lista de provedores."""
    try:
        from src.backend.services.aceleracao import provar

        return provar()
    except Exception as erro:
        return False, f"sonda indisponivel ({type(erro).__name__})"


def relato_maquina():
    dados = medir_maquina()
    linhas = ["=== PODER DA MAQUINA (medido agora, nesta maquina) ==="]
    linhas.extend(_linhas_base(dados))
    if dados.get("ram_livre"):
        linhas.append(f"RAM livre agora: {_gb(dados['ram_livre'])} GB de {_gb(dados.get('ram_visivel'))} GB visiveis")
    linhas.extend(_linhas_placas(dados, com_vivo=True))
    linhas.extend(_linhas_adaptadores(dados))
    for d in dados.get("discos") or []:
        linhas.append(f"Disco {d['letra']}: {_gb(d['livre'])} GB livres de {_gb(d['total'])} GB")
    linhas.extend(_linhas_aceleracao(dados))
    vivo = dados.get("vivo") or {}
    vram_total = int(vivo.get("vram_total") or 0)
    vram_livre = int(vivo.get("vram_livre") or 0)
    linhas.append(f"O que cabe nesta maquina (VRAM livre hoje: {vram_livre} MB de {vram_total} MB):")
    for rotulo, exigido in _CARGAS_CONHECIDAS:
        precisa_mb = exigido * 1024
        if not vram_total:
            veredito = "sem placa NVIDIA"
        elif precisa_mb <= vram_livre * 0.8:
            veredito = "cabe, com a folga de agora"
        elif precisa_mb <= vram_total * 0.8:
            veredito = "cabe na placa toda, mas nao na VRAM livre de agora"
        else:
            veredito = "NAO CABE nesta placa"
        linhas.append(f"  ~{exigido:g} GB de pesos | {rotulo}: {veredito}")
    linhas.append("  Regra de bolso: so cabe se a VRAM livre for ~1,3x os pesos (somam-se ativacoes e contexto). "
                  "Com a aceleracao por GPU provada acima, 'caber' quer dizer correr na placa; sem ela, nao queria dizer nada.")
    linhas.append("  As exigencias acima vem da documentacao dos projetos e mudam de versao: confirme a versao "
                  "atual antes de instalar (tool_verificar_dependencias).")
    return "\n".join(linhas)


def resumo_da_maquina():
    dados = _medir_estatico()
    linhas = ["=== MAQUINA (medido no arranque) ==="]
    linhas.extend(_linhas_base(dados))
    linhas.extend(_linhas_placas(dados, com_vivo=False))
    for d in dados.get("discos") or []:
        linhas.append(f"Disco {d['letra']}: {_gb(d['total'])} GB totais")
    linhas.extend(_linhas_aceleracao(dados))
    linhas.append("Antes de propor algo que exija potencia (modelo de IA, GPU, RAM), chame tool_info_ambiente: "
                  "la esta o mesmo, com a VRAM e a RAM livres de agora e o que cabe.")
    return "\n".join(linhas) + "\n"
