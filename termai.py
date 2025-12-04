import os
import sys
import json
import requests
import subprocess
from pathlib import Path

# --- Configuration Paths ---
APP_NAME = "termai"
DATA_DIR = Path.home() / ".local/share" / APP_NAME
# We now use a JSON file for all settings
CONFIG_FILE = DATA_DIR / "config.json"
# Legacy file path for migration
OLD_KEY_FILE = DATA_DIR / "key"

# --- Colors ---
GREEN = "\033[92m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
RESET = "\033[0m"

# --- Default Settings ---
# If the config file is deleted/missing, these values are used to recreate it.
DEFAULT_CONFIG = {
    "api_key": "",
    "model_name": "gemini-2.5-flash",
    "system_instruction": (
        "You are a CLI assistant specific to Termux. "
        "Do NOT use Markdown. Do NOT use backticks. "
        "Do NOT use bolding. Just write plain text. "
        "Keep answers concise."
    ),
    "generation_config": {
        "temperature": 0.7,
        "top_p": 0.9,
        "top_k": 40,
        "maxOutputTokens": 1024
    }
}

def load_config():
    """
    Loads config.json. 
    Handles migration from old 'key' file if needed.
    Creates default file if missing.
    """
    # Ensure directory exists
    if not DATA_DIR.exists():
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Check for Config File
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"[Error] Your config file ({CONFIG_FILE}) is invalid JSON.")
            print("Please fix it or delete it to reset defaults.")
            sys.exit(1)

    # 2. Migration: If no config, check for old key file
    api_key = ""
    if OLD_KEY_FILE.exists():
        print(f"[{APP_NAME}] Migrating legacy key file to new config format...")
        with open(OLD_KEY_FILE, "r") as f:
            api_key = f.read().strip()
        # Rename old file to backup just in case
        OLD_KEY_FILE.rename(DATA_DIR / "key.bak")

    # 3. First Run Setup
    if not api_key:
        print(f"[{APP_NAME}] First run! Enter your Gemini API Key.")
        api_key = input("API Key: ").strip()
        if not api_key:
            print("Error: Key cannot be empty.")
            sys.exit(1)

    # 4. Create new Config Dictionary
    new_config = DEFAULT_CONFIG.copy()
    new_config["api_key"] = api_key
    
    # Save it
    with open(CONFIG_FILE, "w") as f:
        json.dump(new_config, f, indent=4)
    
    print(f"Configuration saved to {CONFIG_FILE}\n")
    return new_config

def open_editor():
    """Opens the config file in the default editor (nano)."""
    editor = os.getenv('EDITOR', 'nano')
    print(f"Opening config in {editor}...")
    subprocess.call([editor, str(CONFIG_FILE)])
    sys.exit(0)

def print_help():
    """Prints the help menu with available commands."""
    print(f"\n{GREEN}Termai - Termux AI Assistant{RESET}")
    print(f"A lightweight CLI tool for Gemini AI integration in Termux.\n")
    
    print(f"{YELLOW}Usage:{RESET}")
    print(f"  ai [OPTIONS] \"YOUR QUERY\"")
    print(f"  cat file.txt | ai [OPTIONS] \"OPTIONAL PROMPT\"")
    
    print(f"\n{YELLOW}Options:{RESET}")
    print(f"  {CYAN}--config{RESET}      Open configuration file (Edit API key, Model, Prompts)")
    print(f"  {CYAN}--debug{RESET}       Enable debug mode (Show raw status codes and errors)")
    print(f"  {CYAN}--help, -h{RESET}    Show this help message")
    
    print(f"\n{YELLOW}Examples:{RESET}")
    print(f"  ai \"How do I unzip a tar file?\"")
    print(f"  ai --config")
    print(f"  cat error.log | ai \"Explain this error briefly\"")
    sys.exit(0)

def main():
    # 0. Load Configuration (Variables System)
    config = load_config()

    # 1. Handle Flags
    if "--help" in sys.argv or "-h" in sys.argv:
        print_help()

    if "--config" in sys.argv:
        open_editor()

    debug_mode = "--debug" in sys.argv
    # Filter flags out of arguments so they don't get sent to the AI
    args = [arg for arg in sys.argv[1:] if arg not in ["--debug", "--config", "--help", "-h"]]

    # 2. Input Handling
    user_input = ""
    if not sys.stdin.isatty():
        # Handle Piped Input (e.g., cat file | ai)
        user_input = sys.stdin.read().strip()
        if args: user_input += "\n" + " ".join(args)
    elif args:
        # Handle Standard Arguments (e.g., ai "query")
        user_input = " ".join(args)
    else:
        # No input provided, show help
        print_help()

    # 3. Prepare Variables from Config
    api_key = config.get("api_key")
    model_name = config.get("model_name", "gemini-2.5-flash")
    system_instr = config.get("system_instruction", "")
    gen_config = config.get("generation_config", {})

    # Construct URL dynamically
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"

    # 4. Payload Construction
    payload = {
        "contents": [{"parts": [{"text": user_input}]}],
        "systemInstruction": {"parts": [{"text": system_instr}]},
        "generationConfig": gen_config
    }

    if debug_mode: print(f"[Debug] Model: {model_name} | Temp: {gen_config.get('temperature')}")

    # 5. Send Request
    try:
        response = requests.post(api_url, json=payload)
        
        if debug_mode:
            print(f"[Debug] Status: {response.status_code}")

        if response.status_code != 200:
            print(f"\n[Error {response.status_code}]")
            print(response.text)
            sys.exit(1)

        data = response.json()
        
        # Safety Check
        if "promptFeedback" in data and "blockReason" in data["promptFeedback"]:
            print(f"[Blocked] Reason: {data['promptFeedback']['blockReason']}")
            sys.exit(0)

        # Output
        if "candidates" in data:
            # Check for content existence
            cand = data["candidates"][0]
            if "content" in cand:
                # GREEN OUTPUT HERE
                print(f"{GREEN}{cand['content']['parts'][0]['text'].strip()}{RESET}")
            else:
                print("[No content returned]")
                if debug_mode: print(data)
        else:
            print("[Error] Invalid response format")
            if debug_mode: print(data)

    except Exception as e:
        print(f"\n[Connection Error] {e}")

if __name__ == "__main__":
    main()