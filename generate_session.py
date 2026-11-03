import asyncio
import sys
from telethon import TelegramClient
from telethon.sessions import StringSession

async def main():
    print("=== Telethon Session String Generator ===\n")
    api_id_input = input("Enter your Telegram API_ID: ").strip()
    api_hash_input = input("Enter your Telegram API_HASH: ").strip()

    if not api_id_input or not api_hash_input:
        print("Error: API_ID and API_HASH are required.")
        sys.exit(1)

    try:
        api_id = int(api_id_input)
    except ValueError:
        print("Error: API_ID must be an integer.")
        sys.exit(1)

    client = TelegramClient(StringSession(), api_id, api_hash_input)
    
    print("\nConnecting to Telegram MTProto gateway...")
    await client.start()

    me = await client.get_me()
    session_string = client.session.save()

    print("\n=======================================================")
    print(f"Successfully authenticated as: {me.first_name} (@{me.username or 'No Username'}) [ID: {me.id}]")
    print("=======================================================")
    print("\nCopy the TG_SESSION_STRING below and paste it into your Render Environment Variables:\n")
    print(f"TG_SESSION_STRING={session_string}\n")
    print("=======================================================")

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
