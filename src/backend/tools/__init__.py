"""Ferramentas do agente.

O registo vive em tools/registry.py: cada modulo declara as suas ferramentas com
@register e fica registado quando e importado (o ai/loop.py importa os modulos de
ferramentas exatamente por esse efeito). Este __init__ nao carrega nada de
proposito - importar o pacote nao deve arrastar todas as ferramentas.
"""
