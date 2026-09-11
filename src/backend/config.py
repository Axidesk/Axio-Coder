import os

APP_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(APP_ROOT, "data")

def caminho_data(*partes):
    return os.path.join(DATA_DIR, *partes)

def carregar_env(caminho=None):
    if caminho is None:
        caminho = os.path.join(APP_ROOT, ".env")
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if not linha or linha.startswith("#") or "=" not in linha:
                    continue
                chave, valor = linha.split("=", 1)
                chave = chave.strip()
                valor = valor.strip().strip('"').strip("'")
                if chave not in os.environ:
                    os.environ[chave] = valor
    except FileNotFoundError:
        pass
