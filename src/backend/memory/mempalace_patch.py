import os


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
    """Impede o mempalace de reconstruir o client a cada escrita no palace.

    O ChromaBackend._client guarda o client em cache e reabre-o quando a
    assinatura (inode, mtime) do chroma.sqlite3 muda. Cada escrita nossa muda o
    mtime - e quem esta a MEIO de uma escrita, o proprio minerador, fica com a
    collection a apontar para um System ja parado: o delete das drawers antigas
    falha com "'RustBindingsAPI' object has no attribute 'bindings'" e a busca
    semantica cai em "timeout ao acessar banco de memorias".

    Fixar o mtime em zero mantem a detecao da TROCA do ficheiro (inode, o caso
    do palace reconstruido) e deixa de disparar a cada commit. O ChromaDB le o
    SQLite em cada consulta, logo nao ha dado em cache a ficar velho.

    O resto do que aqui estava (sobrescrever get_collection) ficou redundante e
    prejudicial a partir do mempalace 3.9.0: ele ja cacheia o client, aplica as
    migracoes e serializa as escritas.
    """
    try:
        from mempalace.backends.chroma import ChromaBackend
    except Exception:
        return None
    if getattr(ChromaBackend, "_axio_sem_mtime", False):
        return False

    @staticmethod
    def _db_stat_estavel(palace_path):
        try:
            st = os.stat(os.path.join(palace_path, "chroma.sqlite3"))
            return (st.st_ino, 0.0)
        except OSError:
            return (0, 0.0)

    ChromaBackend._db_stat = _db_stat_estavel
    ChromaBackend._axio_sem_mtime = True
    return True
