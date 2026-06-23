# -*- coding: utf-8 -*-
from rag_store import build_index

if __name__ == "__main__":
    n = build_index(include_cycles=True)
    print("RAG index rebuilt. Chunks indexed: {}".format(n))
