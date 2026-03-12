import type { ChatMessage } from '../types/chat';

interface Props { message: ChatMessage }

const URL_REGEX = /(https?:\/\/[^\s,)]+)/g;

function linkify(text: string): React.ReactNode[] {
    const parts = text.split(URL_REGEX);
    return parts.map((part, i) => {
        if (URL_REGEX.test(part)) {
            URL_REGEX.lastIndex = 0;
            return <a key={i} href={part} target="_blank" rel="noopener noreferrer" className="inline-link">{part}</a>;
        }
        URL_REGEX.lastIndex = 0;
        return part;
    });
}


export function MessageBubble({ message }: Props) {
    const isUser = message.role === 'user';

    /* ── User bubble ────────────────────────────────────────────────── */
    if (isUser) {
        return (
            <div className="message-wrapper message-user">
                {/* Show fund scope tags if multiple funds were selected */}
                {message.activeFunds && message.activeFunds.length > 0 && (
                    <div className="fund-scope-tag">
                        🎯 {message.activeFunds.join(' · ')}
                    </div>
                )}
                <div className="user-bubble">
                    <p className="message-content">{message.content}</p>
                </div>
            </div>
        );
    }

    /* ── Assistant bubble ───────────────────────────────────────────── */
    const raw = message.content || '';
    const sourceMatch = raw.match(/\n\nSource:\s*([\s\S]+)$/i);
    const bodyText = sourceMatch
        ? raw.slice(0, raw.length - sourceMatch[0].length).trim()
        : raw.trim();

    let urls: string[] = message.source_urls ?? [];
    if (urls.length === 0 && sourceMatch) {
        urls = sourceMatch[1].split(/,\s*/).map(u => u.trim()).filter(u => u.startsWith('http'));
    }

    const chips: { url: string; label: string }[] = [];
    const seenUrls = new Set<string>();

    urls.forEach(url => {
        if (seenUrls.has(url)) return;
        seenUrls.add(url);

        let label = url;
        try {
            const u = new URL(url);
            const pathParts = u.pathname.split('/').filter(Boolean);
            
            if (u.hostname.includes('indmoney.com')) {
                // For INDmoney, include the fund slug for uniqueness
                const fundSlug = pathParts[pathParts.length - 1];
                label = `indmoney.com/.../${fundSlug}`;
            } else if (u.hostname.includes('amfiindia.com')) {
                const file = pathParts[pathParts.length - 1];
                label = `amfiindia.com/${file}`;
            } else {
                const firstSeg = pathParts[0];
                label = firstSeg ? `${u.hostname}/${firstSeg}` : u.hostname;
            }
        } catch { /* keep raw */ }
        
        chips.push({ url, label });
    });

    return (
        <div className="message-wrapper message-assistant">
            {/* Fund label header for per-fund scoped answers */}
            {message.scopedFund && (
                <div className="fund-answer-header">
                    <span style={{
                        width: 8, height: 8, borderRadius: '50%',
                        background: 'var(--accent)', display: 'inline-block'
                    }} />
                    {message.scopedFund}
                </div>
            )}
            <div className="assistant-row">
                <div className="assistant-avatar">i</div>
                <div className="assistant-content">
                    <p className="message-content">{linkify(bodyText)}</p>
                </div>
            </div>

            {chips.length > 0 && (
                <div className="source-row">
                    <span className="source-label">Sources</span>
                    <div className="source-chips">
                        {chips.map((c, i) => (
                            <a key={i} href={c.url} target="_blank" rel="noopener noreferrer"
                                className="source-chip" title={c.url}>
                                🔗 {c.label}
                            </a>
                        ))}
                    </div>
                </div>
            )}

        </div>
    );
}
