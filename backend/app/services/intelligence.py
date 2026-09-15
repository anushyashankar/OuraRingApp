import google.generativeai as genai
from sqlalchemy.orm import Session
from app.core.config import settings
from sqlalchemy import select
from app.models.metric import DailyMetric
from datetime import date, timedelta
import statistics

# plain-language vocabulary. the z-score is the engine, not the interface --
# nothing below the API layer should ever surface a sigma to the reader.
FRIENDLY_NAMES = {
    "sleep_score": "Sleep",
    "readiness_score": "Readiness",
    "activity_score": "Activity",
}

# what each metric means in words, for the briefing and the chat context
METRIC_MEANINGS = {
    "sleep_score": "how well you slept",
    "readiness_score": "how recovered your body is",
    "activity_score": "how much you moved",
}


# the briefing is a pure function of the day's numbers, so cache it against them.
# the free Gemini tier allows 20 calls/day -- a page reload must not spend one.
_BRIEFING_CACHE: dict = {}


def friendly_metric_name(metric: str) -> str:
    return FRIENDLY_NAMES.get(metric, metric.replace("_", " ").title())


def describe_level(z: float) -> tuple[str, str]:
    """Turn a z-score into (label, tone). Tone drives colour in the UI."""
    if z >= 1.5:
        return "unusually high for you", "high"
    if z >= 0.5:
        return "a little above your usual", "slightly-high"
    if z <= -1.5:
        return "unusually low for you", "low"
    if z <= -0.5:
        return "a little below your usual", "slightly-low"
    return "normal for you", "normal"


def describe_trend(velocity) -> str | None:
    """Turn a 7-day change into words. None when we can't say."""
    if velocity is None:
        return None
    if velocity >= 5:
        return "up from last week"
    if velocity <= -5:
        return "down from last week"
    return "about the same as last week"


