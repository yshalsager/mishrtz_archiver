import re
from argparse import ArgumentParser
from asyncio import create_subprocess_shell
from asyncio.subprocess import Process
from pathlib import Path
from shutil import rmtree
from subprocess import run
from typing import AsyncGenerator, Union
from zipfile import ZIP_DEFLATED, ZipFile

import multivolumefile
from FastTelethonhelper import fast_download, fast_upload
from py7zr import SevenZipFile
from pyrogram import Client
from pyrogram.types import Message as PyrogramMessage
from telethon import TelegramClient
from telethon.helpers import TotalList
from telethon.tl.custom import Message as TelethonMessage

downloads_dir = Path("downloads/")
if downloads_dir.exists():
    rmtree(downloads_dir, ignore_errors=True)
uploads_dir = Path("uploads/")
if uploads_dir.exists():
    rmtree(uploads_dir, ignore_errors=True)
uploads_dir.mkdir(exist_ok=True)

ls_command = "ls -v" if run(["which", "exa"]).returncode else "exa -s name --no-icons"


def progress(current, total):
    print(f"{current * 100 / total:.1f}%")


async def archive_series(
    message: Union[TelethonMessage, PyrogramMessage],
    chat: str,
    pyrogram=False,
    use_python_zip=False,
):
    caption = f"https://t.me/{message.chat.username}/{message.message_id or message.id}\n{message.text}"
    lecture_name = (
        re.sub("#.*\n", "", re.sub("https://.*", "", message.text))
        .replace("\n", " ")
        .replace(",", "")
        .strip()[:100]
    )
    start_message_link = re.search(r"https://t.me/([\w.]+)/(\d+)", message.text)
    if not start_message_link:
        print(f"Can't find message link in {message.text}!")
        return
    messages = []
    start_id = int(start_message_link.group(2)) + 1
    while True:
        # noinspection PyTypeChecker
        if pyrogram:
            message: PyrogramMessage = await client.get_messages(
                f"@{start_message_link.group(1)}", message_ids=start_id
            )
        else:
            message: TelethonMessage = await client.get_messages(
                f"@{start_message_link.group(1)}", ids=start_id
            )
        if message:
            if (
                not message.document
                and not message.audio
                and not message.video
                and not message.voice
            ):
                break
            messages.append(message)
        start_id += 1
    if not messages:
        return
    print(f"Working on {len(messages)} files")
    for message in messages:
        if hasattr(message, "file"):
            print(f"Processing {message.file.name}")
            await fast_download(client, message, reply=None)
        else:
            print(f"Processing {getattr(message, getattr(message, 'media'))}")
            await client.download_media(message, progress=progress)
        # Path(message.file.name).write_text(message.text)
    # Zip files
    if not use_python_zip:
        process: Process = await create_subprocess_shell(
            f'cd {downloads_dir} && ls | zip "{lecture_name}.zip" -r9 -s 1990m -@ '
            f'&& mv "{lecture_name}.zip" ../{uploads_dir}/',
        )
        await process.communicate()
    else:
        if (
            sum(f.stat().st_size for f in downloads_dir.glob("**/*") if f.is_file())
            / 1024
            / 1024
            >= 1990
        ):
            with multivolumefile.open(
                f"{uploads_dir}/{lecture_name}.7z", mode="wb", volume=1990 * 1024 * 1024
            ) as target_archive:
                with SevenZipFile(target_archive, "w") as archive:
                    for file in sorted(downloads_dir.iterdir()):
                        archive.write(file, file.name)
        else:
            with ZipFile(
                f"{uploads_dir}/{lecture_name}.zip", "w", compresslevel=9
            ) as zip_file:
                for file in sorted(downloads_dir.iterdir()):
                    zip_file.write(file, file.name, compress_type=ZIP_DEFLATED)

    rmtree(downloads_dir, ignore_errors=True)
    print("Uploading...")
    for file in sorted(uploads_dir.iterdir()):
        if pyrogram:
            if (
                file.name.endswith(".mp3")
                or file.name.endswith(".m4a")
                or file.name.endswith(".wav")
            ):
                await client.send_audio(chat_id=chat, audio=str(file), caption=caption)
            elif (
                file.name.endswith(".mp4")
                or file.name.endswith(".mkv")
                or file.name.endswith(".3gp")
            ):
                await client.send_video(chat_id=chat, video=str(file), caption=caption)
            else:
                await client.send_document(
                    chat_id=chat, document=str(file), caption=caption
                )
        else:
            await client.send_file(
                chat,
                file=await fast_upload(client, str(file), str(file.name)),
                caption=caption,
            )
        file.unlink(missing_ok=True)


async def main(
    start_message_id: int,
    end_message_id: int,
    chat: str,
    pyrogram=False,
    use_python_zip=False,
):
    pattern = r"^\([\d,]+\)"
    # noinspection PyTypeChecker
    if pyrogram:
        series_list: AsyncGenerator[PyrogramMessage] = client.iter_history(
            "@mishrtz",
            offset_id=start_message_id - 1,
            limit=(end_message_id + 1) - (start_message_id - 1),
            reverse=True,
        )
        message: PyrogramMessage
        async for message in series_list:
            if re.match(pattern, message.text):
                print(f"Downloading series {message.text}")
                await archive_series(message, chat, pyrogram=pyrogram)
                print("Done")
    else:
        series_list: TotalList[TelethonMessage] = await client.get_messages(
            "@mishrtz",
            min_id=start_message_id - 1,
            max_id=end_message_id + 1,
            reverse=True,
        )
        message: TelethonMessage
        for message in series_list:
            if re.match(pattern, message.text):
                print(f"Downloading series {message.text}")
                await archive_series(
                    message, chat, pyrogram=pyrogram, use_python_zip=use_python_zip
                )
                print("Done")


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "-u",
        "--api-id",
        help="API ID",
        required=True,
        type=int,
    )
    parser.add_argument(
        "-p",
        "--api-hash",
        help="API HASH",
        required=True,
        type=str,
    )
    parser.add_argument(
        "-s",
        "--start",
        help="Start message ID",
        required=True,
        type=int,
    )
    parser.add_argument(
        "-e",
        "--end",
        help="End message ID",
        required=True,
        type=int,
    )
    parser.add_argument(
        "-c", "--chat", help="Chat to send file to", default="me", type=str
    )
    parser.add_argument(
        "-a",
        "--pyrogram",
        help="Use Pyrogram instead of Telethon for interacting with Telegram",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "-z",
        "--zip",
        help="Use Python zip instead of system zip",
        action="store_true",
        default=False,
    )
    args = parser.parse_args()

    client = (
        TelegramClient("mishrtz_telethon", api_id=args.api_id, api_hash=args.api_hash)
        if not args.pyrogram
        else Client("mishrtz_pyrogram", api_id=args.api_id, api_hash=args.api_hash)
    )
    with client:
        client.loop.run_until_complete(
            main(
                args.start,
                args.end,
                args.chat,
                pyrogram=args.pyrogram,
                use_python_zip=args.zip,
            )
        )
