import os
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from transformers import TextStreamer, TextIteratorStreamer
from threading import Thread
from pdf_reader import PdfReader
from local_embedding import LocalEmbedding
from huggingface_hub import login

try:
    from groq import Groq
except ImportError:
    Groq = None

class AiModel():
    def __init__(self):
        '''
            Initializes the AI model based on the LLM_MODE environment variable.
            If LLM_MODE=groq, uses the ultra-fast Groq API with Llama 3.
            If LLM_MODE=local, uses local HuggingFace generation (e.g. Qwen 3B).
        '''
        self.mode = os.environ.get("LLM_MODE", "groq").lower()
        
        print("running checks to make sure everything is good...")
        
        if self.mode == "local":
            self.model_name = os.environ.get("LOCAL_MODEL_NAME", "Qwen/Qwen2.5-3B-Instruct")
            self.hugging_face_auth()
            self.hardware_check()
            print("we are creating the model this might take a while please wait...")
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_name, trust_remote_code=True)
            self.model = AutoModelForCausalLM.from_pretrained(
                pretrained_model_name_or_path=self.model_name, 
                torch_dtype="auto", 
                device_map="auto"
            )
        else:
            self.model_name = os.environ.get("GROQ_MODEL_NAME", "llama-3.1-8b-instant")
            if not Groq:
                raise ImportError("groq package is missing. Please run `pip install groq`.")
            api_key = os.environ.get("GROQ_API_KEY")
            if not api_key:
                raise ValueError("GROQ_API_KEY environment variable is not set. Please add it to your .env file.")
            
            print(f"Initializing Groq client for fast inference using {self.model_name}...")
            self.groq_client = Groq(api_key=api_key)
            self.tokenizer = None
            self.model = None

    def hardware_check(self):
        '''
            making sure we are working on a local GPU rather than CPU to take advantage of Local LLMs
        '''
        if torch.cuda.is_available():
            print(f"GPU detected: {torch.cuda.get_device_name(0)}")
        else:
            print("WARNING: No GPU detected.")
    
    def hugging_face_auth(self):
        '''
            in order to download the right model to work on some of the model are gated by HuggingFace therefore we must authenticate first
        '''
        HUGGING_FACE_TOKEN = os.environ.get("HF_TOKEN")
        if not HUGGING_FACE_TOKEN or HUGGING_FACE_TOKEN.strip() == "":
            print("No HF_TOKEN environment variable found or it is empty. Skipping login (Qwen is public).")
            return

        print("Attempting Hugging Face login...")
        try:
            login(token=HUGGING_FACE_TOKEN.strip())
            print("Login successful!")
        except Exception as e:
            print(f"Hugging Face login failed: {e}. Attempting to proceed without authentication...")

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

        if self.mode == "local":
            formatted = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            inputs = self.tokenizer(formatted, return_tensors="pt").to(self.model.device)

            # TextIteratorStreamer stores tokens in a Queue instead of printing to stdout.
            streamer = TextIteratorStreamer(
                self.tokenizer, skip_prompt=True, skip_special_tokens=True, timeout=300.0
            )

            thread = Thread(
                target=self.model.generate,
                kwargs=dict(**inputs, max_new_tokens=1000, streamer=streamer),
                daemon=True,
            )
            thread.start()

            for chunk in streamer:
                yield chunk

            thread.join()
            
        else:
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


    def full_prompt_for_rag(self, relevent_sections, question_prompt):
        '''
            this is a prompt constructor that will put together the user question, the pdf relevant sections, and system prompt
        '''
        return f"""
            <|system|>
                You are an AI assistant. Answer the following question based *only* on the provided document text. 
                If the answer is not found in the document, say "The document does not contain information on this topic." Do not use any prior knowledge.

                Document Text:
                ---
                    {relevent_sections}
                ---
            <|end|>
            |user|>
                Question: {question_prompt}
            <|end|>
            <|assistant|>
                Answer:
    """
