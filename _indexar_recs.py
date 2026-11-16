import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.backend.tools.gravacoes import indexar_gravacoes


def progresso(posicao, total, nome):
    if posicao % 20 == 0 or posicao == total:
        print(f"[{posicao}/{total}] {nome}", flush=True)


_, relato = indexar_gravacoes(progresso=progresso)
print(relato, flush=True)
