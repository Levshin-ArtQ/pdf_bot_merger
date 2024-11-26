import os
import subprocess
import glob
import logging
import re
from collections import Counter
from os.path import basename
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, ContextTypes, \
    CallbackQueryHandler
from PyPDF2 import PdfMerger, PdfReader


# Directory to store uploaded files
UPLOAD_DIR = "./uploaded_files"
os.makedirs(UPLOAD_DIR, exist_ok=True)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Handler for the start command
async def start(update: Update, _) -> None:
    await update.message.reply_text(
        "Привет! Я могу работать с файлами PDF и Word. "
        "Просто отправь мне файлы, а я спрошу, что с ними сделать!"
    )


def resolve_file_name_conflict(output_path):
    """
    Resolve naming conflicts by appending a numeric suffix if the file already exists.
    """
    base, ext = os.path.splitext(output_path)
    counter = 1
    while os.path.exists(output_path):
        output_path = f"{base} ({counter}){ext}"
        counter += 1
    return output_path


def analyze_and_generate_filename(file_paths, upload_dir):
    """
    Analyze filenames to find common words and generate a merged filename.

    Args:
        file_paths (list of str): List of file paths to analyze.
        upload_dir (str): Directory to store the merged file.

    Returns:
        str: Generated filename for the merged PDF.
    """
    if not file_paths:
        return os.path.join(upload_dir, "merged.pdf")

    # Extract words from filenames
    words_list = []
    for file_path in file_paths:
        file_name = os.path.splitext(os.path.basename(file_path))[0]
        words = re.findall(r'\b\w+\b', file_name.lower())  # Extract words, ignoring case
        words_list.extend(words)

    # Count word occurrences across all filenames
    word_counts = Counter(words_list)
    print(words_list)

    # Filter for common words appearing in all filenames
    common_words = [
        word for word, count in word_counts.items() if count == len(file_paths)
    ]

    # Create the merged filename
    if common_words:
        common_part = "_".join(common_words[:3])  # Limit to 3 common words for brevity
        merged_filename = f"{common_part}_merged.pdf"
    else:
        merged_filename = "merged.pdf"

    # Resolve naming conflicts
    merged_file_path = os.path.join(upload_dir, merged_filename)
    merged_file_path = resolve_file_name_conflict(merged_file_path)

    return merged_file_path



