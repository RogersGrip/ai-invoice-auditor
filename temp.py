from langchain_aws import ChatBedrockConverse

llm = ChatBedrockConverse(
            model="cohere.command-r-plus-v1:0",
            temperature=0.7,
            max_tokens=4096,
            region_name="us-east-1")

print(llm.invoke("Hi"))