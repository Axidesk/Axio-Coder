from dataclasses import dataclass

from src.backend.geometry.pecas import volume_previsto


@dataclass(frozen=True)
class Nivel:
    nome: str
    elevacao: float
    descricao: str = ""


@dataclass(frozen=True)
class Material:
    nome: str
    cor: tuple
    transparencia: float = 0.0
    brilho: float = 0.0


@dataclass(frozen=True)
class Grupo:
    nome: str
    descricao: str = ""
    pecas: tuple = ()


@dataclass(frozen=True)
class Documento:
    identificacao: str
    nome: str
    descricao: str = ""
    pecas: tuple = ()


@dataclass(frozen=True)
class Modelo:
    nome: str
    pecas: tuple
    descricao: str = ""
    autor: str = "Axio Coder"
    niveis: tuple = ()
    materiais: tuple = ()
    grupos: tuple = ()
    documentos: tuple = ()

    def volumes_previstos(self):
        return {peca.nome: volume_previsto(peca) for peca in self.pecas}
