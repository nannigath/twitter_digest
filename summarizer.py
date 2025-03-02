# summarizer.py
import os
from langchain import PromptTemplate
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain.schema import StrOutputParser
from prompts import PROMPTS  # Import the prompts dictionary

class SummaryGenerator:
    def __init__(self, model_type="openai", openai_api_key=None, google_api_key=None):
        """Initialize with model type and API keys."""
        self.model_type = model_type.lower()
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        self.google_api_key = google_api_key or os.getenv("GOOGLE_API_KEY")

        if self.model_type == "openai" and not self.openai_api_key:
            raise ValueError("OpenAI API key not provided or found in environment variables.")
        if self.model_type == "gemini" and not self.google_api_key:
            raise ValueError("Google API key not provided or found in environment variables.")

        if self.model_type == "openai":
            self.llm = ChatOpenAI(
                model="deepseek-chat",
                api_key=self.openai_api_key,
                openai_api_base='https://api.deepseek.com',
                temperature=0
            )
        elif self.model_type == "gemini":
            self.llm = ChatGoogleGenerativeAI(
                model="gemini-1.5-flash",
                google_api_key=self.google_api_key,
                temperature=0,
                convert_system_message_to_human=True
            )
        else:
            raise ValueError("Unsupported model_type. Use 'openai' or 'gemini'.")

    def generate_summary(self, documents, prompt_template="v11"):
        """Generate a summary from preprocessed documents using model-specific chains."""
        # Load prompt from dictionary
        if prompt_template not in PROMPTS:
            raise ValueError(f"Prompt template '{prompt_template}' not found. Available options: {list(PROMPTS.keys())}")
        prompt_text = PROMPTS[prompt_template]

        if self.model_type == "gemini":
            # Gemini-specific chain
            llm_prompt = PromptTemplate.from_template(prompt_text)
            doc_prompt = PromptTemplate.from_template("{page_content}")
            stuff_chain = (
                {
                    "context": lambda docs: "\n\n".join(
                        doc.page_content for doc in documents
                    )
                }
                | llm_prompt
                | self.llm
                | StrOutputParser()
            )
            result = stuff_chain.invoke(documents)
            return result

        elif self.model_type == "openai":
            # OpenAI-specific chain
            prompt = ChatPromptTemplate.from_messages([("system", prompt_text)])
            chain = create_stuff_documents_chain(self.llm, prompt)
            result = chain.invoke({"context": documents})
            return result