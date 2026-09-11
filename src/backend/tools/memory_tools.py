import os

from src.backend.memory.store import garantir_pasta_knowledge, nome_arquivo_seguro, dedup_nota
from src.backend.memory.vector import salvar_memoria_no_vetor, excluir_memoria_do_vetor, varrer_memoria_vetor, reparar_memoria_vetor
from src.backend.state import emit_event

def tool_gerenciar_memoria(acao: str, titulo: str = None, conteudo: str = None):
    emit_event("executing", function="Gerenciando memoria")
    pasta = garantir_pasta_knowledge()
    if acao == "escrever" and titulo and conteudo:
        nome_seguro = nome_arquivo_seguro(titulo)
        duplicata = dedup_nota(titulo, conteudo)
        if duplicata:
            return duplicata
        with open(os.path.join(pasta, f"{nome_seguro}.md"), "w", encoding="utf-8") as f:
            f.write(conteudo)
        status_vetor = salvar_memoria_no_vetor(titulo, conteudo)
        if status_vetor == "ok":
            return f"Memória '{titulo}' atualizada e gravada no mempalace."
        return f"Memória '{titulo}' atualizada (.md). Gravação no vetor: {status_vetor}."
    elif acao == "ler" and titulo:
        nome_seguro = nome_arquivo_seguro(titulo)
        caminho = os.path.join(pasta, f"{nome_seguro}.md")
        if os.path.exists(caminho):
            with open(caminho, "r", encoding="utf-8") as f:
                return f.read()
        return "Nota não encontrada."
    elif acao == "excluir" and titulo:
        nome_seguro = nome_arquivo_seguro(titulo)
        caminho = os.path.join(pasta, f"{nome_seguro}.md")
        if not os.path.exists(caminho):
            return "Nota não encontrada."
        os.remove(caminho)
        status_vetor = excluir_memoria_do_vetor(titulo)
        if status_vetor == "ok":
            return f"Memória '{titulo}' excluída (.md) e removida do mempalace."
        return f"Memória '{titulo}' excluída (.md). Remoção no vetor: {status_vetor}."
    elif acao == "listar":
        return ", ".join([f.replace(".md", "") for f in os.listdir(pasta) if f.endswith(".md")])
    return "Ação inválida."

def tool_gerenciar_banco_vetorial(acao: str, caminho_relativo: str = "", conteudo: str = None):
    emit_event("executing", function="Gerenciando banco vetorial")
    pasta_banco = os.path.expanduser("~/.mempalace/palace")
    if not os.path.exists(pasta_banco):
        return "Banco de dados vetorial não encontrado."
    
    if acao == "varredura":
        return varrer_memoria_vetor()
    elif acao == "reparar":
        return reparar_memoria_vetor()
    elif acao == "listar":
        caminho_alvo = os.path.join(pasta_banco, caminho_relativo)
        if not os.path.exists(caminho_alvo):
            return f"Caminho {caminho_relativo} não existe."
        if os.path.isdir(caminho_alvo):
            return ", ".join(os.listdir(caminho_alvo))
        return "Não é um diretório."
    elif acao == "ler":
        caminho_alvo = os.path.join(pasta_banco, caminho_relativo)
        if os.path.exists(caminho_alvo) and os.path.isfile(caminho_alvo):
            with open(caminho_alvo, "r", encoding="utf-8") as f:
                return f.read()
        return "Arquivo não encontrado."
    elif acao == "deletar":
        caminho_alvo = os.path.join(pasta_banco, caminho_relativo)
        if os.path.exists(caminho_alvo):
            if os.path.isdir(caminho_alvo):
                import shutil
                shutil.rmtree(caminho_alvo)
            else:
                os.remove(caminho_alvo)
            return f"{caminho_relativo} deletado com sucesso."
        return "Caminho não encontrado."
    elif acao == "escrever" and conteudo is not None:
        caminho_alvo = os.path.join(pasta_banco, caminho_relativo)
        with open(caminho_alvo, "w", encoding="utf-8") as f:
            f.write(conteudo)
        return f"Arquivo {caminho_relativo} escrito com sucesso."
    return "Ação inválida."