# File handler
async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle file uploads from the user."""
    document = update.message.document
    file_name = document.file_name
    file_type = document.mime_type
    file_path = os.path.join(UPLOAD_DIR, basename(file_name))

    # Resolve file name conflicts
    file_path = resolve_file_name_conflict(file_path)

    # Initialize or retrieve the processing message
    if "status_message" not in context.user_data:
        context.user_data["status_message"] = await update.message.reply_text(
            "Обрабатываю ваш файл..."
        )
    else:
        pass
        # await context.user_data["status_message"].edit_text("Обрабатываю ваш файл...")

    # Retrieve the file object and download the file
    file = await document.get_file()
    await file.download_to_drive(file_path)
    previous_state = context.user_data.get("status_message", []).text


    # Validate file type
    if file_type not in [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    ]:
        await context.user_data["status_message"].edit_text(
            previous_state + f"\nФайл {file_name} не поддерживается. Принимаю только PDF и Word."
        )
        os.remove(file_path)
        return

    # Convert Word to PDF if needed
    if file_type != "application/pdf":
        try:
            pdf_path = convert_to_pdf(file_path)
            previous_state += f"\n☑️ Файл {file_name} успешно конвертирован в PDF!"
            await context.user_data["status_message"].edit_text(
                previous_state
            )
            file_path = pdf_path
        except Exception as e:
            previous_state += f"\n❌ Не удалось конвертировать файл {file_name}. Ошибка: {e}"
            await context.user_data["status_message"].edit_text(
                previous_state
            )
            logger.error(f"❌ Не удалось конвертировать файл {file_name}. Ошибка: {e}")
            os.remove(file_path)
            return

    # Add the file to the user data
    context.user_data.setdefault("files", []).append(file_path)

    # Ask user what to do next after the first file
    if len(context.user_data["files"]) == 1:
        await context.user_data["status_message"].reply_text(
            "Хотите объединить все загруженные файлы в один PDF или оставить их как есть?",
            reply_markup=ReplyKeyboardMarkup(
                [["Объединить", "Оставить"]], one_time_keyboard=True
            ),
        )
    else:
        previous_state += f"\nФайл {file_name} обработан"
        await context.user_data["status_message"].edit_text(
            previous_state
        )
        # await send_files(update, context)


# Convert Word to PDF
def convert_to_pdf(input_path: str) -> str:
    output_path = input_path.rsplit(".", 1)[0] + ".pdf"
    output_path = resolve_file_name_conflict(output_path)
    command = ["soffice", "--headless", "--convert-to", "pdf", input_path, "--outdir", UPLOAD_DIR]
    subprocess.run(command, check=True)
    return output_path


# Merge PDFs
async def merge_pdfs(update: Update, context: CallbackContext) -> None:
    files = context.user_data.get("files", [])
    if not files:
        await update.message.reply_text("Нет файлов для объединения.")
        return

    output_path = os.path.join(UPLOAD_DIR, "merged.pdf")
    output_path = analyze_and_generate_filename(output_path, UPLOAD_DIR)
    merger = PdfMerger()

    try:
        for file_path in files:
            with open(file_path, 'rb') as pdf:
                merger.append(PdfReader(pdf))
        merger.write(output_path)
        merger.close()

        # Send the merged PDF to the user
        await update.message.reply_text("Файлы успешно объединены! Высылаю")
        await update.message.reply_document(document=open(output_path, "rb"))


    except Exception as e:
        await update.message.reply_text(f"Ошибка при объединении файлов: {e}\n Предпололжительно один или несколько "
                                        f"из файлов был поврежден(ы)")
    finally:
        # Clean up
        for file_path in files:
            try:
                os.remove(file_path)
            #     TODO: remove result merge file
            except FileNotFoundError as e:
                logger.error(f'User probably sent files with similar filenames\n {e}')
        # context.user_data["files"] = []
        context.user_data.clear()


async def send_files(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    files = context.user_data.get("files", [])
    for file_path in files:
        await update.message.reply_document(
            document=open(file_path, "rb"),
            caption=f"Файл: {os.path.basename(file_path)}",
            disable_notification=True
        )
    # Cleanup files and user data
    for file in files:
        os.remove(file)
    context.user_data.clear()


# Command to cancel operation
async def cancel(update: Update, context: CallbackContext) -> None:
    await update.message.reply_text("Операция отменена. Все загруженные файлы удалены.")
    for file_path in context.user_data.get("files", []):
        os.remove(file_path)
    context.user_data["files"] = []


async def reboot(update: Update, context: CallbackContext) -> None:
    keyboard = [
        [
            InlineKeyboardButton("Да", callback_data="delete"),
            InlineKeyboardButton("Нет", callback_data="_"),
        ],
        [InlineKeyboardButton("Перечислить все файлы", callback_data="show")],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text("Хотите очистить базу файлов (все файлы будут удалены, эта операция необратима):", reply_markup=reply_markup)


async def nothing(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text('Действие отменено, можете дальше работать со своими файлами')


async def delete(update: Update, _):
    query = update.callback_query

    # CallbackQueries need to be answered, even if no notification to the user is needed
    # Some clients may have trouble otherwise. See https://core.telegram.org/bots/api#callbackquery
    await query.answer()

    # await query.edit_message_text(text=f"Selected option: {query.data}")
    files = glob.glob('./uploaded_files/*')
    await query.edit_message_text(f'removing {len(files)} files from directory...')
    for f in files:
        os.remove(f)
    await query.edit_message_text(f'files removed')


async def show(update: Update, _):
    query = update.callback_query
    await query.answer()

    # await query.edit_message_text(text=f"Selected option: {query.data}")
    files = glob.glob('./uploaded_files/*')
    await query.edit_message_text(f'sending {len(files)} files from directory...')
    for f in files:
        await query.message.reply_document(document=open(f, "rb"), disable_notification=True)


# Main function
def main() -> None:
    token = "7502939501:AAFWMFbIYpU-28PPDB0fuIvq_awztRqR2Tc"
    # updater = Updater(token)
    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CommandHandler('reboot', reboot))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_file))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex("^Объединить$"), merge_pdfs))
    application.add_handler(CallbackQueryHandler(callback=nothing, pattern="_"))
    application.add_handler(CallbackQueryHandler(callback=delete, pattern="delete"))
    application.add_handler(CallbackQueryHandler(callback=show, pattern="show"))
    application.add_handler(MessageHandler(filters.TEXT & filters.Regex("^Оставить$"), send_files))
    logger.info("Bot is running...")
    application.run_polling()


    # updater.idl


if __name__ == "__main__":
    main()
