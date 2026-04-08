import asyncio
import json
from app.services.llm_client import invoke_llm_json

async def main():
    try:
        res = await invoke_llm_json('You are a helpful AI', 'Say hello in JSON formatted as {"message": "Hello"}')
        print("Success:", res)
    except Exception as e:
        import traceback
        traceback.print_exc()

asyncio.run(main())
