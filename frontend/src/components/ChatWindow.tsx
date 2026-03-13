import { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import type { ChatMessage } from '../types/chat';
import { MessageBubble } from './MessageBubble';

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/chat';

/* ─── Fund Data ─────────────────────────────────────────────────────────── */
const FUNDS = [
    {
        code: 'PPFCF', name: 'Parag Parikh Flexi Cap Fund', category: 'Flexi Cap · Direct-Growth', color: '#3b82f6',
        questions: ['What is the exit load for PPFCF?', 'What is the current NAV of PPFCF?', 'Who manages Flexi Cap Fund?', 'What is PPFCF expense ratio?']
    },
    {
        code: 'PPTSF', name: 'PPFAS ELSS Tax Saver Fund', category: 'ELSS · 3-year lock-in', color: '#22c55e',
        questions: ['What is the ELSS lock-in period?', 'What is PPTSF current NAV?', 'Does PPTSF save tax under 80C?', 'What is the minimum SIP for PPTSF?']
    },
    {
        code: 'PPCHF', name: 'Conservative Hybrid Fund', category: 'Conservative Hybrid', defaultSelected: false, color: '#f59e0b',
        questions: ['What is the current NAV of PPCHF?', 'What is PPCHF exit load?', 'Who manages Conservative Hybrid?', 'What is PPCHF expense ratio?']
    },
    {
        code: 'PPLF', name: 'Parag Parikh Liquid Fund', category: 'Liquid Fund', color: '#a78bfa',
        questions: ['What is PPLF exit load schedule?', 'What is the current NAV of PPLF?', 'What benchmark does PPLF track?', 'Is PPLF suitable for short-term?']
    },
];

const SUGGESTIONS = [
    { icon: '📊', text: 'What is the exit load for Parag Parikh funds?' },
    { icon: '👤', text: 'Who manages Parag Parikh funds?' },
    { icon: '📄', text: 'How to Download CAS?' },
    { icon: '💰', text: 'What is the expense ratio?' },
    { icon: '🔒', text: 'What is PPTSF lock-in period?' },
    { icon: '📈', text: 'What is the NAV today?' },
];

/* ─── Icons ─────────────────────────────────────────────────────────────── */
function SendIcon() {
    return <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M22 2L11 13" /><path d="M22 2L15 22L11 13L2 9L22 2Z" /></svg>;
}
function PlusIcon() {
    return <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" /></svg>;
}
function ChevronIcon() {
    return <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="6 9 12 15 18 9" /></svg>;
}

/* ─── Multi-Fund Planner Component ──────────────────────────────────────── */
interface PlannerProps {
    funds: typeof FUNDS;
    onAsk: (q: string, fundCode: string) => void;
    onAskAll: (queries: Record<string, string>) => void;
    disabled: boolean;
}

function MultiFundPlanner({ funds, onAsk, onAskAll, disabled }: PlannerProps) {
    const [inputs, setInputs] = useState<Record<string, string>>({});

    const handleSend = (code: string) => {
        const q = (inputs[code] || '').trim();
        if (!q || disabled) return;
        onAsk(q, code);
        setInputs(prev => ({ ...prev, [code]: '' }));
    };

    const filledCount = Object.values(inputs).filter(v => v.trim()).length;

    const plannerRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (!disabled) {
            // Re-added funds.length to ensure it centers when content grows/shrinks
            plannerRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    }, [disabled, funds.length]);

    return (
        <div className="multi-fund-planner" ref={plannerRef}>
            <div className="planner-header">
                <h2 className="planner-title">{funds.length} Funds Selected</h2>
                <div className="planner-sub">
                    pick a starter question or type a custom one below. Each fund is answered independently.
                </div>
            </div>

            {funds.map((fund, idx) => (
                <div className="planner-fund-block" key={fund.code} style={{ animationDelay: `${idx * 0.07}s` }}>
                    <div className="planner-fund-label">
                        <span style={{ width: 12, height: 12, borderRadius: '50%', background: fund.color, display: 'inline-block', flexShrink: 0 }} />
                        <strong>{fund.code}</strong>
                        <span>— {fund.name}</span>
                    </div>

                    <div className="planner-q-chips">
                        {fund.questions.map((q, i) => (
                            <button key={i} className="planner-q-chip" disabled={disabled}
                                onClick={() => setInputs(prev => ({ ...prev, [fund.code]: q }))}
                                title="Click to fill this question in the input box below">
                                {q}
                            </button>
                        ))}
                    </div>

                    <div className="planner-input-row">
                        <input
                            className="planner-input"
                            type="text"
                            placeholder={`Type a custom question for ${fund.code}…`}
                            value={inputs[fund.code] || ''}
                            onChange={e => setInputs(prev => ({ ...prev, [fund.code]: e.target.value }))}
                            onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); handleSend(fund.code); } }}
                            disabled={disabled}
                        />
                        <button
                            className="planner-send-btn"
                            disabled={!(inputs[fund.code]?.trim()) || disabled}
                            onClick={() => handleSend(fund.code)}
                        >
                            Ask →
                        </button>
                    </div>
                </div>
            ))}

            {/* Ask All button — appears when 2+ inputs have text */}
            {filledCount > 1 && (
                <div className="planner-ask-all">
                    <button
                        className="planner-ask-all-btn"
                        disabled={disabled}
                        onClick={() => { onAskAll({ ...inputs }); setInputs({}); }}
                    >
                        ✦ Ask All {filledCount} Funds at Once
                    </button>
                    <span className="planner-ask-all-hint">
                        Each question is sent to its fund independently — answers appear one by one
                    </span>
                </div>
            )}
        </div>
    );
}

