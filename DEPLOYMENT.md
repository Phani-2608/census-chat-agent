# Deployment Guide - US Census Chat Agent

## Quick Start for Evaluation

### Local Development

1. **Clone the repository** (if using GitHub)
   ```bash
   git clone <repository-url>
   cd census-chat-agent
   ```

2. **Run setup script**
   ```bash
   chmod +x setup.sh
   ./setup.sh
   ```

3. **Configure credentials**
   - Edit `.env` file with your Snowflake account details
   - Add your Anthropic API key
   ```env
   SNOWFLAKE_USER=your_username
   SNOWFLAKE_PASSWORD=your_password
   SNOWFLAKE_ACCOUNT=xy12345
   ANTHROPIC_API_KEY=sk-ant-...
   ```

4. **Start the application**
   ```bash
   python app.py
   ```

5. **Access the application**
   - Open browser to `http://localhost:5000`
   - Start asking questions about US Census data

### Manual Setup (If Setup Script Fails)

1. **Create and activate virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Copy environment template**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

4. **Run tests to verify setup**
   ```bash
   python -m pytest tests/test_validators.py -v
   ```

5. **Start application**
   ```bash
   python app.py
   ```

## Deployment to Cloud Platforms

### Option 1: Heroku

1. **Install Heroku CLI**
   ```bash
   # macOS
   brew tap heroku/brew && brew install heroku
   
   # Windows
   choco install heroku-cli
   ```

2. **Create Heroku app**
   ```bash
   heroku create your-app-name
   ```

3. **Set environment variables**
   ```bash
   heroku config:set SNOWFLAKE_USER=your_username
   heroku config:set SNOWFLAKE_PASSWORD=your_password
   heroku config:set SNOWFLAKE_ACCOUNT=your_account
   heroku config:set ANTHROPIC_API_KEY=sk-ant-...
   heroku config:set FLASK_SECRET_KEY=$(python -c 'import os; print(os.urandom(16).hex())')
   ```

4. **Add Procfile** (create file named `Procfile` in root)
   ```
   web: gunicorn -w 4 -b 0.0.0.0:$PORT app:app
   ```

5. **Deploy**
   ```bash
   git push heroku main
   ```

6. **Access application**
   ```bash
   heroku open
   ```

### Option 2: Railway

1. **Connect GitHub repository to Railway**
   - Go to railway.app
   - Create new project
   - Connect GitHub repository

2. **Set environment variables in Railway dashboard**
   - SNOWFLAKE_USER
   - SNOWFLAKE_PASSWORD
   - SNOWFLAKE_ACCOUNT
   - ANTHROPIC_API_KEY
   - FLASK_SECRET_KEY

3. **Railway automatically detects Python and deploys**

4. **Access via Railway-provided domain**

### Option 3: Google Cloud Run

1. **Create Dockerfile** (in root directory)
   ```dockerfile
   FROM python:3.9-slim
   
   WORKDIR /app
   
   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt
   
   COPY . .
   
   ENV PORT=8080
   CMD exec gunicorn --bind :$PORT --workers 4 app:app
   ```

2. **Build and push to Google Container Registry**
   ```bash
   gcloud builds submit --tag gcr.io/PROJECT-ID/census-chat-agent
   ```

3. **Deploy to Cloud Run**
   ```bash
   gcloud run deploy census-chat-agent \
     --image gcr.io/PROJECT-ID/census-chat-agent \
     --platform managed \
     --region us-central1 \
     --set-env-vars SNOWFLAKE_USER=...,SNOWFLAKE_PASSWORD=...,etc.
   ```

### Option 4: AWS Lambda with Zappa

1. **Install Zappa**
   ```bash
   pip install zappa
   ```

2. **Create Zappa settings file** (`zappa_settings.json`)
   ```json
   {
     "dev": {
       "app_function": "app.app",
       "aws_region": "us-east-1",
       "runtime": "python3.9",
       "environment_variables": {
         "SNOWFLAKE_USER": "your_username",
         "SNOWFLAKE_ACCOUNT": "your_account"
       }
     }
   }
   ```

3. **Deploy**
   ```bash
   zappa deploy dev
   ```

## Prerequisites for Cloud Deployment

### Snowflake Setup

1. **Create Snowflake trial account** (if needed)
   - Visit www.snowflake.com/free-trial/
   - Create account in your preferred region

2. **Get Census Data**
   - Log into Snowflake
   - Go to Marketplace
   - Search for "SafeGraph Open Census"
   - Add to your account (free)

3. **Note your account details**
   - Account ID: `xy12345.us-east-1` (visible in UI)
   - Username: Your login email
   - Password: Your password

### Anthropic API Key

1. **Visit api.anthropic.com**
2. **Sign up or log in**
3. **Create API key** in account settings
4. **Copy key** (format: `sk-ant-...`)

## Testing Deployment

After deployment, verify the application works:

1. **Test health check**
   ```bash
   curl https://your-app-url.com/health
   ```
   Expected response:
   ```json
   {"status": "healthy", "timestamp": "2024-01-15T10:30:00"}
   ```

