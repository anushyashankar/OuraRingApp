import { useEffect, useRef, useState } from 'react'
import { apiFetch } from './api/client'
import './App.css'

// definings fields and structure
interface MetricSummary {
  metric: string;
  friendly_name: string;
  latest_value: number;
  latest_day: string;
  mean: number;
  stdev: number;
  z_score: number;
  velocity?: number | null;
  // plain-language layer, computed server side so there is one source of truth
  level_label: string;
  level_tone: 'low' | 'slightly-low' | 'normal' | 'slightly-high' | 'high';
  comparison: string;
  trend_label?: string | null;
  days_of_history: number;
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

interface Briefing {
  briefing: string;
  days_of_history: number;
  generated_by: string;
}

// the questions she is actually likely to have, phrased the way she would ask them
const SUGGESTED_QUESTIONS = [
  "Why am I tired today?",
  "Am I sleeping better than last month?",
  "What's changed this week?",
  "Was I unwell recently?",
];

function App() {
  const [metrics, setMetrics] = useState<MetricSummary[]>([]);
  const [useSample, setUseSample] = useState(true);
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState("");
  const [loadingChat, setLoadingChat] = useState(false);
  const [loadingMetrics, setLoadingMetrics] = useState(false);
  const [correlations, setCorrelations] = useState<Correlation[]>([]);
  const [loadingCorrelations, setLoadingCorrelations] = useState(false);
  const [briefing, setBriefing] = useState<Briefing | null>(null);
  const [loadingBriefing, setLoadingBriefing] = useState(false);
  // the statistics stay available, just not in the way by default
  const [showNumbers, setShowNumbers] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // fetch metrics and correlations whenever the toggle for sample data changes
  useEffect(() => {
    async function loadData() {
      setLoadingMetrics(true);
      setLoadingCorrelations(true);
      setLoadingBriefing(true);
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

      // briefing is a separate request so a slow model call never holds up the cards
      try {
        const brief = await apiFetch("/briefing", "GET", null, useSample);
        setBriefing(brief);
      } catch (err) {
        console.error("Failed to fetch briefing", err);
        setBriefing(null);
      } finally {
        setLoadingBriefing(false);
      }
    }
    loadData();
  }, [useSample]);

  // keep the newest message in view
  useEffect(() => {
    // block:'nearest' keeps this inside the message list -- the default also
    // scrolls the window and drags the whole page down
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [messages, loadingChat]);

  const askQuestion = async (text: string) => {
    if (!text.trim() || loadingChat) return;

    // snapshot the transcript before adding this turn -- the backend wants the
    // prior conversation, not the question we're about to ask
    const history = messages;

    setMessages(prev => [...prev, { sender: 'user', text }]);
    setQuestion("");
    setLoadingChat(true);

    try {
      const response = await apiFetch("/chat", "POST", { question: text, history }, useSample);
      setMessages(prev => [...prev, { sender: 'ai', text: response.answer }]);
    } catch (err) {
      console.error("Chat error", err);
      const status = (err as { status?: number }).status;
      setMessages(prev => [
        ...prev,
        {
          sender: 'ai',
          text: status === 429
            ? "I've answered as many questions as I can today. Please try again tomorrow."
            : "Sorry, something went wrong getting that answer. Please try again."
        }
      ]);
    } finally {
      setLoadingChat(false);
    }
  };

  // listen for user hitting send or enter key
  const handleSendMessage = (e: React.SyntheticEvent) => {
    e.preventDefault();
    askQuestion(question);
  };

  // helper to format metric name
  const formatMetricName = (name: string) => {
    return name
      .replace(/_score/g, '')
      .replace(/_/g, ' ')
      .replace(/\b\w/g, c => c.toUpperCase());
  };

  // plain-language strength, so the reader never has to know what r means
  const describeStrength = (r: number) => {
    const a = Math.abs(r);
    if (a > 0.5) return r > 0 ? "usually move together" : "usually move in opposite directions";
    if (a > 0.2) return r > 0 ? "often move together" : "often move in opposite directions";
    return "don't seem related";
  };

  return (
    <div className="app-container">
      <header className="app-header">
        <div className="header-title-section">
          <h1 className="main-title">Your Health, Explained</h1>
          <p className="subtitle">What your Oura numbers actually mean — compared to your own normal</p>
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

      {/* The one thing she should be able to read and then close the tab */}
      <section className="briefing-panel">
        <h2 className="briefing-heading">Today</h2>
        {loadingBriefing ? (
          <p className="briefing-text briefing-loading">Looking at your last couple of months…</p>
        ) : briefing ? (
          <>
            <p className="briefing-text">{briefing.briefing}</p>
            <p className="briefing-source">
              Based on your last {briefing.days_of_history} days. This describes your
              numbers — it isn't medical advice.
            </p>
          </>
        ) : (
          <p className="briefing-text briefing-loading">
            Couldn't put today's summary together. Your numbers are still below.
          </p>
        )}
      </section>

      <main className="dashboard-grid">
        {/* Left Panel: Metrics Dashboard */}
        <section className="metrics-section">
          <h2 className="section-title">How today compares</h2>
          {loadingMetrics ? (
            <div className="loading-spinner">Loading your numbers…</div>
          ) : metrics.length === 0 ? (
            <div className="empty-state">No recent data found. Sync your Oura account to get started.</div>
          ) : (
            <>
              <div className="metrics-grid">
                {metrics.map((m) => (
                  <div key={m.metric} className={`metric-card metric-tone-${m.level_tone}`}>
                    <div className="metric-header">
                      <span className="metric-title">{m.friendly_name}</span>
                    </div>
                    <div className="metric-value-container">
                      <span className="metric-value">{Math.round(m.latest_value)}</span>
                    </div>
                    <div className="metric-plain">
                      <p className="metric-level">{m.level_label}</p>
                      <p className="metric-comparison">{m.comparison}</p>
                      {m.trend_label && (
                        <p className="metric-comparison">And it's {m.trend_label}</p>
                      )}
                    </div>
                    {showNumbers && (
                      <div className="metric-stats">
                        <div className="stat-row">
                          <span>60d Average:</span>
                          <span>{m.mean.toFixed(1)}</span>
                        </div>
                        <div className="stat-row">
                          <span>Z-Score:</span>
                          <span className="z-badge">
                            {m.z_score > 0 ? `+${m.z_score.toFixed(2)}` : m.z_score.toFixed(2)}σ
                          </span>
                        </div>
                        <div className="stat-row">
                          <span>7d change:</span>
                          <span>
                            {m.velocity === null || m.velocity === undefined
                              ? "n/a"
                              : m.velocity > 0
                                ? `+${m.velocity.toFixed(1)}`
                                : m.velocity.toFixed(1)}
                          </span>
                        </div>
                        <div className="stat-row">
                          <span>Latest Day:</span>
                          <span className="date-text">{m.latest_day}</span>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
              <button
                type="button"
                className="numbers-toggle"
                onClick={() => setShowNumbers(v => !v)}
              >
                {showNumbers ? "Hide the numbers" : "Show the numbers"}
              </button>
            </>
          )}
        </section>

        {/* Behind the numbers toggle on purpose. With only three metrics these pairs
            are near-tautological -- Oura derives readiness partly from sleep -- and
            nothing here is actionable for a non-technical reader. It still feeds the
            chat model as context, it just isn't a claim on her dashboard. */}
        <section
          className="correlations-section"
          style={{ display: showNumbers ? undefined : 'none' }}
        >
          <h2 className="section-title">Patterns over the last two months</h2>
          {loadingCorrelations ? (
            <div className="loading-spinner">Looking for patterns…</div>
          ) : correlations.length === 0 ? (
            <div className="empty-state">No clear patterns yet.</div>
          ) : (
            <div className="correlations-list">
              {correlations.map((c, i) => (
                <div key={i} className="correlation-card">
                  <div className="correlation-header">
                    <span className="correlation-pair">
                      {formatMetricName(c.metric_a)} and {formatMetricName(c.metric_b)}{' '}
                      {describeStrength(c.r)}
                    </span>
                    {showNumbers && (
                      <span
                        className="z-badge"
                        style={{
                          backgroundColor: c.r > 0.2 ? 'rgba(16, 185, 129, 0.15)' : c.r < -0.2 ? 'rgba(239, 68, 68, 0.15)' : 'var(--border)',
                          color: c.r > 0.2 ? '#10b981' : c.r < -0.2 ? '#ef4444' : 'var(--text-h)',
                          border: 'none'
                        }}
                      >
                        r = {c.r > 0 ? `+${c.r.toFixed(2)}` : c.r.toFixed(2)}
                      </span>
                    )}
                  </div>
                  <div className="correlation-body">{c.interpretation}</div>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Right Panel: AI Chat assistant */}
        <section className="chat-section">
          <div className="chat-section-header">
            <h2 className="section-title">Ask about your health</h2>
            {messages.length > 0 && (
              <button
                type="button"
                className="numbers-toggle"
                onClick={() => setMessages([])}
                disabled={loadingChat}
              >
                Start over
              </button>
            )}
          </div>
          <div className="chat-container">
            <div className="chat-messages">
              {messages.length === 0 ? (
                <div className="chat-welcome">
                  <p>Ask me anything about your sleep, energy or activity.</p>
                  <p className="hint">
                    I've looked at your last 60 days, and I'll remember what we've
                    already talked about. Tap a question to start:
                  </p>
                </div>
              ) : (
                messages.map((msg, index) => (
                  <div key={index} className={`chat-message ${msg.sender}-message`}>
                    <div className="message-sender">{msg.sender === 'user' ? 'You' : 'Answer'}</div>
                    <div className="message-content">{msg.text}</div>
                  </div>
                ))
              )}
              {loadingChat && (
                <div className="chat-message ai-message loading">
                  <div className="message-sender">Answer</div>
                  <div className="message-content">
                    <span className="dot"></span>
                    <span className="dot"></span>
                    <span className="dot"></span>
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* tapping beats typing -- she should never face an empty box */}
            <div className="question-chips">
              {SUGGESTED_QUESTIONS.map((q) => (
                <button
                  key={q}
                  type="button"
                  className="question-chip"
                  disabled={loadingChat}
                  onClick={() => askQuestion(q)}
                >
                  {q}
                </button>
              ))}
            </div>

            <form onSubmit={handleSendMessage} className="chat-input-form">
              <input
                type="text"
                placeholder="Or type your own question…"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                disabled={loadingChat}
              />
              <button type="submit" disabled={loadingChat || !question.trim()}>
                Ask
              </button>
            </form>
          </div>
        </section>
      </main>
    </div>
  );
}
export default App;
