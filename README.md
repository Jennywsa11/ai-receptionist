# 🤖 AI Receptionist Chatbot

## 📌 Overview
The AI Receptionist Chatbot is a web application that scrapes a business website and answers customer questions automatically using AI.

It acts like a virtual receptionist by understanding website content and responding to user queries in real time.

---

## 🚀 Live Demo
https://ai-receptionist-production-29c1.up.railway.app/

---

## 🧠 What This Project Does
- 🌐 Scrapes content from any public website  
- 🤖 Uses AI to understand and process the content  
- 💬 Allows users to ask questions about the website  
- ⚡ Provides fast and intelligent answers  
- 📩 Can send responses via Discord webhook  

---

## 🛠️ Tech Stack
- Python (FastAPI)  
- OpenAI API  
- Supabase (Database)  
- Railway (Deployment)  
- Web scraping tools (BeautifulSoup / Requests)

---

## ⚙️ Setup Instructions

```bash
# 1. Clone the repository
git clone https://github.com/YOUR-USERNAME/ai-receptionist.git
cd ai-receptionist

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create a .env file and add your keys
OPENAI_API_KEY=your_openai_api_key
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key

### 🔧 What you must change:
Replace:
``` id="fix1"
YOUR-USERNAME

# 4. Run the application
uvicorn main:app --reload

# 5. Open in browser
http://127.0.0.1:8000
