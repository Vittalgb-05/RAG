import os
import streamlit as st
from pdf_reader import PdfReader
from local_embedding import LocalEmbedding

try:
    from groq import Groq
except ImportError:
    Groq = None

class AiModel():
    def __init__(self):
        '''
            Initializes the AI model using the Groq API.
        '''
        print("running checks to make sure everything is good...")
        
        self.model_name = os.environ.get("GROQ_MODEL_NAME", "llama-3.1-8b-instant")
        if not Groq:
            raise ImportError("groq package is missing. Please run `pip install groq`.")
            
        # Try to get API key from Streamlit Secrets (for deployment), fallback to .env (for local development)
        try:
            api_key = st.secrets["GROQ_API_KEY"]
        except (KeyError, FileNotFoundError):
            api_key = os.environ.get("GROQ_API_KEY")
            
        if not api_key:
            raise ValueError("GROQ_API_KEY is not set. Please add it to your Streamlit secrets or .env file.")
        
        print(f"Initializing Groq client for fast inference using {self.model_name}...")
        self.groq_client = Groq(api_key=api_key)


    def ask_a_question_from_pdf_stream(self, pdf_path: str, prompt: str = "tell me what is this pdf about", local_embedding=None, chat_history=None):
        '''
            Streaming variant of ask_a_question_from_pdf.
            Yields decoded text chunks in real time.
        '''
        if local_embedding is None:
            pdf_reader = PdfReader(pdf_path)
            pdf_paragraphs = pdf_reader.get_paragraphs()
            local_embedding = LocalEmbedding()
            local_embedding.build_index(pdf_paragraphs)

        # Contextualize the search query by prepending the last user question
        search_query = prompt
        if chat_history:
            last_user_msgs = [m["content"] for m in chat_history if m["role"] == "user"]
            if last_user_msgs:
                search_query = f"{last_user_msgs[-1]} {prompt}"

        relevant_sections = local_embedding.get_context(search_query, k=10)
        
        system_content = f"""You are a helpful AI assistant. Answer the user's question based *only* on the provided Document Text and the Conversation History. 
If the answer is not found in the document or history, say "The document does not contain information on this topic." Do not use any prior knowledge.

Document Text:
---
{relevant_sections}
---"""

        messages = [{"role": "system", "content": system_content}]
        
        if chat_history:
            for msg in chat_history:
                messages.append({"role": msg["role"], "content": msg["content"]})
                
        messages.append({"role": "user", "content": prompt})

        # Deployment Mode: Groq Cloud Inference
        stream = self.groq_client.chat.completions.create(
            messages=messages,
            model=self.model_name,
            stream=True,
            max_tokens=1024,
        )
        for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
