
# Telegram Channel Forwarder

This script forwards images from a public Telegram channel to another Telegram channel using a bot.

## Requirements

- Python 3.10+
- `requests` library
- `beautifulsoup4` library
- `python-telegram-bot` library

## Installation

1. Clone the repository or download the script.
2. Install the required libraries:
   ```sh
   pip install requests beautifulsoup4 python-telegram-bot
   ```

## Configuration

1. Replace `'bot token'` with your actual bot token in the  variable.
2. Set the source channel username (without `@`) in the  variable.
3. Set the target channel username (with `@`) in the  variable.

## Usage

Run the script:

```sh
python main.py
```