2. **Test chat endpoint**
   ```bash
   curl -X POST https://your-app-url.com/api/chat \
     -H "Content-Type: application/json" \
     -d '{"message": "What is the population of California?"}'
   ```
   Expected response:
   ```json
   {
     "response": "California has a population of approximately...",
     "query_executed": true,
     "is_off_topic": false,
     "conversation_turn": 1
   }
   ```

3. **Test reset endpoint**
   ```bash
   curl -X POST https://your-app-url.com/api/reset
   ```

## Monitoring & Debugging

### View Logs

**Local:**
```bash
# Flask development server shows logs in terminal
python app.py
```

**Heroku:**
```bash
heroku logs -t  # Tail logs in real-time
```

**Cloud Run:**
```bash
gcloud run logs read census-chat-agent --limit=100
```

### Common Issues

#### Issue: "Missing Snowflake credentials"
**Solution:**
- Verify .env file exists in root directory
- Check all required fields are populated
- Ensure no trailing spaces in credentials

#### Issue: "ANTHROPIC_API_KEY not found"
**Solution:**
- Verify API key is set in environment
- On cloud platforms, check secrets/config tab
- API key format should start with `sk-ant-`

#### Issue: "Connection refused to Snowflake"
**Solution:**
- Verify Snowflake account ID is correct
- Check username and password
- Ensure Snowflake account is active (trial not expired)
- Verify IP whitelisting (if applicable)

#### Issue: Response takes >60 seconds
**Solution:**
- This is a known limitation for complex queries
- Try simpler questions first
- Check Snowflake warehouse size (may need to scale up)
- Consider query caching for frequently asked questions

#### Issue: Blank page or "Cannot GET /"
**Solution:**
- Verify Flask app started successfully
- Check PORT environment variable (defaults to 5000)
- Try accessing /health endpoint
- Check application logs for errors

## Performance Tuning

### Snowflake Optimization

1. **Increase warehouse size** (for faster query execution)
   ```sql
   ALTER WAREHOUSE COMPUTE_WH SET WAREHOUSE_SIZE = 'LARGE';
   ```

2. **Create indexes** on frequently searched columns
   ```sql
   CREATE INDEX idx_state ON CENSUS_DATA.PUBLIC.DEMOGRAPHICS(state);
   CREATE INDEX idx_county ON CENSUS_DATA.PUBLIC.DEMOGRAPHICS(county);
   ```

3. **Enable caching**
   ```sql
   ALTER SYSTEM SET QUERY_RESULT_CACHE_TTL = 3600;
   ```

### Application Optimization

1. **Enable response caching**
   - Modify `chat_service.py` to cache similar queries
   - Suggested: Use Redis for distributed caching

2. **Optimize LLM calls**
   - Reduce prompt size
   - Use smaller models for simple queries
   - Batch multiple queries if possible

3. **Database connection pooling**
   - Modify `database.py` to use connection pool
   - Recommended: SQLAlchemy with pooling

## Security Considerations

### Before Production Deployment

1. **Rotate API Keys**
   - Never commit real API keys to git
   - Use environment variables
   - Rotate keys regularly

2. **Enable HTTPS**
   - Cloud platforms provide free HTTPS
   - Heroku: Automatic
   - Cloud Run: Automatic
   - Railway: Automatic

3. **Add authentication** (if needed)
   - Consider adding username/password for access
   - Or restrict to internal network only

4. **Enable CORS properly**
   - Current: `CORS(app)` allows all origins
   - For production: Specify allowed origins
   ```python
   CORS(app, origins=['https://yourdomain.com'])
   ```

5. **Add rate limiting**
   - Prevent abuse and API cost explosion
   ```bash
   pip install Flask-Limiter
   ```

6. **Enable logging & monitoring**
   - Track API usage
   - Alert on errors
   - Monitor performance

## Maintenance & Updates

### Regular Tasks

1. **Check logs weekly** for errors and performance issues
2. **Monitor API usage** and costs
3. **Update dependencies monthly**
   ```bash
   pip list --outdated
   pip install --upgrade <package>
   ```
4. **Rotate secrets** every 90 days
5. **Test disaster recovery** (backup/restore procedures)

### Scaling Strategy

**Current capacity:** Handles ~10-20 concurrent users (single dyno/instance)

**For 100+ concurrent users:**
1. Upgrade to multiple dynos/instances
2. Implement Redis for session storage
3. Add database connection pooling
4. Consider caching layer (CloudFlare, CDN)
5. Implement query result caching

## Accessing Running Demo

### For Evaluation Team

The application will be deployed to: `[URL will be provided]`

**Credentials:** None required (public access)

**How to test:**
1. Open the URL in browser
2. Ask questions like:
   - "What is the population of California?"
   - "Show me the demographic breakdown of New York"
   - "How many people live in Texas?"
3. Use "New Conversation" button to reset chat
4. Check browser console (F12) for any error messages

### Accessing Logs

Logs are available via:
- **Local:** Terminal where `python app.py` is running
- **Cloud:** Cloud provider's log viewer
- **Health check:** `/health` endpoint returns system status

## Support & Troubleshooting

For issues or questions:
1. Check DEPLOYMENT.md (this file)
2. Review application README.md
3. Check REFLECTION.md for known limitations
4. Examine logs for specific error messages
5. Test endpoints manually with curl/Postman
