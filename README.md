# Study Coach
AI driven study coach with an agentic workflow that leads the student through their 
subjects. This is a simple version but still showcases the potential.

## Tech Stack
* **Frontend:** Next.js (App Router), React, Tailwind CSS
* **Backend:** Python, FastAPI, SQLAlchemy
* **Database:** PostgreSQL
* **AI:** OpenAI API (gpt-4o-mini)

## How to run locally

### Prerequisites
1. Node.js installed.
2. Python 3 installed.
3. PostgreSQL installed and running (with a database named `studycoach`).
4. An OpenAI API key.

### 1. Backend Setup
Navigate to the backend directory and set up the Python environment:
```bash
cd backend
python -m venv venv
source venv/Scripts/activate  # On Windows: .\venv\Scripts\Activate.ps1
pip install -r requirements.txt