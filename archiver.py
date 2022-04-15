import re
from argparse import ArgumentParser
from asyncio import create_subprocess_shell
from asyncio.subprocess import Process
from pathlib import Path
from shutil import rmtree
from subprocess import run
from typing import AsyncGenerator
from zipfile import ZIP_DEFLATED, ZipFile

import multivolumefile
from py7zr import SevenZipFile
from pyrogram import Client
from pyrogram.types import Message as PyrogramMessage
from tqdm.asyncio import tqdm

downloads_dir = Path("downloads/")
if downloads_dir.exists():
    rmtree(downloads_dir, ignore_errors=True)
downloads_dir.mkdir(exist_ok=True)
uploads_dir = Path("uploads/")
if uploads_dir.exists():
    rmtree(uploads_dir, ignore_errors=True)
uploads_dir.mkdir(exist_ok=True)

ls_command = "ls -v" if run(["which", "exa"]).returncode else "exa -s name --no-icons"


def progress(current, total, progress_bar):
    progress_bar.update(current - progress_bar.n)
    if current == total:
        progress_bar.set_description(
            f"Done! {progress_bar.desc.split(' ', maxsplit=1)[-1]}"
        )


async def archive_series(
    message: PyrogramMessage,
    chat: str,
    use_python_zip: bool = False,
):
    caption = (
        f"https://t.me/{message.chat.username}/{message.message_id}\n{message.text}"
    )
    lecture_name = (
        re.sub("#.*\n", "", re.sub("https://.*", "", message.text))
        .replace("\n", " ")
        .replace(",", "")
        .replace('"', "")
        .replace("'", "")
        .strip()[:100]
    )
    start_message_link = re.search(r"https://t.me/([\w.]+)/(\d+)", message.text)
    if not start_message_link:
        print(f"Can't find message link in {message.text}!")
        return
    messages = []
    first_message: PyrogramMessage = await client.get_messages(
        f"@{start_message_link.group(1)}", message_ids=int(start_message_link.group(2))
    )
    start_id = (
        int(start_message_link.group(2)) + 1
        if first_message.media not in ("audio", "document", "video", "voice")
        else int(start_message_link.group(2))
    )
    while True:
        message: PyrogramMessage = await client.get_messages(
            f"@{start_message_link.group(1)}", message_ids=start_id
        )
        if not message.empty:
            if message.media not in ("audio", "document", "video", "voice"):
                break
            messages.append(message)
        start_id += 1
    if not messages:
        return
    print(f"Working on {len(messages)} files")
    previous_message_filename = ""
    for idx, message in enumerate(messages):
        file = getattr(message, getattr(message, "media"))
        file_name = getattr(
            file,
            "file_name",
            f"{idx:0>3}.{file.mime_type.split('/')[-1].split('-')[-1]}",
        )
        progress_bar = tqdm(
            total=file.file_size,
            unit="iB",
            unit_scale=True,
            desc=f"Downloading {file_name}...",
            unit_divisor=1024,
            miniters=1,
        )
        file_name = (
            f"{downloads_dir}/{idx}_{file_name}"
            if previous_message_filename and previous_message_filename == file_name
            else ""
        )
        previous_message_filename = file_name
        await client.download_media(
            message,
            progress=progress,
            progress_args=(progress_bar,),
            file_name=file_name,
        )
        # (
        #     downloads_dir / getattr(message, getattr(message, "media")).file_name
        # ).write_text(caption)
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
        progress_bar = tqdm(
            total=file.stat().st_size,
            unit="iB",
            unit_scale=True,
            desc=f"Uploading {file.name}...",
            unit_divisor=1024,
            miniters=1,
        )
        if file.suffix in [
            ".mp3",
            ".m4a",
            ".wav",
            ".ogg",
            ".flac",
            ".aac",
            ".wma",
            ".amr",
            ".opus",
            ".ra",
            ".rm",
            ".m4b",
            ".aif",
            ".dts",
            ".mpeg",
        ]:
            await client.send_audio(
                chat_id=chat,
                audio=str(file),
                caption=caption,
                progress=progress,
                progress_args=(progress_bar,),
            )
        elif file.suffix in [
            ".mp4",
            ".mkv",
            ".3gp",
            ".webm",
            ".flv",
            ".avi",
            ".wmv",
            ".m4v",
            ".mpeg",
            ".mov",
        ]:
            await client.send_video(
                chat_id=chat,
                video=str(file),
                caption=caption,
                progress=progress,
                progress_args=(progress_bar,),
            )
        else:
            await client.send_document(
                chat_id=chat,
                document=str(file),
                caption=caption,
                progress=progress,
                progress_args=(progress_bar,),
            )
        file.unlink(missing_ok=True)


async def main(
    start_message_id: int,
    end_message_id: int,
    chat: str,
    use_python_zip=False,
):
    pattern = r"^\([\d,]+\)"
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
            await archive_series(message, chat, use_python_zip=use_python_zip)
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
        "-z",
        "--zip",
        help="Use Python zip instead of system zip",
        action="store_true",
        default=False,
    )
    args = parser.parse_args()

    client = Client("mishrtz_pyrogram", api_id=args.api_id, api_hash=args.api_hash)
    with client:
        client.loop.run_until_complete(
            main(
                args.start,
                args.end,
                args.chat,
                use_python_zip=args.zip,
            )
        )
