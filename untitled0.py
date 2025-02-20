# -*- coding: utf-8 -*-
"""Untitled0.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/12LL-Rpn-73ALPGW4RmzywSgCcTwm_Cqv
"""

# -*- coding: utf-8 -*-

"""neiro1680_experiment.ipynb"""

# Установка необходимых библиотек
!pip install python-telegram-bot transformers librosa soundfile pydub nltk pymorphy2 natasha noisereduce
!pip install -U huggingface_hub
!pip install faster-whisper
!pip install vosk
!pip install ffmpeg

import nest_asyncio
nest_asyncio.apply()

from huggingface_hub import notebook_login

notebook_login()

import nltk
nltk.download('punkt_tab')

!pip install nest_asyncio
!pip install vosk sounddevice

from google.colab import drive
drive.mount('/content/drive')
!cp "/content/drive/MyDrive/vosk-model-ru-0.10.zip" "/content/"
!unzip /content/vosk-model-ru-0.10.zip -d /content/vosk
!cp -r /content/vosk/ "/content/drive/My Drive/"

import os
import soundfile as sf
import torch
import librosa
import nltk
from nltk.tokenize import sent_tokenize
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
import logging
import asyncio
import subprocess
from vosk import Model, KaldiRecognizer
import io
import traceback  # Import traceback
from telegram.constants import ParseMode

# 1. Telegram Bot Token (замените на свой токен!)
TELEGRAM_TOKEN = "7733509719:AAFVwYEU9rUeYpw88QaMpLtLetAHs8VGk_M" # Теперь твой токен

# 2. Устройство для вычислений (CPU)
device = torch.device("cpu")
print(f"Используется устройство: {device}")

# 3. Настройка NLTK (загрузка данных)
NLTK_DATA_PATH = os.path.join(os.getcwd(), "nltk_data")
if not os.path.exists(NLTK_DATA_PATH):
    os.makedirs(NLTK_DATA_PATH)
nltk.data.path.append(NLTK_DATA_PATH)

try:
    nltk.download('punkt', download_dir=NLTK_DATA_PATH)
    print("Данные NLTK успешно загружены.")
except Exception as e:
    print(f"Ошибка при загрузке данных NLTK: {e}")

# Инициализация модели Vosk
vosk_model_path = "/content/vosk/vosk-model-ru-0.10"

try:
    vosk_model = Model(vosk_model_path)
    print("Модель Vosk успешно загружена.")
except Exception as e:
    print(f"Ошибка при загрузке модели Vosk: {e}")
    vosk_model = None  # Set to None if loading fails

# Вспомогательные функции для обработки аудио
async def convert_to_wav(input_file: str) -> str | None:
    """Converts audio file to WAV format using ffmpeg."""
    output_file = "output.wav"
    try:
        command = f"ffmpeg -i {input_file} -acodec pcm_s16le -ar 16000 -ac 1 -y {output_file}"
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            logging.error(f"FFmpeg error: {stderr.decode()}")
            return None
        return output_file
    except Exception as e:
        logging.error(f"Error during audio conversion: {e}")
        return None

def create_progress_bar(progress: float) -> str:
    """Creates a text-based progress bar."""
    bar_length = 20
    filled_length = int(bar_length * progress)
    bar = '█' * filled_length + '-' * (bar_length - filled_length)
    return f"[{bar}] {int(progress * 100)}%"

