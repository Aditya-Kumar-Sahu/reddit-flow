# Reddit to YouTube AI Automation

This Python script automates the process of converting Reddit posts into AI-generated avatar videos and uploading them to YouTube. It replicates a complex n8n workflow using Python and various AI APIs.

## Features

-   **Telegram Bot Interface**: Send a Reddit link to the bot to start the process.
-   **AI Content Extraction**: Uses Google Gemini to extract content and generate an engaging script.
-   **Reddit Integration**: Fetches post content and comments (including nested replies) using PRAW.
-   **Text-to-Speech**: Uses ElevenLabs for high-quality voiceovers.
-   **Avatar Video Generation**: Uses HeyGen to create a talking avatar video.
-   **YouTube Upload**: Automatically uploads the final video to YouTube.

## Prerequisites

-   Python 3.8+
-   A Telegram Bot Token
-   Reddit API Credentials
-   Google Gemini API Key
-   ElevenLabs API Key
-   HeyGen API Key
-   YouTube Data API Credentials (OAuth 2.0 Client ID)

## Setup

1.  **Clone the repository** (or download the files).

2.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Environment Configuration**:
    -   Copy `.env.example` to `.env`:
        ```bash
        cp .env.example .env
        ```
    -   Fill in your API keys in the `.env` file.

4.  **YouTube API Setup**:
    -   Go to the [Google Cloud Console](https://console.cloud.google.com/).
    -   Create a project and enable the **YouTube Data API v3**.
    -   Go to **Credentials** -> **Create Credentials** -> **OAuth client ID**.
    -   Select **Desktop app**.
    -   Download the JSON file and rename it to `client_secrets.json`.
    -   Place `client_secrets.json` in the project root directory.

## Running the Script

1.  Start the script:
    ```bash
    python main.py
    ```

2.  **First Run (YouTube Auth)**:
    -   On the first run, a browser window will open (or a link will be printed in the console) asking you to authorize the application to upload videos to your YouTube channel.
    -   Follow the prompts to allow access.
    -   A `token.json` file will be created to store your authentication for future runs.

3.  **Using the Bot**:
    -   Open your Telegram bot.
    -   Send `/start` to verify it's running.
    -   Send a Reddit link (e.g., `https://www.reddit.com/r/technology/comments/...`).
    -   The bot will update you on the progress and send the YouTube link when finished.

## Project Structure

-   `main.py`: The core script containing all logic and service classes.
-   `requirements.txt`: List of Python dependencies.
-   `.env`: Configuration file for API keys (do not commit this to version control).
-   `client_secrets.json`: YouTube OAuth credentials.
-   `token.json`: Stored YouTube user session (generated automatically).

## Troubleshooting

-   **YouTube Upload Error**: If you see quota errors, ensure your Google Cloud project has quota available.
-   **HeyGen Error**: Check your HeyGen credits. Video generation requires credits.
-   **Reddit API**: Ensure your User Agent string in `.env` is unique to avoid rate limiting.
