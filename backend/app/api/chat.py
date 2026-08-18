from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.services.intelligence import IntelligenceService

router = APIRouter()

# request schema for JSON body to be sent
from pydantic import BaseModel, Field

class ChatTurn(BaseModel):
    sender: str  # "user" or "ai"
    text: str

class ChatRequest(BaseModel):
    question: str
    # prior turns, oldest first. the client owns the transcript, so the API stays
    # stateless -- no session store to expire or leak between users.
    history: list[ChatTurn] = Field(default_factory=list)

@router.post("/chat")
async def chat_with_oura(request: ChatRequest, db: Session = Depends(get_db)):
    try:
        service = IntelligenceService()
        answer = await service.answer_question(
            db,
            request.question,
            history=[turn.model_dump() for turn in request.history],
        )
        return {"answer": answer}
    except Exception as e:
        # the free Gemini tier caps daily requests; surface that as itself rather
        # than a generic 500, so the UI can say something true about what happened
        if "429" in str(e) or "quota" in str(e).lower():
            raise HTTPException(
                status_code=429,
                detail="Daily question limit reached. Try again tomorrow.",
            )
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/briefing")
async def get_briefing(db: Session = Depends(get_db)):
    try:
        service = IntelligenceService()
        return await service.get_daily_briefing(db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/metrics/summary")
def get_metrics_summary(db: Session = Depends(get_db)):
    try:
        service = IntelligenceService()
        return service.get_metric_analysis(db)
    except Exception as e:
        raise HTTPException(status_code = 500, detail=str(e))
    
@router.get("/metrics/correlations")                                                    
def get_metrics_correlations(db: Session = Depends(get_db)):                            
    try:                                                                                
        service = IntelligenceService()                                                 
        return service.get_correlations_json(db)                                        
    except Exception as e:                                                              
        raise HTTPException(status_code=500, detail=str(e))