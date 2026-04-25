from config.settings import settings

class ContextBuilder:
    @staticmethod
    def build(documents: list) -> str:
        if not documents: return ""
        
        seen_texts = set()
        unique_docs = []
        for doc in documents:
            if doc['text'] not in seen_texts:
                seen_texts.add(doc['text'])
                unique_docs.append(doc)

        context_parts = []
        current_length = 0
        max_len = getattr(settings, 'MAX_CONTEXT_LENGTH', 12000)
        for doc in unique_docs:
            snippet = f"[Nguồn: {doc['source']}]\n{doc['text']}\n---"
            if current_length + len(snippet) > max_len:
                print("  [Builder] Token Limit Reached -> Truncating Context")
                break
            context_parts.append(snippet)
            current_length += len(snippet)

        return "\n".join(context_parts)