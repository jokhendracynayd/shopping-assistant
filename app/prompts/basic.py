from langchain_core.prompts import ChatPromptTemplate
INTENTS = [
    "FAQ",
    # "Product_Inquiry",
    # "Order_Status",
    # "Complaint",
    # "General_Query",
    "Other"
]

intent_classification_prompt = ChatPromptTemplate.from_messages([
    (
        "system",
        f"""You are an intent classification system.  
Your task is to analyze the user query and classify it into **one** of the predefined intents.  

Possible intents: {INTENTS}  

Guidelines:
- Always pick exactly **one** intent.  
- If unsure, choose "Other".  
- Do not explain your reasoning.  
- Output strictly in valid JSON format.  

Format:
{{{{  
  "intent": "<one of the intents>"  
}}}}
"""
    ),
    ("human", "{input}")
])

rag_prompt = ChatPromptTemplate.from_messages([
    ("system",
     "You are a concise and helpful assistant for product FAQs. "
     "Use the provided context documents to answer the question. "
     "If the context does not contain the answer, say "
     "'I can only answer product-related questions based on available information.' "
     "Keep answers short and clear."),
    ("human",
     "Question: {question}\n\n"
     "Context:\n{context}\n\n"
     "Answer:")
])