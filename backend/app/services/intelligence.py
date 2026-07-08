import google.generativeai as genai
from sqlalchemy.orm import Session
from app.core.config import settings
from sqlalchemy import select
from app.models.metric import DailyMetric
from datetime import date, timedelta
import statistics

class IntelligenceService:
    def __init__(self):
        genai.configure(api_key=settings.GOOGLE_API_KEY)
        self.model = genai.GenerativeModel('gemini-2.5-flash')

    async def answer_question(self, db: Session, question: str):
        raw_context = self.get_recent_metrics_summary(db, days=60)
        stats_context = self.get_statistical_insights(db, days=60)
        correlation_context = self.get_correlation_insights(db, days=60) 

        today_str = date.today().isoformat()

        prompt = f"""
        You are a Health Intelligence Assistant.
        Today is {today_str}.
        You are looking at the user's Oura Ring data for the last 60 days.

        DATA:
        {raw_context}

        STATISTICAL INSIGHTS (Relative to user's history):
        {stats_context}

        PHYSIOLOGICAL CORRELATIONS (Identified trends):                                 
        {correlation_context}

        USER QUESTION:
        {question}

        INSTRUCTIONS:
         - Use the provided DATA and STATISTICAL INSIGHTS to explain scores.
         - If the data is missing or insufficient, say so.
         - A Z-score (σ) above +1.5 or below -1.5 is significant.
         - Be concise and grounded in the numbers (mention specific scores).
         - IMPORTANT: Do not give medical advice. You are a data interpreter.
        """

        response = self.model.generate_content(prompt)
        return response.text
    
    def _calculate_metrics_stats(self, db: Session, days: int = 60):
        start_date = date.today() - timedelta(days=days)

        # query data for windo
        query = select(DailyMetric).where(DailyMetric.day >= start_date)
        result = db.execute(query)
        metrics = result.scalars().all()

        if not metrics:
            return []
        
        # group by metric type
        grouped = {}
        for m in metrics:
            if m.metric not in grouped:
                grouped[m.metric] = []
            grouped[m.metric].append(m)
        
        stats = []
        for metric_name, data_points in grouped.items():
            values = [p.value for p in data_points]

            if len(values) < 2:
                continue

            mean_val = statistics.mean(values)
            stdev_val = statistics.stdev(values) or 0.1

            sorted_points = sorted(data_points, key=lambda x: x.day, reverse=True)      
            latest_point = sorted_points[0]                                             
                                                                                        
            # Calculate 7-day velocity (latest value - value 7 days ago)                
            target_date = latest_point.day - timedelta(days=7)                          
            val_7_days_ago = None                                                       
            for p in sorted_points:                                                     
                if p.day <= target_date:                                                
                    val_7_days_ago = p.value                                            
                    break                                                               
                                                                                        
            if val_7_days_ago is None and len(sorted_points) > 1:                       
                val_7_days_ago = sorted_points[-1].value                                
                                                                                        
            velocity = latest_point.value - val_7_days_ago if val_7_days_ago is not None else 0.0                                                                                  
            z_score = (latest_point.value - mean_val) / stdev_val                       
                                                                                        
            stats.append({                                                              
                "metric": metric_name,                                                  
                "latest_value": latest_point.value,                                     
                "latest_day": latest_point.day,                                         
                "mean": mean_val,                                                       
                "stdev": stdev_val,                                                     
                "z_score": z_score,                                                     
                "velocity": velocity                                                    
            })
        return stats

    
    def get_statistical_insights(self, db: Session, days: int = 60):
        """
        Calculates mean, stdev, and z-score for latest data points for Gemini.
        """
        # start_date = date.today() - timedelta(days=days)

        # # query data for windo
        # query = select(DailyMetric).where(DailyMetric.day >= start_date)
        # result = db.execute(query)
        # metrics = result.scalars().all()

        # if not metrics:
        #     return "No data available for statistical analysis"
        
        # # group by metric type
        # grouped = {}
        # for m in metrics:
        #     if m.metric not in grouped:
        #         grouped[m.metric] = []
        #     grouped[m.metric].append(m)
        
        # insights = []
        # for metric_name, data_points in grouped.items():
        #     values = [p.value for p in data_points]

        #     if len(values) < 2:
        #         continue

        #     mean_val = statistics.mean(values)
        #     stdev_val = statistics.stdev(values) or 0.1

        #     latest_point = max(data_points, key=lambda x: x.day)
        #     z_score = (latest_point.value - mean_val) / stdev_val

        #     insights.append(
        #         f"- {metric_name}: Latest={latest_point.value} on {latest_point.day}. "
        #         f"60-day Mean={mean_val:.1f}, StdDev={stdev_val:.1f}. "
        #         f"Z-score={z_score:+.2f}σ."
        #     )
        stats = self._calculate_metrics_stats(db, days)
        if not stats:
            return "No data available"
        
        insights = []
        for s in stats:
            insights.append(
                f"- {s['metric']}: Latest={s['latest_value']} on {s['latest_day']}. "
                f"60-day Mean={s['mean']:.1f}, StdDev={s['stdev']:.1f}. "
                f"Z-score={s['z_score']:+.2f}σ."
            )
        
        return "\n".join(insights)
    
    def get_recent_metrics_summary(self, db: Session, days: int = 7):
        """
        Fetches metrics from DB and formats for LLM.
        """
        start_date = date.today() - timedelta(days=days)

        # building queries w sqlalchemy
        query = select(DailyMetric).where(DailyMetric.day >= start_date)
        # query = select(DailyMetric)
        result = db.execute(query)
        metrics = result.scalars().all()

        context_parts = []
        for m in metrics:
            context_parts.append(f"{m.day}: {m.metric} is {m.value}")

        return "\n".join(context_parts)
    
    def get_metric_analysis(self, db: Session, days: int = 60):
        """
        Return structured JSON for frontend.
        """
        return self._calculate_metrics_stats(db, days)
    
    def _calculate_correlations(self, db: Session, days: int = 60):                     
        """                                                                             
        Groups metrics by day, calculates Pearson correlation for unique pairs,         
        and provides natural language interpretations.                                  
        """                                                                             
        import itertools                                                                
        start_date = date.today() - timedelta(days=days)                                
        query = select(DailyMetric).where(DailyMetric.day >= start_date)                
        result = db.execute(query)                                                      
        metrics = result.scalars().all()                                                
                                                                                        
        if not metrics:                                                                 
            return []                                                                   
                                                                                        
        # align metrics by day: day -> { metric_name -> value }                      
        by_date = {}                                                                    
        for m in metrics:                                                               
            if m.day not in by_date:                                                    
                by_date[m.day] = {}                                                     
            by_date[m.day][m.metric] = m.value                                          
                                                                                        
        # get unique metric names present in the dataset                             
        metric_names = list(set(m.metric for m in metrics))                             
        if len(metric_names) < 2:                                                       
            return []                                                                   
                                                                                        
        def pearson_r(x, y):                                                            
            n = len(x)                                                                  
            if n < 3:                                     
                return 0.0                                                              
            mean_x = sum(x) / n                                                         
            mean_y = sum(y) / n                                                         
            diff_x = [val - mean_x for val in x]                                        
            diff_y = [val - mean_y for val in y]                                        
            numerator = sum(dx * dy for dx, dy in zip(diff_x, diff_y))                  
            denominator = (sum(dx**2 for dx in diff_x) * sum(dy**2 for dy in            
    diff_y))**0.5                                                                             
            return numerator / denominator if denominator != 0 else 0.0                 
                                                                                        
        correlations = []                                                               
        # calculate correlation for all unique combinations (e.g. Sleep vs Activity) 
        for metric_a, metric_b in itertools.combinations(metric_names, 2):              
            x, y = [], []                                                               
            for day, data in by_date.items():                                           
                if metric_a in data and metric_b in data:                               
                    x.append(data[metric_a])                                            
                    y.append(data[metric_b])                                            
                                                                                        
            if len(x) >= 5:  # need at least 5 days of overlapping data                 
                r = pearson_r(x, y)                                                     
                                                                                        
                if r > 0.5:                                                             
                    desc = "Strong Positive Correlation"                                
                elif r > 0.2:                                                           
                    desc = "Moderate Positive Correlation"                              
                elif r < -0.5:                                                          
                    desc = "Strong Negative Correlation"                                
                elif r < -0.2:                                                          
                    desc = "Moderate Negative Correlation"                              
                else:                                                                   
                    desc = "Weak or No Correlation"                                     
                                                                                        
                # generate custom clinical interpretations based on metrics             
                key = frozenset([metric_a, metric_b])                                   
                interpretation = "These metrics tend to move in opposite directions." if r < 0 else "These metrics show a direct co-movement relationship."                        
                                                                                        
                if key == frozenset(["activity_score", "sleep_score"]):                 
                    interpretation = (                                                  
                        "Higher activity level is linked to better sleep quality, suggesting exercise promotes recovery." if r > 0.2 else                                   
                        "Higher activity level correlates with lower sleep scores, suggesting late-day strain or overtraining is disrupting sleep." if r < -0.2 else         
                        "Daily activity level does not show a direct influence on Sleep Score."                                                                                   
                    )                                                                   
                elif key == frozenset(["activity_score", "readiness_score"]):           
                    interpretation = (                                                  
                        "Higher activity levels correlate with higher readiness scores, suggesting excellent cardiovascular adaptation." if r > 0.2 else                          
                        "Higher activity levels correspond with lower next-day readiness, indicating recovery routines should be enhanced." if r < -0.2 else                        
                        "Daily activity scores show a stable balance relative to recovery capacity."                                                                       
                    )                                                                   
                elif key == frozenset(["sleep_score", "readiness_score"]):              
                    interpretation = (                                                  
                        "Better sleep quality is strongly linked to higher readiness, highlighting sleep as your primary restoration driver." if r > 0.2 else                   
                        "Higher sleep scores correlate with lower readiness; check for physiological stressors like HRV drops or resting heart rate spikes." if r < -0.2 else    
                        "Sleep quality and baseline readiness show independent fluctuations."                                                                            
                    )                                                                   
                                                                                        
                correlations.append({                                                   
                    "metric_a": metric_a,                                               
                    "metric_b": metric_b,                                               
                    "r": round(r, 2),                                                   
                    "description": desc,                                                
                    "interpretation": interpretation                                    
                })                                                                      
                                                                                        
        return correlations                                                             
                                                                                        
    def get_correlation_insights(self, db: Session, days: int = 60) -> str:             
        """                                                                             
        Formatted text representation of correlations for the LLM.                      
        """                                                                             
        corrs = self._calculate_correlations(db, days)                                  
        if not corrs:                                                                   
            return "No significant physiological correlations identified yet."          
                                                                                        
        lines = []                                                                      
        for c in corrs:                                                                 
            lines.append(                                                               
                f"- {c['metric_a']} vs {c['metric_b']}: r={c['r']:.2f} ({c['description']}). "                                                                   
                f"Insight: {c['interpretation']}"                                       
            )                                                                           
        return "\n".join(lines)                                                         
                                                                                        
    def get_correlations_json(self, db: Session, days: int = 60):                       
        """                                                                             
        Returns structured list for frontend routes.                                    
        """                                                                             
        return self._calculate_correlations(db, days)
    