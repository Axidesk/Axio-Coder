"""Arquivo de teste simples para validar o ambiente Python."""


def somar(a: int, b: int) -> int:
    """Retorna a soma de dois números inteiros."""
    return a + b


def saudacao(nome: str) -> str:
    """Retorna uma mensagem de saudação."""
    return f"Olá, {nome}! Tudo pronto para testar. ✅"


def multiplicar(a: int, b: int) -> int:
    """Retorna o produto de dois números inteiros."""
    return a * b


if __name__ == "__main__":
    print(saudacao("Axio Coder"))
    print(f"2 + 2 = {somar(2, 2)}")
    print(f"3 x 4 = {multiplicar(3, 4)}")
    print("Teste concluído com sucesso! 🚀")
