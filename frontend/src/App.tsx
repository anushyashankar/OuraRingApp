import { useEffect, useState } from 'react'
import { apiFetch } from './api/client'
import './App.css'

// definings fields and structure
interface MetricSummary {
  metric: string;
  latest_value: number;
  latest_day: string;
  mean: number;
  stdev: number;
  z_score: number;
  velocity?: number;
}

interface Message {
  sender: 'user' | 'ai';
  text: string;
}

interface Correlation {                                                                 
  metric_a: string;                                                                     
  metric_b: string;                                                                     
  r: number;                                                                            
  description: string;                                                                  
  interpretation: string;                                                               
}  

function App() {                                                                              
  const [metrics, setMetrics] = useState<MetricSummary[]>([]);                          
  const [useSample, setUseSample] = useState(true);                                     
  const [messages, setMessages] = useState<Message[]>([]);                              
  const [question, setQuestion] = useState("");                                         
  const [loadingChat, setLoadingChat] = useState(false);                                
  const [loadingMetrics, setLoadingMetrics] = useState(false);                          
  const [correlations, setCorrelations] = useState<Correlation[]>([]);                  
  const [loadingCorrelations, setLoadingCorrelations] = useState(false);                
                                                                                        
  // fetch metrics and correlations whenever the toggle for sample data changes         
  useEffect(() => {                                                                     
    async function loadData() {                                                         
      setLoadingMetrics(true);                                                          
      setLoadingCorrelations(true);                                                     
      try {                                                                             
        const data = await apiFetch("/metrics/summary", "GET", null, useSample);        
        setMetrics(data);                                                               
                                                                                        
        const corrData = await apiFetch("/metrics/correlations", "GET", null, useSample);
        setCorrelations(corrData);                                                      
      } catch (err) {                                                                   
        console.error("Failed to fetch metrics and correlations", err);                 
      } finally {                                                                       
        setLoadingMetrics(false);                                                       
        setLoadingCorrelations(false);                                                  
      }                                                                                 
    }                                                                                   
    loadData();                                                                         
  }, [useSample]);  

  // listen for user hitting send or enter key
  const handleSendMessage = async (e: React.SyntheticEvent) => {
    e.preventDefault();
    if (!question.trim() || loadingChat) return;

    const userMessage: Message = { sender: 'user', text: question };
    setMessages(prev => [...prev, userMessage]);
    const currentQuestion = question;
    setQuestion("");
    setLoadingChat(true);

    try {
      const response = await apiFetch("/chat", "POST", { question: currentQuestion }, useSample);
      const aiMessage: Message = { sender: 'ai', text: response.answer };
      setMessages(prev => [...prev, aiMessage]);
    } catch (err) {
      console.error("Chat error", err);
      setMessages(prev => [
        ...prev,
        { sender: 'ai', text: "Error: Failed to get response from assistant. Please try again."}
      ]);
    } finally {
      setLoadingChat(false);
    }
  };

  // helper to format metric name
  const formatMetricName = (name: string) => {
    return name
      .replace(/_/g, ' ')
      .replace(/\b\w/g, c => c.toUpperCase());
  };

  // helper to determine class based on score
  const getZScoreClass = (z: number) => {
    if (z > 1.5) return 'metric-z-excellent';
    if (z > 0.5) return 'metric-z-good';
    if (z < -1.5) return 'metric-z-poor';
    if (z < -0.5) return 'metric-z-warning';
    return 'metric-z-neutral';
  };

  // helper to determine trend arrow
  const renderTrend = (velocity?: number) => {
    if (velocity === undefined) return null;
    if (velocity > 0.5) return <span className="trend-arrow trend-up">▲ +{velocity.toFixed(1)}</span>;
    if (velocity < -0.5) return <span className="trend-arrow trend-down">▼ {velocity.toFixed(1)}</span>;
    return <span className="trend-arrow trend-flat">◀▶ {velocity.toFixed(1)}</span>;
  };

  return (                                                                              
    <div className="app-container">                                                     
      <header className="app-header">                                                   
        <div className="header-title-section">                                          
          <h1 className="main-title">Oura Health Intelligence</h1>                      
          <p className="subtitle">Computational insights & predictive interpretation</p>
        </div>                                                                          
        <div className="controls">                                                      
          <label className="toggle-container">                                          
            <input                                                                      
              type="checkbox"                                                           
              checked={useSample}                                                       
              onChange={(e) => setUseSample(e.target.checked)}                          
            />                                                                          
            <span className="toggle-slider"></span>                                     
            <span className="toggle-label">Use Sample DB (Sick Week Demo)</span>        
          </label>                                                                      
        </div>                                                                          
      </header>                                                                         
                                                                                        
      <main className="dashboard-grid">                                                 
        {/* Left Panel: Metrics Dashboard */}                                           
        <section className="metrics-section">                                           
          <h2 className="section-title">Latest Physiological Metrics</h2>               
          {loadingMetrics ? (                                                           
            <div className="loading-spinner">Loading health metrics...</div>            
          ) : metrics.length === 0 ? (                                                  
            <div className="empty-state">No metrics data found. Sync your Oura Cloud    
account.</div>                                                                            
          ) : (                                                                         
            <div className="metrics-grid">                                              
              {metrics.map((m) => {                                                     
                const zClass = getZScoreClass(m.z_score);                               
                return (                                                                
                  <div key={m.metric} className={`metric-card ${zClass}`}>              
                    <div className="metric-header">                                     
                      <span className="metric-title">{formatMetricName(m.metric)}</span>
                      {renderTrend(m.velocity)}                                         
                    </div>                                                              
                    <div className="metric-value-container">                            
                      <span className="metric-value">{m.latest_value}</span>            
                      <span className="metric-unit">pts</span>                          
                    </div>                                                              
                    <div className="metric-stats">                                      
                      <div className="stat-row">                                        
                        <span>60d Average:</span>                                       
                        <span>{m.mean.toFixed(1)}</span>                                
                      </div>                                                            
                      <div className="stat-row">                                        
                        <span>Z-Score:</span>                                           
                        <span className="z-badge">{m.z_score > 0 ? `+${m.z_score.       
toFixed(2)}` : m.z_score.toFixed(2)}σ</span>                                              
                      </div>                                                            
                      <div className="stat-row">                                        
                        <span>Latest Day:</span>                                        
                        <span className="date-text">{m.latest_day}</span>               
                      </div>                                                            
                    </div>                                                              
                  </div>                                                                
                );                                                                      
              })}                                                                       
            </div>                                                                      
          )}                                                                            
        </section>

        <section className="correlations-section" style={{ marginTop: '32px' }}>        
          <h2 className="section-title">Physiological Correlations (60-Day History)</h2>
          {loadingCorrelations ? (                                                      
            <div className="loading-spinner">Analyzing metrics relationships...</div>   
          ) : correlations.length === 0 ? (                                             
            <div className="empty-state">No significant correlations identified.</div>  
          ) : (                                                                         
            <div className="correlations-list" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>                                                                 
              {correlations.map((c, i) => (                                             
                <div key={i} className="correlation-card" style={{                      
                  padding: '16px',                                                      
                  border: '1px solid var(--border)',                                    
                  borderRadius: '10px',                                                 
                  backgroundColor: 'var(--bg)',                                         
                  boxShadow: 'var(--shadow)',                                           
                  display: 'flex',                                                      
                  flexDirection: 'column',                                              
                  gap: '8px'                                                            
                }}>                                                                     
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>                                                                  
                    <span style={{ fontWeight: 600, fontSize: '14px', color: 'var(--text-h)' }}>                                                                              
                      {formatMetricName(c.metric_a)} vs {formatMetricName(c.metric_b)}  
                    </span>                                                             
                    <span className="z-badge" style={{                                  
                      backgroundColor: c.r > 0.2 ? 'rgba(16, 185, 129, 0.15)' : c.r < -0.2 ? 'rgba(239, 68, 68, 0.15)' : 'var(--border)',                                        
                      color: c.r > 0.2 ? '#10b981' : c.r < -0.2 ? '#ef4444' : 'var(--text-h)',                                                                                 
                      border: 'none'                                                    
                    }}>                                                                 
                      r = {c.r > 0 ? `+${c.r.toFixed(2)}` : c.r.toFixed(2)}             
                    </span>                                                             
                  </div>                                                                
                  <div style={{ fontSize: '13px', color: 'var(--text)', lineHeight: 1.4 }}>                                                                                       
                    <strong>{c.description}:</strong> {c.interpretation}                
                  </div>                                                                
                </div>                                                                  
              ))}                                                                       
            </div>                                                                      
          )}                                                                            
        </section>                                                                      
                                                                                        
        {/* Right Panel: AI Chat assistant */}                                          
        <section className="chat-section">                                              
          <h2 className="section-title">Gemini Health Analyst</h2>                      
          <div className="chat-container">                                              
            <div className="chat-messages">                                             
              {messages.length === 0 ? (                                                
                <div className="chat-welcome">                                          
                  <p>I am your health intelligence assistant, powered by Gemini.</p>    
                  <p>I have access to your last 60 days of historical trends and Z-scores.</p>                                                                               
                  <p className="hint">Try asking: <em>"Analyze my scores during my sick week. What patterns stand out?"</em></p>                                                  
                </div>                                                                  
              ) : (                                                                     
                messages.map((msg, index) => (                                          
                  <div key={index} className={`chat-message ${msg.sender}-message`}>    
                    <div className="message-sender">{msg.sender === 'user' ? 'You' : 'Gemini'}</div>                                                                           
                    <div className="message-content">{msg.text}</div>                   
                  </div>                                                                
                ))                                                                      
              )}                                                                        
              {loadingChat && (                                                         
                <div className="chat-message ai-message loading">                       
                  <div className="message-sender">Gemini</div>                          
                  <div className="message-content">                                     
                    <span className="dot"></span>                                       
                    <span className="dot"></span>                                       
                    <span className="dot"></span>                                       
                  </div>                                                                
                </div>                                                                  
              )}                                                                        
            </div>                                                                      
                                                                                        
            <form onSubmit={handleSendMessage} className="chat-input-form">             
              <input                                                                    
                type="text"                                                             
                placeholder="Ask about your metrics, trends, or recovery..."            
                value={question}                                                        
                onChange={(e) => setQuestion(e.target.value)}                           
                disabled={loadingChat}                                                  
              />                                                                        
              <button type="submit" disabled={loadingChat || !question.trim()}>         
                Send                                                                    
              </button>                                                                 
            </form>                                                                     
          </div>                                                                        
        </section>                                                                    
      </main>                                                                           
    </div>                                                                              
  );                                                                                    
}
export default App;          