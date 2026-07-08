from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.services.intelligence import IntelligenceService

router = APIRouter()

# request schema for JSON body to be sent
from pydantic import BaseModel
class ChatRequest(BaseModel):
    question: str

@router.post("/chat")
async def chat_with_oura(request: ChatRequest, db: Session = Depends(get_db)):
    try:
        service = IntelligenceService()
        answer = await service.answer_question(db, request.question)
        return {"answer": answer}
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