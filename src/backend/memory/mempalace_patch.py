def abrir_client(palace_path):
    """Abre (ou reaproveita) o PersistentClient do palace com as migracoes do mempalace 3.9.0.

    O ChromaBackend._client aplica _prepare_palace_for_open antes de construir o
    PersistentClient: _fix_missing_collection_type (marcador _type que o chromadb
    1.5.9+ exige e palaces construidos em <=1.5.8 nao gravaram), _fix_blob_seq_ids
    e as quarantines de HNSW. Abrir o PersistentClient direto, sem esse pass, faz
    um palace antigo travar ou falhar na primeira query sob chromadb 1.5.9.
    """
    from mempalace.backends.registry import get_backend

    return get_backend("chroma")._client(palace_path)


def aplicar_patch():
    """No-op desde o mempalace 3.9.0.

    A sobrescrita antiga de ChromaBackend.get_collection ficou redundante e
    prejudicial: o mempalace 3.9.0 ja cacheia o client (ChromaBackend._client),
    aplica as migracoes (_prepare_palace_for_open), resolve a embedding function
    e serializa as escritas (ChromaCollection._write_lock). Sobrescrever o
    get_collection com a versao antiga abria o PersistentClient direto, sem o
    pass de migracao, o que fazia palaces antigos (chromadb <=1.5.8) travarem
    na abertura com chromadb 1.5.9.
    """
    return None