/* ─── Main Component ─────────────────────────────────────────────────────── */
export function ChatWindow() {
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [selectedFunds, setSelectedFunds] = useState<Set<string>>(new Set());
    const [drawerOpen, setDrawerOpen] = useState(false);
    const [showPlanner, setShowPlanner] = useState(false);
    const [prevFundCount, setPrevFundCount] = useState(0);

    const messagesEndRef = useRef<HTMLDivElement>(null);
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    useEffect(() => { 
        // Only auto-scroll to bottom if planner is NOT active.
        // If planner is active (which is order: -1 at the top), we don't want to fight its scroll.
        if (!showPlanner) {
            messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }); 
        }
    }, [messages, isLoading, showPlanner]);


    // Auto-pop the planner when user selects more funds
    useEffect(() => {
        if (selectedFunds.size > 1 && selectedFunds.size > prevFundCount) {
            setShowPlanner(true);
        } else if (selectedFunds.size <= 1) {
            setShowPlanner(false);
        }
        setPrevFundCount(selectedFunds.size);
    }, [selectedFunds.size, prevFundCount]);

    useEffect(() => {
        const el = textareaRef.current;
        if (!el) return;
        el.style.height = 'auto';
        el.style.height = Math.min(el.scrollHeight, 190) + 'px';
    }, [input]);

    const toggleFund = (code: string) => {
        setSelectedFunds(prev => {
            const next = new Set(prev);
            if (next.has(code)) {
                next.delete(code);
            } else {
                next.add(code);
            }
            return next;
        });
    };

    const clearFunds = () => setSelectedFunds(new Set());

    /* sequential multi-fund Ask All */
    const handleAskAll = async (fundInputs: Record<string, string>) => {
        const entries = Object.entries(fundInputs).filter(([, q]) => q.trim());
        if (!entries.length || isLoading) return;
        setIsLoading(true);
        setShowPlanner(false); // Close planner on ask all
        for (const [fundCode, query] of entries) {
            const userMsg: ChatMessage = {
                id: `user-${Date.now()}-${fundCode}`, role: 'user', content: query,
                timestamp: new Date(), activeFunds: [fundCode],
            };
            setMessages(prev => [...prev, userMsg]);
            try {
                const resp = await axios.post(API_URL, { query, scheme_filter: fundCode });
                const d = resp.data;
                setMessages(prev => [...prev, {
                    id: `ai-${Date.now()}-${fundCode}`, role: 'assistant',
                    content: d.answer, source_urls: d.sources,
                    timestamp: new Date(), scopedFund: fundCode,
                }]);
            } catch {
                setMessages(prev => [...prev, {
                    id: `err-${Date.now()}-${fundCode}`, role: 'assistant',
                    content: `Couldn't reach the server for ${fundCode}.`, timestamp: new Date(),
                }]);
            }
        }
        setIsLoading(false);
    };

    /* core send — scoped to a specific fund or general */
    const handleSend = async (query: string, scopedFund?: string | null) => {
        if (!query.trim() || isLoading) return;

        const fundFilter = scopedFund !== undefined
            ? scopedFund
            : selectedFunds.size > 0
                ? Array.from(selectedFunds).join(' | ')
                : null;

        const activeFundsList = scopedFund
            ? [scopedFund]
            : selectedFunds.size > 0
                ? [...selectedFunds]
                : undefined;

        const userMsg: ChatMessage = {
            id: Date.now().toString(), role: 'user', content: query,
            timestamp: new Date(), activeFunds: activeFundsList,
        };
        setMessages(prev => [...prev, userMsg]);
        setInput('');
        setIsLoading(true);
        setShowPlanner(false); // Close planner on single ask

        try {
            const resp = await axios.post(API_URL, { query, scheme_filter: fundFilter });
            const d = resp.data;
            setMessages(prev => [...prev, {
                id: (Date.now() + 1).toString(), role: 'assistant',
                content: d.answer, source_urls: d.sources,
                guardrail_triggered: d.guardrail_triggered,
                timestamp: new Date(), scopedFund: scopedFund ?? undefined,
            }]);
        } catch {
            setMessages(prev => [...prev, {
                id: (Date.now() + 1).toString(), role: 'assistant',
                content: 'Sorry, I couldn\'t reach the server. Please make sure the backend is running on port 8000.',
                timestamp: new Date(),
            }]);
        } finally { setIsLoading(false); }
    };

    const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(input); }
    };

    const selectedFundData = FUNDS.filter(f => selectedFunds.has(f.code));
    const isMultiSelect = selectedFunds.size > 1;

    const placeholder = () => {
        if (selectedFunds.size === 0) return 'Ask about any PPFAS fund…';
        if (selectedFunds.size === 1) return `Ask about ${[...selectedFunds][0]}…`;
        return 'Ask a general question, or use the fund planner above…';
    };

    return (
        <div className="app-root dark">

            {/* ═══════ SIDEBAR ═══════ */}
            <aside className="sidebar">
                <div className="sidebar-brand">
                    <div className="brand-icon">i</div>
                    <div className="brand-text">
                        <strong>Ask INDy</strong>
                        <span>PPFAS Fund Assistant</span>
                    </div>
                    {/* No theme toggle — dark mode only */}
                </div>

                <button className="new-chat-btn" onClick={() => { setMessages([]); setInput(''); setSelectedFunds(new Set()); setShowPlanner(false); }}>
                    <PlusIcon /> New chat
                </button>

                {isMultiSelect && (
                    <button className="multi-select-badge"
                        onClick={() => setShowPlanner(true)}
                        title="Click to open the Multi-Fund Planner">
                        {selectedFunds.size} funds · Open Planner →
                    </button>
                )}

                <div className="sidebar-section">
                    <div className="sidebar-section-label">Select Fund(s)</div>

                    {FUNDS.map(fund => {
                        const isSelected = selectedFunds.has(fund.code);
                        return (
                            <div key={fund.code} className="fund-block">
                                <button
                                    className={`fund-card ${isSelected ? 'selected' : ''}`}
                                    onClick={() => toggleFund(fund.code)}
                                >
                                    <div className="fund-card-dot" style={{ background: fund.color }} />
                                    <div className="fund-card-body">
                                        <div className="fund-card-code">{fund.code}</div>
                                        <div className="fund-card-name">{fund.name}</div>
                                        <div className="fund-card-cat">{fund.category}</div>
                                    </div>
                                    <div className="fund-card-check">✓</div>
                                </button>

                                {/* Preset questions — only for single-select */}
                                {isSelected && !isMultiSelect && (
                                    <div className="fund-questions">
                                        {fund.questions.map((q, i) => (
                                            <button key={i} className="fund-q-chip"
                                                onClick={() => handleSend(q, fund.code)} title={q}>
                                                → {q}
                                            </button>
                                        ))}
                                    </div>
                                )}
                            </div>
                        );
                    })}
                </div>

                <div className="sidebar-footer">
                    <div className="disclaimer-strip">Facts only — not investment advice</div>
                </div>
            </aside>

            {/* ═══════ MAIN CHAT ═══════ */}
            <div className="chat-main">
                {/* Mobile topbar */}
                <div className="mobile-topbar">
                    <div className="mobile-brand">
                        <div className="mobile-icon">i</div>
                        <span className="mobile-brand-name">Ask INDy</span>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <button className={`mobile-fund-btn ${selectedFunds.size > 0 ? 'has-selection' : ''}`}
                            onClick={() => setDrawerOpen(o => !o)}>
                            {selectedFunds.size === 0 ? 'All Funds' : selectedFunds.size > 1 ? `${selectedFunds.size} funds` : `📌 ${[...selectedFunds][0]}`}
                            <ChevronIcon />
                        </button>
                    </div>
                </div>

                {/* Mobile fund drawer */}
                <div className={`mobile-fund-drawer ${drawerOpen ? 'open' : ''}`}>
                    {FUNDS.map(fund => (
                        <button key={fund.code}
                            className={`mobile-fund-chip ${selectedFunds.has(fund.code) ? 'selected' : ''}`}
                            onClick={() => toggleFund(fund.code)}>
                            {fund.code}
                        </button>
                    ))}
                </div>

                {/* Context bar */}
                {selectedFunds.size > 0 && (
                    <div className="fund-context-bar">
                        {selectedFundData.map(f => (
                            <span key={f.code} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                                <span style={{ width: 9, height: 9, borderRadius: '50%', background: f.color, display: 'inline-block' }} />
                                <strong>{f.code}</strong>
                            </span>
                        ))}
                        <span style={{ opacity: 0.6, fontSize: 15, marginLeft: 2 }}>
                            {selectedFunds.size === 1
                                ? `— ${FUNDS.find(f => selectedFunds.has(f.code))?.name}`
                                : `— ${selectedFunds.size} funds selected`}
                        </span>
                        <button className="clear-fund-btn" onClick={clearFunds}>✕ Clear</button>
                    </div>
                )}

                {/* Messages */}
                <div className="chat-messages">
                    <div className="messages-inner">

                        {/* ── No messages AND not showing planner: welcome ── */}
                        {messages.length === 0 && !showPlanner && (
                            <div className="welcome-state">
                                <div className="welcome-icon-wrap">
                                    <div className="welcome-icon">i</div>
                                </div>
                                <h1 className="welcome-title">Ask INDy</h1>
                                <p className="welcome-sub">
                                    Your AI assistant for Parag Parikh Mutual Fund facts.
                                    Select one or more funds from the sidebar, or ask anything below.
                                </p>
                                <div className="suggestion-grid">
                                    {SUGGESTIONS.map((s, i) => (
                                        <button key={i} className="suggestion-card" onClick={() => handleSend(s.text)}>
                                            <span className="suggestion-card-icon">{s.icon}</span>
                                            <span className="suggestion-card-text">{s.text}</span>
                                        </button>
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* ── Chat Messages ── */}
                        {messages.map(msg => <MessageBubble key={msg.id} message={msg} />)}

                        {/* ── The Planner: pops at the bottom of the chat list ── */}
                        {showPlanner && (
                            <MultiFundPlanner funds={selectedFundData} onAsk={handleSend} onAskAll={handleAskAll} disabled={isLoading} />
                        )}

                        {isLoading && (
                            <div className="message-wrapper message-assistant">
                                <div className="assistant-row">
                                    <div className="assistant-avatar">i</div>
                                    <div className="typing-indicator"><span /><span /><span /></div>
                                </div>
                            </div>
                        )}
                        <div ref={messagesEndRef} />
                    </div>
                </div>

                {/* Input area */}
                <div className="chat-input-area">
                    <div className="input-wrap">
                        {messages.length > 0 && (
                            <div className="quick-pills">
                                {SUGGESTIONS.slice(0, 4).map((s, i) => (
                                    <button key={i} className="quick-pill" onClick={() => handleSend(s.text)}>{s.text}</button>
                                ))}
                                {isMultiSelect && (
                                    <button className="quick-pill"
                                        style={{ borderColor: 'var(--accent-border)', color: 'var(--accent-2)' }}
                                        onClick={() => setShowPlanner(true)}>
                                        ✦ Back to Planner
                                    </button>
                                )}
                            </div>
                        )}

                        <div className="input-card">
                            {selectedFunds.size > 0 && (
                                <div className="input-fund-context">
                                    <span style={{ color: 'var(--text-3)', fontSize: 14 }}>Scoped to:</span>
                                    {selectedFundData.map(f => (
                                        <span key={f.code} className="input-fund-tag">{f.code}</span>
                                    ))}
                                </div>
                            )}
                            <form className="input-row" onSubmit={e => { e.preventDefault(); handleSend(input); }}>
                                <textarea
                                    ref={textareaRef} rows={1}
                                    placeholder={placeholder()}
                                    value={input}
                                    onChange={e => setInput(e.target.value)}
                                    onKeyDown={handleKeyDown}
                                    disabled={isLoading}
                                />
                                <button type="submit" className="send-btn" disabled={!input.trim() || isLoading}>
                                    <SendIcon />
                                </button>
                            </form>
                        </div>
                        <p className="input-caption">Facts only · Not investment advice · 4 PPFAS schemes</p>
                    </div>
                </div>
            </div>
        </div>
    );
}
