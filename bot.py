import os
from os.path import isfile, join
import subprocess
from tarfile import ExtractError

from pyrogram import Client, filters, enums
from pyrogram.types import (ReplyKeyboardMarkup, InlineKeyboardMarkup,
                            InlineKeyboardButton)

import yt_dlp

import glob
import os
import pickle 

import sqlite3

file_ids = {}

# load from pickle (if any files exist)
if os.path.isfile('file_ids.pkl'):
    with open('file_ids.pkl', 'rb') as f:
        file_ids = pickle.load(f)

ytdlp = yt_dlp.YoutubeDL({})

# _default_clients["ANDROID_MUSIC"] = _default_clients["ANDROID_CREATOR"]

import keys

# Initialize the Telegram bot client
bot = Client("tembot",
             api_id=keys.api_id, api_hash=keys.api_hash,
             bot_token=keys.BOT_TOKEN
            )

def file_exists(filename):
    return os.path.isfile(filename)

def generate_emoji_for_captions( title, size, res_data, extension):
    if file_exists(f'downloads/{title}_{res_data}{extension}'):
        return '🚀'
    else:
        return '⚡️' if size < 50 else '⏰' if size < 150 else '⏳' if size < 300 else '🐌'

def add_button_to_keyboard(line, row, max_in_one_line, buttons, name, tag):
    buttons[line].append(InlineKeyboardButton( f"{name}", callback_data=tag))
    row += 1
    if row == max_in_one_line:
        buttons.append([])
        row = 0
        line += 1
    return buttons, row, line

def round_size_to_mb(bytes):
    if bytes == None:
        return -1
    return round(bytes / (1024 * 1024), 2)

def call_ffmpeg_async(args : list):
    with open(os.devnull, 'wb') as devnull:
        # process = subprocess.Popen('ffmpeg ' + cmd, shell=True, stdout=devnull, stderr=devnull)
        args.insert(0, 'ffmpeg')
    
        process = subprocess.Popen(args)
        return process.wait()

def get_availible_formats(info) -> list:
    # info = ytdlp.extract_info(video_url, download=False)
    formats = ytdlp._get_formats(info)
    
    usable_formats = []
    
    for f in formats:
        # if format string contains () block, add format to usable_formats
        res = f['format']
        if '(' in res and 'p' in res:
                usable_formats.append(f)

    return usable_formats
    

def generate_buttons_and_captions(video_url, info):
    max_in_one_line = 4
    row = 0
    line = 0
    
    buttons = [[]]
    vid_caption = ''
    
    res_size_pairs = {}
    
    formats = get_availible_formats(info)
    
    # actually just check for 5 basic resolutions
    
    acceptable_formats = ['144p', '240p', '360p', '480p', '720p', '1080p', '1440p', '2160p']
    
    mp3filesize = 0

    for f in formats:
        print(f"{f['format']} {f['ext']} {f['vcodec']} {f['acodec']}")
        filesize = round_size_to_mb(f['filesize'])
        if f['vcodec'] == 'none' and f['acodec'] != 'none': # basicaly mp3
            mp3filesize = max(mp3filesize, filesize)
        for frm in acceptable_formats:
            if frm in f['format']:
                if not 'mp4' in f['ext']:
                    continue
                res_size_pairs[frm] = filesize if res_size_pairs.get(frm) == None else max(res_size_pairs[frm], filesize)

    
    add_button_to_keyboard(line, row, max_in_one_line, buttons, '🎧 Mp3', 'audio' )
    vid_caption += f"`🎧 Mp3 - {mp3filesize} MB`\n"
    
    for res, size in res_size_pairs.items():
        # choose emoji based on file size
        emoji = generate_emoji_for_captions(info.get('title'), size, res, '.mp4')
        buttons, row, line = add_button_to_keyboard(line, row, max_in_one_line, buttons, emoji + f' {res}', res)
        vid_caption += f"`{emoji} {res} - {size} MB`\n"
    
    # add_button_to_keyboard( line, row, max_in_one_line, buttons, '✨ Best', 'best')
    # vid_caption += f"`✨ Best - {round_size_to_mb(best_stream.filesize)} MB ({best_stream.resolution})`\n"

    vid_caption += f"\n[Link]({video_url})"
    
    return buttons, vid_caption




@bot.on_message(filters.command("start"))
async def start_command(client, message):
    await bot.send_message(message.chat.id, "Welcome to the YouTube Downloader bot!\nSend me a YouTube video link and I'll send you the best quality available.")

