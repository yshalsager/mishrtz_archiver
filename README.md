# mishrtz Archiver

A simple Python 3 tool to archive lectures form https://t.me/mishrtz Telegram channel.

The tool simple read the channel posts, get each lectures' group link, download lectures' files, zip them, and finally upload to a specific chat.

## Installation

```bash
# Using poetry
poetry install

# or using pip 18+
pip install .
```

## Usage

```bash
python3 archiver.py [-h] -u API_ID -p API_HASH -s START -e END [-c CHAT] [-a] [-z]

optional arguments:
  -h, --help            show this help message and exit
  -u API_ID, --api-id API_ID
                        API ID
  -p API_HASH, --api-hash API_HASH
                        API HASH
  -s START, --start START
                        Start message ID
  -e END, --end END     End message ID
  -c CHAT, --chat CHAT  Chat to send file to
  -a, --pyrogram        Use Pyrogram instead of Telethon for interacting with Telegram
  -z, --zip             Use Python zip instead of system zip
```



