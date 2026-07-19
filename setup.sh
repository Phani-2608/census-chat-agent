#!/bin/bash

# US Census Chat Agent - Setup Script

echo "🚀 Setting up US Census Chat Agent..."

# Check Python version
python --version
if [ $? -ne 0 ]; then
    echo "❌ Python not found. Please install Python 3.9+"
    exit 1
fi

# Create virtual environment
echo "📦 Creating virtual environment..."
python -m venv venv

# Activate virtual environment
echo "✅ Activating virtual environment..."
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

# Create .env file from example
if [ ! -f .env ]; then
    echo "📝 Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please edit .env with your Snowflake and API credentials"
else
    echo "✅ .env file already exists"
fi

# Create necessary directories
mkdir -p templates logs

# Run tests
echo "🧪 Running tests..."
python -m pytest tests/test_validators.py -v

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env with your Snowflake credentials"
echo "2. Edit .env with your Anthropic API key"
echo "3. Run: python app.py"
echo "4. Open: http://localhost:5000"
