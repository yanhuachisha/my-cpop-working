from app.agent.rag import SearchIndexManager


if __name__ == "__main__":
    print(SearchIndexManager.from_env().initialize())
