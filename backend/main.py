from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from pydantic import BaseModel
from typing import List

import json
from openai import OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 1. Anslut till din Docker-databas
DATABASE_URL = "postgresql://user:password@localhost:5432/studycoach"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 2. Databas-modell (Hur datan sparas i tabellen)
class UserProfile(Base):
    __tablename__ = "profiles"
    id = Column(Integer, primary_key=True, index=True)
    subject = Column(String, index=True)
    goal = Column(String)
    deadline = Column(String)

class ConceptMastery(Base):
    __tablename__ = "concept_mastery"
    id = Column(Integer, primary_key=True, index=True)
    profile_id = Column(Integer)  
    concept = Column(String)
    mastery = Column(Integer)

# Skapa tabellen automatiskt i databasen
Base.metadata.create_all(bind=engine)

# 3. Pydantic-modell (Hur datan från frontend ser ut)
class OnboardingData(BaseModel):
    subject: str
    goal: str
    deadline: str

class QuizResultItem(BaseModel):
    concept: str
    mastery: int

class QuizSubmission(BaseModel):
    profile_id: int
    results: List[QuizResultItem]

# 4. Skapa appen och tillåt trafik från Frontend (CORS)
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tillåter Next.js att anropa detta API
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Hjälpfunktion för databasen
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# 5. Din Onboarding Endpoint!
@app.post("/onboarding")
def create_onboarding(data: OnboardingData, db: Session = Depends(get_db)):
    # Skapa en ny rad i databasen
    new_profile = UserProfile(subject=data.subject, goal=data.goal, deadline=data.deadline)
    db.add(new_profile)
    db.commit()
    db.refresh(new_profile)
    return {"message": "Data sparad!", "profile": new_profile}

@app.post("/quiz-results")
def save_quiz_results(submission: QuizSubmission, db: Session = Depends(get_db)):
    for res in submission.results:
        mastery_entry = ConceptMastery(
            profile_id=submission.profile_id,
            concept=res.concept,
            mastery=res.mastery
        )
        db.add(mastery_entry)
    db.commit()
    return {"message": "Quiz-resultat sparade!"}

@app.get("/profile/{profile_id}")
def get_profile(profile_id: int, db: Session = Depends(get_db)):
    # 1. Hämta användarens grunddata (mål, deadline etc)
    user = db.query(UserProfile).filter(UserProfile.id == profile_id).first()
    if not user:
        return {"error": "Användaren hittades inte"}
        
    # 2. Hämta alla quiz-resultat (mastery) för just denna användare
    mastery = db.query(ConceptMastery).filter(ConceptMastery.profile_id == profile_id).all()
    
    # 3. Skicka tillbaka ett fint paket med all data
    return {
        "user": {
            "subject": user.subject,
            "goal": user.goal,
            "deadline": user.deadline
        },
        "mastery": [{"concept": m.concept, "score": m.mastery} for m in mastery]
    }

# 1. Uppdaterad dörrvakt för feedback (Nu tar vi emot exakta poäng!)
class FeedbackData(BaseModel):
    profile_id: int
    concept: str
    correct_count: int
    total_count: int
    difficulty: str

