# Reddit to YouTube AI Automation

This Python script automates the process of converting Reddit posts into AI-generated avatar videos and uploading them to YouTube. It replicates a complex n8n workflow using Python and various AI APIs.

## ✨ Features

- **Telegram Bot Interface**: Send a Reddit link to the bot to start the process
- **AI Content Extraction**: Uses Google Gemini to extract content and generate an engaging script
- **Reddit Integration**: Fetches post content and comments (including nested replies) using PRAW
- **Text-to-Speech**: Uses ElevenLabs for high-quality voiceovers
- **Avatar Video Generation**: Uses HeyGen to create a talking avatar video
- **YouTube Upload**: Automatically uploads the final video to YouTube
- **Error Handling**: Comprehensive error handling with user-friendly messages
- **Progress Tracking**: Real-time updates on processing status
- **Resource Management**: Automatic cleanup of temporary files

## 📋 Prerequisites

- **Python 3.9+**
- **Telegram Bot Token** - Get from [@BotFather](https://t.me/botfather)
- **Reddit API Credentials** - Create an app at [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) (script type)
- **Google Gemini API Key** - Get from [Google AI Studio](https://makersuite.google.com/app/apikey)
- **ElevenLabs API Key** - Sign up at [elevenlabs.io](https://elevenlabs.io)
- **HeyGen API Key** - Sign up at [heygen.com](https://heygen.com)
- **YouTube Data API Credentials** - Set up OAuth 2.0 at [Google Cloud Console](https://console.cloud.google.com/)

### 💰 Cost Estimates

Each video generation costs approximately:
- **ElevenLabs**: $0.05-0.15 per video (text-to-speech)
- **HeyGen**: $0.10-0.50 per video (avatar generation)
- **Total**: $0.15-0.65 per video

Processing time: 5-10 minutes per video

## 🚀 Setup

### 1. Clone the repository

```bash
git clone <repository-url>
cd "reddit-flow"
```

### 2. Create a virtual environment

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/Mac
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Environment Configuration

Copy `.env.example` to `.env`:

```bash
# Windows
copy .env.example .env

# Linux/Mac
cp .env.example .env
```

Edit `.env` and fill in your API keys. See `.env.example` for the required format.

### 5. YouTube API Setup

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project (or select an existing one)
3. Enable the **YouTube Data API v3**
4. Go to **Credentials** → **Create Credentials** → **OAuth client ID**
5. Select **Desktop app** as the application type
6. Download the JSON file and save it as `client_secrets.json` in the project root (or update `YOUTUBE_CLIENT_SECRETS_FILE` in `.env` to point to it)

## 📱 Usage

### Start the bot

```bash
python main.py
```

### First Run - YouTube Authorization

On the first run, a browser window will open asking you to authorize the application to upload videos to your YouTube channel:

1. Sign in to your Google account
2. Grant the requested permissions
3. The authorization will be saved in `token.json` for future runs

### Using the Bot

1. Open your Telegram bot
2. Send `/start` to see the welcome message
3. Send a Reddit link:
   ```
   https://www.reddit.com/r/technology/comments/abc123/
   ```
4. Optionally add your thoughts:
   ```
   https://www.reddit.com/r/askreddit/comments/xyz789/ This is interesting because...
   ```
5. Wait 5-10 minutes for processing
6. Receive your YouTube link!

### Available Commands

- `/start` - Show welcome message with instructions
- `/help` - Show detailed help and cost information

## 📁 Project Structure

```
reddit-to-youtube-automation/
├── main.py                      # Core application code
├── check_avatars.py             # Utility to check HeyGen avatars
├── requirements.txt             # Python dependencies
├── pyproject.toml               # Project metadata
├── .env                         # Configuration (not in git)
├── .env.example                 # Configuration template
├── .gitignore                   # Git ignore patterns
├── README.md                    # This file
├── PROGRESS.md                  # Development progress tracker
├── client_secrets.json          # YouTube OAuth credentials (not in git)
├── token.json                   # YouTube session (auto-generated, not in git)
├── avatar.json                  # Avatar data
├── idea to avatar.json          # n8n workflow reference
├── logs/                        # Application logs
├── temp/                        # Temporary files during processing
└── tests/                       # Unit tests
```

## 🔧 Configuration Options

All configuration can be set via environment variables in `.env`:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | ✅ | - | Telegram bot token |
| `REDDIT_CLIENT_ID` | ✅ | - | Reddit API client ID |
| `REDDIT_CLIENT_SECRET` | ✅ | - | Reddit API secret |
| `REDDIT_USER_AGENT` | ✅ | - | Reddit API user agent |
| `REDDIT_USERNAME` | ✅ | - | Reddit username |
| `REDDIT_PASSWORD` | ✅ | - | Reddit password |
| `GOOGLE_API_KEY` | ✅ | - | Google Gemini API key |
| `ELEVENLABS_API_KEY` | ✅ | - | ElevenLabs API key |
| `ELEVENLABS_VOICE_ID` | ✅ | - | ElevenLabs voice ID |
| `HEYGEN_API_KEY` | ✅ | - | HeyGen API key |
| `HEYGEN_AVATAR_ID` | ✅ | - | HeyGen avatar ID |
| `YOUTUBE_CLIENT_SECRETS_FILE` | ✅ | `client_secrets.json` | Path to YouTube OAuth file |
| `YOUTUBE_CATEGORY_ID` | ❌ | `28` | YouTube category (28 = Science & Technology) |
| `YOUTUBE_REGION_CODE` | ❌ | `IN` | YouTube region code |
| `MAX_COMMENTS` | ❌ | `20` | Maximum comments to include |
| `SCRIPT_MAX_WORDS` | ❌ | `200` | Maximum script length |
| `HEYGEN_WAIT_TIMEOUT` | ❌ | `1800` | Video generation timeout (seconds) |
| `HEYGEN_VIDEO_WIDTH` | ❌ | `1080` | Video width in pixels (default 9:16) |
| `HEYGEN_VIDEO_HEIGHT` | ❌ | `1920` | Video height in pixels (default 9:16) |
| `LOG_LEVEL` | ❌ | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |

## 🐛 Troubleshooting

### YouTube Upload Errors

**Error**: `Quota exceeded`
- **Solution**: YouTube API has daily quotas. Check your [quota usage](https://console.cloud.google.com/apis/api/youtube.googleapis.com/quotas)
- Each upload costs ~1600 quota units; default limit is 10,000 units/day

**Error**: `Invalid client secrets file`
- **Solution**: Download the correct OAuth 2.0 credentials from Google Cloud Console as a Desktop app

**Error**: `Token has expired`
- **Solution**: Delete `token.json` and re-authorize the application

### HeyGen Errors

**Error**: `Insufficient credits`
- **Solution**: Check your HeyGen account balance and purchase more credits

**Error**: `Video generation timeout`
- **Solution**: Increase `HEYGEN_WAIT_TIMEOUT` in `.env` or try again later

### Reddit API Errors

**Error**: `Rate limit exceeded`
- **Solution**: Reddit has rate limits. Wait a few minutes and try again
- **Solution**: Make sure your `REDDIT_USER_AGENT` is unique and descriptive

**Error**: `Post not found`
- **Solution**: Verify the Reddit link is correct and the post is not deleted/private

### ElevenLabs Errors

**Error**: `Voice not found`
- **Solution**: Check your `ELEVENLABS_VOICE_ID` is correct in `.env`
- **Solution**: Visit ElevenLabs dashboard to find available voice IDs

### General Errors

**Error**: `Configuration error: Missing required environment variables`
- **Solution**: Check all required variables in `.env` match `.env.example`

**Error**: `Operation already in progress`
- **Solution**: Only one operation per user at a time. Wait for current operation to complete

## 🔒 Security Notes

- Never commit `.env`, `token.json`, or `client_secrets.json` to version control
- Keep your API keys secure and rotate them periodically
- Use environment-specific `.env` files for different deployments
- Review the `.gitignore` file to ensure sensitive files are excluded

## 📊 Monitoring and Logs

The application uses Python's built-in logging. Set log level via `LOG_LEVEL` environment variable:

```env
LOG_LEVEL=DEBUG  # For detailed debugging
LOG_LEVEL=INFO   # For general information (default)
LOG_LEVEL=WARNING # For warnings only
LOG_LEVEL=ERROR   # For errors only
```

Logs include:
- API request/response summaries
- Processing stage timing
- Error details with stack traces
- Resource cleanup operations

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add/update tests if applicable
5. Submit a pull request

## 📄 License

MIT License - See LICENSE file for details

## 🙏 Acknowledgments

- Built on top of the n8n workflow design
- Uses Google Gemini, ElevenLabs, HeyGen, and YouTube APIs
- Python libraries: python-telegram-bot, PRAW, and more

## 📞 Support

For issues and questions:
- Open an issue on GitHub
- Check existing issues for solutions
- Review troubleshooting section above

---

**Note**: This tool uses paid API services. Monitor your usage and costs carefully. Always test with small batches before scaling up.
