import argparse
import asyncio
import os
import sys
from telethon import TelegramClient
from telethon.sessions import StringSession

async def main():
    parser = argparse.ArgumentParser(description="Telethon Session String Generator")
    parser.add_argument("--ipv4", action="store_true", help="Force IPv4 for MTProto connection")
    parser.add_argument("--ipv6", action="store_true", help="Force IPv6 for MTProto connection")
    args, _ = parser.parse_known_args()

    # Determine IPv6 usage: CLI flag takes precedence, then environment variable, defaulting to True
    env_ipv6 = os.getenv("TG_USE_IPV6", os.getenv("USE_IPV6", "true")).lower() not in ("0", "false", "no")
    if args.ipv4:
        use_ipv6 = False
    elif args.ipv6:
        use_ipv6 = True
    else:
        use_ipv6 = env_ipv6

    print("=== Telethon Session String Generator ===\n")
    print(f"Network Mode: IPv6 {'ENABLED (IPv6-first / IPv6-only)' if use_ipv6 else 'DISABLED (IPv4-only)'}\n")
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

    client = TelegramClient(StringSession(), api_id, api_hash_input, use_ipv6=use_ipv6)
    
    print(f"\nConnecting to Telegram MTProto gateway (use_ipv6={use_ipv6})...")
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