class IntelligenceService:
    def __init__(self):
        genai.configure(api_key=settings.GOOGLE_API_KEY)
        self.model = genai.GenerativeModel('gemini-2.5-flash')

    # how many prior turns to carry. enough for a real back-and-forth, bounded so
    # the data context never gets crowded out of the prompt.
    MAX_HISTORY_TURNS = 8

    def _format_history(self, history) -> str:
        if not history:
            return "(This is the first question. There is no earlier conversation.)"

        recent = history[-self.MAX_HISTORY_TURNS:]
        lines = []
        for turn in recent:
            who = "User" if turn.get("sender") == "user" else "You (assistant)"
            text = (turn.get("text") or "").strip()
            if text:
                lines.append(f"{who}: {text}")
        return "\n        ".join(lines) if lines else "(No earlier conversation.)"

    async def answer_question(self, db: Session, question: str, history=None):
        raw_context = self.get_recent_metrics_summary(db, days=60)
        stats_context = self.get_statistical_insights(db, days=60)
        correlation_context = self.get_correlation_insights(db, days=60)
        history_context = self._format_history(history)

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

        CONVERSATION SO FAR (oldest first):
        {history_context}

        USER QUESTION:
        {question}

        INSTRUCTIONS:
         - You are explaining this to someone who is not technical and does not know
           what a statistic is. Write the way you would talk to a family member.
         - Use the DATA and STATISTICAL INSIGHTS to work out the answer, but explain
           the result in plain, everyday English.
         - NEVER use these words in your answer: z-score, standard deviation, sigma,
           correlation, coefficient, baseline, metric, percentile, statistically.
           The statistics are how you reason, not how you speak.
         - A score more than 1.5 standard deviations from the mean is worth calling out;
           describe it as "unusually high/low for you", never with a number like "1.8".
         - Always compare to THEIR OWN usual, not to other people. Say things like
           "that's lower than you normally get" rather than "that's a low score".
         - Whole numbers only. Round scores. Never write a decimal point.
         - Keep it to 4 sentences or fewer. Answer the question that was asked.
         - The question may be a follow-up that only makes sense given the conversation
           so far -- "why?", "what about last week?", "is that bad?", "and my sleep?".
           Resolve what it refers to from the CONVERSATION SO FAR and answer that.
           Never reply that the question is unclear when the earlier turns make it clear.
         - Don't repeat what you already said earlier in the conversation. Add to it.
         - If the data is missing or insufficient, say so plainly.
         - IMPORTANT: Do not give medical advice, diagnose, or recommend treatment.
           You describe what the numbers show. If asked for medical advice, say that
           it's a question for their doctor and describe what you can see instead.
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

            # 7-day velocity: only meaningful against a point actually near a week
            # back. previously this fell back to the oldest point in the whole 60-day
            # window and still called the result a 7-day change.
            target_date = latest_point.day - timedelta(days=7)
            oldest_acceptable = latest_point.day - timedelta(days=9)
            val_7_days_ago = None
            for p in sorted_points:
                if oldest_acceptable <= p.day <= target_date:
                    val_7_days_ago = p.value
                    break

            velocity = latest_point.value - val_7_days_ago if val_7_days_ago is not None else None
            z_score = (latest_point.value - mean_val) / stdev_val
            level_label, level_tone = describe_level(z_score)

            stats.append({
                "metric": metric_name,
                "friendly_name": friendly_metric_name(metric_name),
                "latest_value": latest_point.value,
                "latest_day": latest_point.day,
                "mean": mean_val,
                "stdev": stdev_val,
                "z_score": z_score,
                "velocity": velocity,
                # plain-language layer -- this is what the dashboard renders
                "level_label": level_label,
                "level_tone": level_tone,
                "comparison": f"Your usual is around {round(mean_val)}",
                "trend_label": describe_trend(velocity),
                "days_of_history": len(values),
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

    def _fallback_briefing(self, stats) -> str:
        """
        Deterministic plain-language summary. Used when the model is unavailable,
        so the top of the page is never blank or spinning.
        """
        standouts = [s for s in stats if abs(s["z_score"]) >= 1.5]
        mild = [s for s in stats if 0.5 <= abs(s["z_score"]) < 1.5]

        if standouts:
            parts = [
                f"your {s['friendly_name'].lower()} is {s['level_label']}"
                for s in standouts
            ]
            lead = "Today stands out — " + ", and ".join(parts) + "."
        elif mild:
            parts = [
                f"your {s['friendly_name'].lower()} is {s['level_label']}"
                for s in mild
            ]
            lead = "Today looks close to a normal day, though " + ", and ".join(parts) + "."
        else:
            lead = "Today looks like a normal day for you across sleep, readiness and activity."

        detail = " ".join(
            f"{s['friendly_name']} came in at {round(s['latest_value'])}; "
            f"your usual is around {round(s['mean'])}."
            for s in stats
        )
        return f"{lead} {detail}".strip()

    async def get_daily_briefing(self, db: Session, days: int = 60):
        """
        One plain-language paragraph for the top of the dashboard. The statistics
        are computed here and handed to the model as facts -- the model's only job
        is wording, never deciding what counts as normal.

        Cached against a fingerprint of the underlying numbers: the briefing can't
        change unless the data does, and a page reload shouldn't cost a model call.
        """
        stats = self._calculate_metrics_stats(db, days)
        if not stats:
            return {
                "briefing": "There's no recent data to look at yet. Sync your Oura account to get started.",
                "days_of_history": 0,
                "generated_by": "fallback",
            }

        facts = "\n".join(
            f"- {s['friendly_name']} ({METRIC_MEANINGS.get(s['metric'], '')}): "
            f"today {round(s['latest_value'])}, your usual is around {round(s['mean'])}. "
            f"This is {s['level_label']}. Compared with last week it is "
            f"{s['trend_label'] or 'not comparable (not enough history)'}."
            for s in sorted(stats, key=lambda s: s["metric"])
        )
        days_of_history = max(s["days_of_history"] for s in stats)

        # key on exactly what the model is told. keying on latest value and average
        # missed changes in spread, which can move a label without moving either --
        # and a stale briefing would then contradict the cards beneath it.
        fingerprint = f"{days}|{days_of_history}|{facts}"
        cached = _BRIEFING_CACHE.get(fingerprint)
        if cached:
            return cached

        prompt = f"""
        Write a short daily health summary for someone who is not technical and does
        not know what a statistic is. It will sit at the top of their dashboard.

        THE FACTS (already computed from their own last {days} days -- treat as true):
        {facts}

        RULES:
        - 2 to 3 sentences, maximum 55 words total. Plain, warm, everyday English.
        - Lead with what actually stands out. If nothing stands out, say it was a normal day.
        - NEVER use the words: z-score, standard deviation, sigma, correlation, baseline,
          metric, percentile, statistically. No numbers with decimal points.
        - Always frame comparisons against THEIR OWN usual, e.g. "higher than you normally get".
        - Do not give medical advice, diagnose, or suggest treatment. Describe only.
        - Write directly to them as "you". No greeting, no sign-off, no bullet points.
        """

        try:
            response = self.model.generate_content(prompt)
            text = (response.text or "").strip()
            if not text:
                raise ValueError("empty response")
            generated_by = "model"
        except Exception:
            text = self._fallback_briefing(stats)
            generated_by = "fallback"

        result = {
            "briefing": text,
            "days_of_history": days_of_history,
            "generated_by": generated_by,
        }
        # only cache real model output -- a fallback should be retried next load
        if generated_by == "model":
            _BRIEFING_CACHE[fingerprint] = result
        return result
    
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
                                                                                        
                # plain-language interpretations -- hedged, because these are
                # patterns in her own data, not findings about cause and effect
                key = frozenset([metric_a, metric_b])
                interpretation = (
                    "On days when one of these goes up, the other has tended to go down."
                    if r < 0 else
                    "These two have tended to rise and fall together."
                )

                if key == frozenset(["activity_score", "sleep_score"]):
                    interpretation = (
                        "On days you moved around more, you've tended to sleep better that night." if r > 0.2 else
                        "On days you moved around more, you've tended to sleep a bit worse — it may be worth noticing when in the day you're active." if r < -0.2 else
                        "How much you move doesn't seem to change how well you sleep."
                    )
                elif key == frozenset(["activity_score", "readiness_score"]):
                    interpretation = (
                        "On days you moved around more, you've tended to feel more recovered too." if r > 0.2 else
                        "After days you moved around more, you've tended to feel less recovered — your body may want more rest afterwards." if r < -0.2 else
                        "How much you move doesn't seem to change how recovered you feel."
                    )
                elif key == frozenset(["sleep_score", "readiness_score"]):
                    interpretation = (
                        "Nights you slept well, you've tended to feel more recovered the next day. Oura works out recovery partly from your sleep, so these two are closely tied by design." if r > 0.2 else
                        "Sleeping well hasn't lined up with feeling recovered, which is unusual — worth keeping an eye on." if r < -0.2 else
                        "Your sleep and how recovered you feel have moved fairly independently."
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
    