async def transcribe_audio(audio_path: str, update: Update, context: CallbackContext) -> str | None:
    """Transcribes audio file to text using Vosk API with progress updates."""
    global vosk_model
    if vosk_model is None:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Модель распознавания Vosk не загружена.")
        return None

    try:
        model_path = "/content/vosk/vosk-model-ru-0.10"  # Укажите путь к вашей модели
        model = Model(model_path)

        try:
            wf = sf.SoundFile(audio_path)
        except sf.LibsndfileError as e:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"SoundFile error: {e}")
            return None
        except Exception as e:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"General error opening audio: {e}")
            return None

        rec = KaldiRecognizer(model, wf.samplerate)
        num_frames = len(wf)

        transcription = ""

        # Function to send progress updates
        async def send_progress_update(frame_num: int):
            progress = frame_num / num_frames
            progress_bar = create_progress_bar(progress)
            try:
                await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=progress_message.message_id,
                    text=f"Распознавание речи... {progress_bar}",
                    parse_mode=ParseMode.MARKDOWN  # Use markdown to send the updates
                )
            except Exception as e:
                logging.warning(f"Error editing message: {e}")

        # Send initial progress message
        progress_message = await context.bot.send_message(chat_id=update.effective_chat.id, text="Начинаю распознавание речи...\n[----------] 0%")

        frame_count = 0
        while True:
            data = wf.read(4000)  # Read data in 4000 frame chunks
            frame_count += 4000
            if len(data) == 0:
                break

            if rec.AcceptWaveform(data.tobytes()):
                result = rec.Result()
                try:
                    import json
                    data = json.loads(result)
                    transcription += data.get("text", "") + " "
                except json.JSONDecodeError:
                    transcription += result + " "

            if frame_count % 20000 == 0:  # Update progress every 20000 frames
                await send_progress_update(frame_count)

        final_result = rec.FinalResult()
        try:
            import json
            data = json.loads(final_result)
            transcription += data.get("text", "")
        except json.JSONDecodeError:
            transcription += final_result

        final_transcription = transcription.strip()

        try:
            await context.bot.edit_message_text(
                    chat_id=update.effective_chat.id,
                    message_id=progress_message.message_id,
                    text=f"Распознавание завершено!\n\nТранскрипция:\n{final_transcription}",
                    parse_mode=ParseMode.MARKDOWN  # Use markdown to send the updates
                )
        except Exception as e:
            logging.warning(f"Error editing message: {e}")


        return final_transcription

    except Exception as e:
        print(f"Ошибка при распознавании речи: {e}")
        traceback.print_exc()  # Print the traceback
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"Ошибка при распознавании речи: {e}")
        return None

def split_text_by_sentences(text, max_message_length=4096):
    sentences = sent_tokenize(text)
    messages = []
    current_message = ""

    for sentence in sentences:
        if len(current_message) + len(sentence) + 1 <= max_message_length:
            current_message += sentence + " "
        else:
            messages.append(current_message.strip())
            current_message = sentence + " "

    if current_message:
        messages.append(current_message.strip())

    return messages

# Telegram Bot Handlers
async def start(update: Update, context: CallbackContext):
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                    text="Привет! Отправьте мне аудиофайл, и я попробую его расшифровать.")

async def audio_message_handler(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id

    if update.message and update.message.audio:
        audio_file = update.message.audio

        try:
            file_id = audio_file.file_id

            new_file = await context.bot.get_file(file_id)
            file_path = new_file.file_path

            audio_filename = "audio.ogg"
            ogg_file = await new_file.download_as_bytearray()

            with open(audio_filename, 'wb') as f:
                f.write(bytes(ogg_file))

            await context.bot.send_message(chat_id=chat_id, text="Аудио получено! Начинаю обработку...")

            wav_filename = await convert_to_wav(audio_filename)

            if not wav_filename:
                await context.bot.send_message(chat_id=chat_id,
                                                text="Ошибка при преобразовании аудио.")
                return

            transcription = await transcribe_audio(wav_filename, update, context)

            if transcription:
               # transcription is already sent in transcribe_audio
               pass
            else:
                await context.bot.send_message(chat_id=chat_id,
                                                 text="Не удалось выполнить транскрипцию.")

            try:
                os.remove(audio_filename)
                os.remove(wav_filename)
            except Exception as e:
                logging.warning(f"Не удалось удалить временные файлы: {e}")

        except Exception as e:
            logging.error(f"Ошибка при обработке аудио: {e}")
            traceback.print_exc()  # Print the traceback
            await context.bot.send_message(chat_id=chat_id,
                                             text=f"Произошла ошибка при обработке аудио: {e}")

    else:
        await context.bot.send_message(chat_id=chat_id,
                                         text="Пожалуйста, отправьте аудиофайл.")

async def main() -> None:
    try:
        application = Application.builder().token(TELEGRAM_TOKEN).build()

        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(filters.AUDIO, audio_message_handler))

        # Run the bot until the user presses Ctrl-C
        await application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        print(f"Бот остановлен из-за ошибки: {e}")
        traceback.print_exc()

# Proper startup
if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                        level=logging.INFO)
    try:
        asyncio.run(main())
    except RuntimeError as e:
        if "This event loop is already running" in str(e):
            print("Event loop is already running. Attempting to run main() as a task.")
            loop = asyncio.get_event_loop()
            loop.create_task(main()) # Schedule main to be run on the existing loop
        else:
            print(f"An error occurred: {e}")
            traceback.print_exc()