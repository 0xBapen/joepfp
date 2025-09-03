import os
import logging
from telegram import Update, MessageEntity
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
import requests
from PIL import Image
import openai
from io import BytesIO
import base64

# Set up logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

openai.api_key = OPENAI_API_KEY
REFERENCE_IMAGE_PATH = "joe_reference.png"
OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Initialize OpenAI client
client = openai.OpenAI(api_key=OPENAI_API_KEY)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a welcome message when the /start command is issued."""
    await context.bot.send_message(chat_id=update.effective_chat.id,
        text="Welcome! In a private chat, just send a photo. In a group, send a photo and tag me in the caption to get it Joe-fied!"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle messages, checking for photos with captions or replies to photos with mentions."""
    message = update.message
    chat_id = message.chat_id
    photo_to_process = None

    bot_username = (await context.bot.get_me()).username

    # Case 2: Reply to a photo with bot tagged in the reply message
    if message.reply_to_message and message.reply_to_message.photo and message.text and message.entities:
        is_mentioned = any(
            entity.type == MessageEntity.MENTION and message.text[entity.offset:entity.offset + entity.length] == f"@{bot_username}"
            for entity in message.entities
        )
        if is_mentioned:
            photo_to_process = message.reply_to_message.photo[-1]
            logger.info("Processing photo: reply to photo with bot mention.")

    # Case 3: Private chat - process any photo
    elif message.chat.type == "private" and message.photo:
        photo_to_process = message.photo[-1]
        logger.info("Processing photo: private chat.")

    if not photo_to_process:
        logger.info("Ignoring message: no relevant photo or mention found.")
        return

    await context.bot.send_message(chat_id=chat_id, text="Downloading your photo...")

    # Download the user\'s photo
    file = await context.bot.get_file(photo_to_process.file_id)
    photo_bytes = await file.download_as_bytearray()
    user_photo = Image.open(BytesIO(photo_bytes))
    user_photo_path = os.path.join(OUTPUT_DIR, f"user_{chat_id}_{photo_to_process.file_id}.png")
    user_photo.save(user_photo_path)

    await context.bot.send_message(chat_id=chat_id, text="Performing face swap with Joe\'s face...")

    try:
        # Ensure joe_reference.png exists
        if not os.path.exists(REFERENCE_IMAGE_PATH):
            await context.bot.send_message(chat_id=chat_id,
                text=f"Error: Reference image \'{REFERENCE_IMAGE_PATH}\' not found. Please ensure it\'s in the same directory as the bot script."
            )
            return

        # Prepare images for GPT-image-1
        with open(REFERENCE_IMAGE_PATH, "rb") as joe_ref_file:
            with open(user_photo_path, "rb") as user_img_file:
                prompt = """
                Modify the second image to have the face of the person in the first image. 
                Maintain the original pose, lighting, and background of the second image, 
                only changing the face and adding a must have circular goatee instead of a full beard to match the first image . Ensure a second image style with the face of the first image.
                """

                result = client.images.edit(
                    model="gpt-image-1",
                    image=[
                        joe_ref_file,
                        user_img_file,
                    ],
                    prompt=prompt,
                # You can specify size, quality, and response_format if needed
                # size="1024x1024",
                # quality="standard",
                # response_format="b64_json",
            )

                image_base64 = result.data[0].b64_json
                image_bytes = base64.b64decode(image_base64)

        # Save the result
        output_image_path = os.path.join(OUTPUT_DIR, f"joefied_{chat_id}_{photo_to_process.file_id}.png")
        with open(output_image_path, "wb") as f:
            f.write(image_bytes)

        await context.bot.send_photo(chat_id=chat_id, photo=open(output_image_path, "rb"))
        await context.bot.send_message(chat_id=chat_id, text="Here\'s your Joe-fied image!")

    except openai.APIError as e:
        logger.error(f"OpenAI API Error: {e}")
        await context.bot.send_message(chat_id=chat_id, text=f"Uh oh, Joe\'s being a bit too spicy! Joe PFP Bot keeps it chill and won\'t Joe\'fy NSFW content.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        await context.bot.send_message(chat_id=chat_id, text=f"wait a few seconds to get Joefied!")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors."""
    logger.error(f"Update {update} caused error {context.error}")
    if update and update.effective_chat:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="An error occurred. Please try again.")

def main():
    """Run the bot."""
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    # Use a general message handler to check for photos or replies to photos
    application.add_handler(MessageHandler(filters.PHOTO | filters.REPLY, handle_message))
    application.add_error_handler(error_handler)

    # Start the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
if __name__ == "__main__":
    main()