@app.get("/generate-quiz/{subject}")
def generate_quiz(subject: str, subtopics: str = ""):
    # 1. DENNA RAD SAKNADES! Den skapar texten om användaren fyllt i egna ämnen.
    user_topics_prompt = f"The user explicitly wants to focus on these sub-topics: {subtopics}." if subtopics else ""
    
    # 2. Nu kan vi använda variabeln i prompten utan att Python kraschar:
    prompt = f"""
    You are an expert AI tutor creating a comprehensive diagnostic quiz for '{subject}'.
    {user_topics_prompt}
    
    INSTRUCTIONS:
    1. Include the user's requested sub-topics (if any).
    2. Think of other crucial sub-topics required to master '{subject}' and add them to create a complete curriculum.
    3. You should have between 5 and 8 distinct sub-topics in total.
    4. Generate EXACTLY 2 multiple-choice questions for EACH sub-topic.
    
    Return a JSON object with EXACTLY this structure:
    {{
        "questions": [
            {{
                "text": "The question text",
                "options": ["A", "B", "C", "D"],
                "answer": "Exact correct string",
                "concept": "Name of the sub-topic"
            }}
        ]
    }}
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={ "type": "json_object" },
            messages=[{"role": "system", "content": "You output strict JSON."}, {"role": "user", "content": prompt}]
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        return {"error": str(e)}


@app.post("/feedback")
def submit_feedback(data: FeedbackData, db: Session = Depends(get_db)):
    record = db.query(ConceptMastery).filter(
        ConceptMastery.profile_id == data.profile_id,
        ConceptMastery.concept == data.concept
    ).first()

    if record:
        # Räkna ut exakta procenten
        percentage = int((data.correct_count / max(1, data.total_count)) * 100)
        record.mastery = percentage

        action = "next_level"

        if data.difficulty == "easy":
            action = "next_level"
            if percentage < 60:
                # TRICKET: Vi plussar på 1000 för att markera den som "Skippad" i databasen!
                record.mastery = percentage + 1000 
                
        elif data.difficulty == "difficult":
            action = "more_questions"
            
        else: # "okay" / neutral
            if percentage < 60:
                action = "more_questions"
            else:
                action = "next_level"
                
        db.commit()
        return {"message": "Feedback saved", "action": action}
        
    return {"error": "Hittade inte ämnet"}

@app.get("/study-plan/{profile_id}")
def get_study_plan(profile_id: int, db: Session = Depends(get_db)):
    user = db.query(UserProfile).filter(UserProfile.id == profile_id).first()
    mastery = db.query(ConceptMastery).filter(ConceptMastery.profile_id == profile_id).all()
    
    if not user or not mastery:
        return {"error": "Kunde inte hitta data"}

    plan = []
    unlocked_found = False
    
    for m in sorted(mastery, key=lambda x: x.id):
        real_mastery = m.mastery % 1000  # Ignorera vår 1000-flagga när vi visar poängen!
        is_bypassed = m.mastery >= 1000  # Kolla om flaggan finns
        
        if real_mastery >= 60:
            status = "completed"
        elif is_bypassed:
            status = "bypassed" # Ny status: Inte klar, men vi släpper förbi dem!
        elif not unlocked_found:
            status = "unlocked"
            unlocked_found = True
        else:
            status = "locked"
            
        plan.append({
            "concept": m.concept,
            "mastery": real_mastery,
            "status": status,
            "description": f"Score: {real_mastery}%"
        })

    return {"deadline": user.deadline, "plan": plan}

@app.get("/session/{profile_id}")
def get_today_session(profile_id: int, db: Session = Depends(get_db)):
    mastery = db.query(ConceptMastery).filter(ConceptMastery.profile_id == profile_id).all()
    
    # Hitta nästa ämne som varken är avklarat ELLER skippat
    focus_concept = None
    for m in sorted(mastery, key=lambda x: x.id):
        real_mastery = m.mastery % 1000
        is_bypassed = m.mastery >= 1000
        if real_mastery < 60 and not is_bypassed:
            focus_concept = m.concept
            break
            
    # Om alla är gröna eller skippade, ge dem det de har lägst "riktig" poäng i!
    if not focus_concept:
        focus_concept = sorted(mastery, key=lambda x: x.mastery % 1000)[0].concept

    # ... (resten av funktionen med prompten till AI:n behåller du precis som förut!)
    prompt = f"""
    You are an expert AI tutor teaching '{focus_concept}'.
    Return a JSON object with this exact structure:
    {{
        "concept": "{focus_concept}",
        "explanation": "A short, engaging explanation (2-3 sentences).",
        "example": "A concrete example.",
        "practice_questions": [
            {{ "text": "Q1", "options": ["A", "B", "C", "D"], "answer": "Exact answer" }},
            {{ "text": "Q2", "options": ["A", "B", "C", "D"], "answer": "Exact answer" }},
            {{ "text": "Q3", "options": ["A", "B", "C", "D"], "answer": "Exact answer" }},
            {{ "text": "Q4", "options": ["A", "B", "C", "D"], "answer": "Exact answer" }},
            {{ "text": "Q5", "options": ["A", "B", "C", "D"], "answer": "Exact answer" }}
        ]
    }}
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={ "type": "json_object" },
            messages=[{"role": "system", "content": "You output strict JSON."}, {"role": "user", "content": prompt}]
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        return {"error": str(e)}