# Define a handler for messages containing YouTube video links
@bot.on_message(filters.regex(r"youtube.com|youtu.be"))
async def respond_on_youtube_link(client, message):
    video_url = message.text

    info = ytdlp.extract_info(video_url, download=False)
    thumbnails = list(info.get('thumbnails') or [])
    
    # get biggest thimbnail
    # [[t.get('id'), t.get('width') or 'unknown', t.get('height') or 'unknown', t['url']] for t in thumbnails])
    
    best_thumbnail = None
    
    for t in thumbnails:
        if t.get('width') and t.get('height'):
            if not best_thumbnail:
                best_thumbnail = t
                continue
            if t.get('width') > best_thumbnail.get('width') and t.get('height') > best_thumbnail.get('height'):
                best_thumbnail = t

    if best_thumbnail:
        thumbnail_url = best_thumbnail['url']
    else:
        thumbnail_url = None

    buttons, vid_caption = generate_buttons_and_captions(video_url, info)

    await bot.send_photo(
        message.chat.id,
        photo=thumbnail_url,
        reply_markup=InlineKeyboardMarkup(buttons),
        caption=vid_caption
    )

@bot.on_callback_query()
async def handle_callback_query(client, query):
    # find link from caption_entities
    link = ''
    for i in query.message.caption_entities:
        if i.type == enums.MessageEntityType.TEXT_LINK:
            link = i.url
            break
    
    info = ytdlp.extract_info(link, download=False)
    
    frm_tag_pairs = {}
    frm_tag_pairs['audio'] = 'bestaudio'
    frm_tag_pairs['best'] = 'bestvideo+bestaudio'
    
    title = info.get('title')
    
    found = False
    frmt = ''
    
    for tag, format in frm_tag_pairs.items():
        if tag in query.data:
            frmt = format
            found = True
            break

    if not found:
        frmt = 'bv*[height<=' + query.data.replace('p', '') + ']+bestaudio/best,fps'
    
    is_audio = ('audio' in frmt) and not ('height' in frmt)
    extension = 'mp3' if is_audio else 'mp4'
    
    # how to delete potential path separators in title?
    title = title.replace('/', '_')
    title = title.replace('\\', '_')
    
    file_path = f'downloads/{title}_{query.data}_raw.%(ext)s'
    fried_path = f'downloads/{title}_{query.data}.{extension}'
    
    if file_exists(fried_path):
        fd = file_ids.get(fried_path)
        if fd:
            msg = await bot.send_cached_media(query.message.chat.id, file_id=fd)
            if msg:
                if msg.media:
                    return
    
    ydl_opts = {
        'format': frmt,
        'outtmpl': file_path
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        if ydl.download(link):
            await bot.answer_callback_query(query.id, 'Requested format is not available.')
            return
    
    # find outputed file and fetch extension from filename
    # in should be in the downloads folder
    
    list_of_files = glob.glob('downloads/*') # * means all if need specific format then *.csv
    file_path = max(list_of_files, key=os.path.getctime)
    
    if not file_exists(f'{fried_path}'):
        await bot.send_message(query.message.chat.id, f"Converting {title} with ffmpeg...")
        if is_audio:
            if call_ffmpeg_async(["-i", file_path, fried_path, "-y"]):
                await bot.answer_callback_query(query.id, 'ffmpeg failed to process the video')
                return
        else:
            if call_ffmpeg_async(["-i", file_path, "-profile:v", "high", "-level:v", "4.2", "-bf", "1", fried_path, "-y"]):
                await bot.answer_callback_query(query.id, 'ffmpeg failed to process the video')
                return
        os.remove(file_path)
    
    # get teh file size of fried file
    
    size = os.path.getsize(fried_path)
    
    await bot.send_message(query.message.chat.id, f"Converting complete!\nSending {round_size_to_mb(size)} MB...")
    
    match query.data:
        case 'audio':
            msg = await bot.send_audio(query.message.chat.id, audio=fried_path)
        case _:
            msg = await bot.send_video(query.message.chat.id, video=fried_path, width=1280, height=720)
    
    if msg is not None:
        file_id = msg.video.file_id if msg.video else msg.audio.file_id
        file_ids[fried_path] = file_id
    
    # save in pickle
    with open('file_ids.pkl', 'wb') as f:
        pickle.dump(file_ids, f)
    

# bot.add_handler()

# Start the bot
bot.run()