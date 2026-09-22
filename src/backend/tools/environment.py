import importlib.util
import os
import sys

from src.backend.state import estado, emit_event
from src.backend.tools.registry import register, tool_names
from src.backend.services.file_service import versao_pacote, venv_projeto, dirs_leitura_extra
from src.backend.services.hardware import relato_maquina
from src.backend.services.process_manager import detectar_shell

CAPACIDADES = (
    ("Imagem: abrir, recortar e converter (.png .jpg .gif .webp .bmp .ico)", "PIL", "pillow"),
    ("Imagem: analise por pixel e visao de ecra (.png .jpg)", "cv2", "opencv-python"),
    ("PDF: ler texto e renderizar a pagina (.pdf)", "pymupdf", "pymupdf"),
    ("OCR: texto de imagem e de pagina de PDF (foto, prancha, cota)", "rapidocr", "rapidocr"),
    ("IFC/BIM: criar, ler e medir o modelo (.ifc)", "ifcopenshell", "ifcopenshell"),
    ("CAD: ler e criar desenho vetorial (.dxf)", "ezdxf", "ezdxf"),
    ("CAD 3D: criar e ler solido B-rep e gravar STEP para CAD mecanico (.step)", "cadquery", "cadquery"),
    ("Geometria 2D: booleanas, areas e distancias", "shapely", "shapely"),
    ("Malhas 3D: ler e medir (.stl .obj .glb)", "trimesh", "trimesh"),
    ("Arrays e algebra numerica", "numpy", "numpy"),
    ("Graficos: desenhar dados em imagem (.png .svg)", "matplotlib", "matplotlib"),
    ("HTML: extrair dados de paginas", "bs4", "beautifulsoup4"),
    ("Planilha: ler e criar (.xlsx)", "openpyxl", "openpyxl"),
    ("Documento: ler e criar (.docx)", "docx", "python-docx"),
    ("Audio: ler e analisar (.wav .flac)", "soundfile", "soundfile"),
)

@register(
    "tool_info_ambiente",
    'Retorna metadados do ambiente: caminho do venv em uso, versões de Python, Mempalace e ChromaDB, diretórios de leitura permitidos e estado do palace do mempalace. Traz também o relatório de CAPACIDADES por família de formato (imagem, PDF, OCR, IFC/BIM, CAD/DXF, CAD 3D/STEP, malhas 3D, planilha, documento, áudio) — é aqui que se responde "eu consigo ler/criar este formato?" antes de dizer que não: cada família mostra OK com a versão ou FALTA com o pacote pip candidato. E traz o PODER DA MAQUINA medido (CPU com nucleos e threads, RAM com pentes e velocidade, placa de video com VRAM total e livre, driver, compute capability, temperatura, discos, e se o Python que corre o Axio tem aceleracao por GPU) mais o veredito do que cabe nesta maquina — é aqui que se responde "esta maquina aguenta isto?" antes de propor um modelo de IA, uma dependencia pesada ou mais poder de interface, sem ter de adivinhar nem pedir ao utilizador para medir.',
    {
    },
)
def tool_info_ambiente():
    emit_event("executing", function="Coletando informações do ambiente")
    raiz = estado.get("pasta_raiz") or "(nenhuma)"
    shell = detectar_shell()
    linhas = [
        f"Pasta raiz: {raiz}",
        f"Shell do terminal (painel do Axio): {shell.get('nome')} -> {shell.get('cmd')}",
        "Shell das ferramentas (tool_executar_processo): cmd.exe via subprocess shell=True (allowlist por executavel)",
        f"Venv em uso (Axio): {sys.prefix}",
        f"Executável Python: {sys.executable}",
        f"Versão Python: {sys.version.split()[0]}",
        f"Versão Mempalace: {versao_pacote('mempalace')}",
        f"Versão ChromaDB: {versao_pacote('chromadb')}",
        f"Ferramentas registadas (tools/registry.py): {len(tool_names())}",
    ]
    venv_proj = venv_projeto()
    if venv_proj:
        linhas.append(f"Venv do projeto selecionado: {venv_proj['dir']} (python: {venv_proj['python']})")
    else:
        linhas.append("Venv do projeto selecionado: nenhum (crie com 'python -m venv .venv' se o projeto precisar de dependências próprias)")
    extras = dirs_leitura_extra()
    linhas.append("Diretórios de leitura permitidos (além da pasta raiz): " + (", ".join(extras) if extras else "(nenhum)"))
    palace = os.path.expanduser("~/.mempalace/palace")
    if os.path.isdir(palace):
        linhas.append(f"Palace do mempalace: {palace}")
        linhas.append(f"chroma.sqlite3 presente: {os.path.isfile(os.path.join(palace, 'chroma.sqlite3'))}")
        linhas.append("Dica: se buscas filtradas por wing falharem, rode 'mempalace repair' (issue #1035 do MemPalace).")
    else:
        linhas.append("Palace do mempalace: não encontrado.")
    linhas.append(relato_maquina())
    linhas.extend(_capacidades())
    return "\n".join(linhas)


def _capacidades():
    """Bloco de capacidades por familia de formato: o que este ambiente ja sabe ler e escrever."""
    linhas = ["Capacidades por familia de formato (FALTA = sem leitor instalado; o candidato e o pacote pip):"]
    for rotulo, modulo, pacote in CAPACIDADES:
        try:
            presente = importlib.util.find_spec(modulo) is not None
        except Exception:
            presente = False
        if not presente:
            linhas.append(f"  FALTA  {rotulo}: candidato -> pip install {pacote}")
            continue
        try:
            versao = versao_pacote(pacote)
        except Exception:
            versao = "?"
        linhas.append(f"  OK     {rotulo}: {modulo} {versao}")
    return linhas
