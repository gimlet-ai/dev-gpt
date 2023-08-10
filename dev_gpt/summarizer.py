from langchain.prompts import PromptTemplate
from langchain.chat_models import ChatOpenAI
from langchain.schema.document import Document
from langchain.chains.summarize import load_summarize_chain
from langchain.text_splitter import CharacterTextSplitter
import textwrap

class TextSummarizer:
    def __init__(self, summary_type: str):
        # Define the prompt based on the summary_type
        if summary_type == "cli":
            prompt_template = textwrap.dedent("""The following is the output of a cli command:

            <output>
            {text}
            </output>

            Please summarize it in one paragraph and highlight the errors. Skip any warnings, security
            vulnerabilities, dependencies or audit issues. For npm test output, describe the error in detail 
            and quote the exact lines of code where the error occurred. For file reads, include the relevant
            lines of code as is. Start with 'The cli command was <status>'.
            """)

        elif summary_type == "memory":
            prompt_template = textwrap.dedent("""The following is the log of steps already completed. 

            <output>
            {text}
            </output>

            Summarize each step one by one and mention it's success/failure status.  
            Skip any warnings, vulnerabilities, dependencies or audit issues. For npm test output, 
            describe the error in detail and quote the exact lines of code where the error occurred. 
            For file reads, include the relevant lines of code as is. Start with 'Step <num>: ' 
            """)

        else:
            raise ValueError("Invalid summary type")

        prompt = PromptTemplate.from_template(prompt_template)
        refine_template = textwrap.dedent("""Your job is to produce a final summary.
        We have provided an existing summary up to a certain point: {existing_answer}.
        We have the opportunity to refine the existing summary (only if needed) with some more context below.
        ------------
        {text}
        ------------
        Given the new context, refine the original summary.  If the context isn't useful, return the original summary.
        """)

        refine_prompt = PromptTemplate.from_template(refine_template)
        llm = ChatOpenAI(temperature=0, model_name="gpt-3.5-turbo-16k")
        self.llm_chain = load_summarize_chain(
            llm=llm,
            chain_type="refine",
            question_prompt=prompt,
            refine_prompt=refine_prompt,
            return_intermediate_steps=False,
            input_key="input_documents",
            output_key="output_text",
        )

    def summarize(self, text: str) -> str:
        docs = [Document(page_content=text)]
        text_splitter = CharacterTextSplitter.from_tiktoken_encoder(chunk_size=1000, chunk_overlap=0)
        split_docs = text_splitter.split_documents(docs)
        result = self.llm_chain.run({"input_documents": split_docs})
        return result