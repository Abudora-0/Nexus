import { useState, useRef, useEffect, useCallback } from "react";
import { useDropzone } from "react-dropzone";
import ReactMarkdown from "react-markdown";
import {
  Upload, Trash2, Loader2, Bot, User, Send, X, FileText, FileType,
  Sparkles, Zap, Copy, Check, BookOpen, Paperclip, Download,
  History, Plus, ChevronDown, ChevronRight, Layers, FileSearch,
} from "lucide-react";
import { uploadFile, chatStream, summarizeDoc, listDocuments, deleteDocument } from "./api";
import type { SourceChunk } from "./api";
import type { ChatSession, StoredMessage } from "./chatStorage";
import { loadSessions, saveSession, deleteSession, newSession, deriveTitle, exportMarkdown } from "./chatStorage";
import "./App.css";

interface Message {
  id: number;
  role: "user" | "assistant";
  content: string;
  sources?: string[];
  sourceChunks?: SourceChunk[];
  streaming?: boolean;
  expandedSources?: boolean;
}

let msgId = 0;

export default function App() {
  const [session, setSession]           = useState<ChatSession>(newSession());
  const [sessions, setSessions]         = useState<ChatSession[]>(loadSessions());
  const [messages, setMessages]         = useState<Message[]>([]);
  const [input, setInput]               = useState("");
  const [documents, setDocuments]       = useState<string[]>([]);
  const [selectedDocs, setSelectedDocs] = useState<Set<string>>(new Set());
  const [uploading, setUploading]       = useState(false);
  const [thinking, setThinking]         = useState(false);
  const [uploadStatus, setUploadStatus] = useState<{type:"ok"|"err"|"loading",text:string}|null>(null);
  const [copiedId, setCopiedId]         = useState<number|null>(null);
  const [summaryDoc, setSummaryDoc]     = useState<string|null>(null);
  const [summaryText, setSummaryText]   = useState("");
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [tab, setTab]                   = useState<"docs"|"history">("docs");

  const bottomRef      = useRef<HTMLDivElement>(null);
  const textareaRef    = useRef<HTMLTextAreaElement>(null);
  const selectedDocsRef = useRef<Set<string>>(selectedDocs);

  useEffect(() => { listDocuments().then(setDocuments).catch(()=>{}); }, []);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    e.target.style.height = "24px";
    e.target.style.height = Math.min(e.target.scrollHeight, 160) + "px";
  };

  // ── Doc selection (multi) ───────────────────────────────────────
  const toggleDoc = (d: string) => {
    setSelectedDocs(prev => {
      const next = new Set(prev);
      next.has(d) ? next.delete(d) : next.add(d);
      selectedDocsRef.current = next;
      return next;
    });
  };
  const clearDocs = () => {
    const empty = new Set<string>();
    selectedDocsRef.current = empty;
    setSelectedDocs(empty);
  };

  // ── Upload ──────────────────────────────────────────────────────
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: { "application/pdf":[".pdf"],"text/plain":[".txt"],"application/octet-stream":[".pdf",".txt"] },
    multiple: false,
    onDrop: async ([file]) => {
      if (!file) return;
      setUploading(true);
      setUploadStatus({ type:"loading", text:`Indexing ${file.name}…` });
      try {
        const result = await uploadFile(file);
        setUploadStatus({ type:"ok", text:`${result.filename} · ${result.chunks} chunks` });
        const docs = await listDocuments();
        setDocuments(docs);
        setSelectedDocs(new Set([result.doc_id]));
      } catch (err:any) {
        setUploadStatus({ type:"err", text: err.message || "Upload failed" });
      } finally { setUploading(false); }
    },
  });

  // ── Summary ─────────────────────────────────────────────────────
  const handleSummarize = async (docId: string) => {
    setSummaryDoc(docId);
    setSummaryText("");
    setSummaryLoading(true);
    try {
      await summarizeDoc(docId,
        (token) => setSummaryText(t => t + token),
        ()      => setSummaryLoading(false),
      );
    } catch { setSummaryLoading(false); }
  };

  // ── Chat ────────────────────────────────────────────────────────
  const sendMessage = useCallback(async () => {
    const q = input.trim();
    if (!q || thinking) return;
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "24px";
    setThinking(true);

    const userMsg: Message = { id: ++msgId, role:"user", content:q };
    const aiMsg:   Message = { id: ++msgId, role:"assistant", content:"", streaming:true };
    const newMsgs = [...messages, userMsg, aiMsg];
    setMessages(newMsgs);

    // Use ref so value is always fresh even in async callbacks
    const live = selectedDocsRef.current;
    const docIdArg  = live.size === 1 ? [...live][0] : null;
    const docIdsArg = live.size  >  1 ? [...live]    : null;

    try {
      await chatStream(q, docIdArg, docIdsArg,
        (token) => setMessages(m => {
          const u=[...m]; u[u.length-1]={...u[u.length-1],content:u[u.length-1].content+token}; return u;
        }),
        (sources, chunks) => setMessages(m => {
          const u=[...m]; u[u.length-1]={...u[u.length-1],sources,sourceChunks:chunks}; return u;
        }),
        () => {
          setMessages(m => {
            const u = [...m];
            u[u.length-1] = { ...u[u.length-1], streaming: false };
            // Save to history using final messages
            const stored: StoredMessage[] = u.map(msg => ({
              role: msg.role, content: msg.content,
              sources: msg.sources, sourceChunks: msg.sourceChunks,
              timestamp: Date.now(),
            }));
            const updated: ChatSession = {
              ...session,
              messages: stored,
              title: deriveTitle(stored),
              updatedAt: Date.now(),
              docIds: [...selectedDocsRef.current],
            };
            setSession(updated);
            saveSession(updated);
            setSessions(loadSessions());
            return u;
          });
          setThinking(false);
        }
      );
    } catch (err:any) {
      setMessages(m => {
        const u=[...m]; u[u.length-1]={...u[u.length-1],content:`⚠️ ${err.message}`,streaming:false}; return u;
      });
      setThinking(false);
    }
  }, [input, thinking, selectedDocs, messages, session]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  };

  // ── New chat ─────────────────────────────────────────────────────
  const startNewChat = () => {
    const s = newSession([...selectedDocs]);
    setSession(s); setMessages([]);
  };

  // ── Load history session ─────────────────────────────────────────
  const loadHistorySession = (s: ChatSession) => {
    setSession(s);
    setMessages(s.messages.map(m => ({
      id: ++msgId, role: m.role, content: m.content,
      sources: m.sources, sourceChunks: m.sourceChunks,
    })));
    if (s.docIds.length) setSelectedDocs(new Set(s.docIds));
    setTab("docs");
  };

  // ── Export ───────────────────────────────────────────────────────
  const exportChat = () => {
    const md = exportMarkdown({ ...session, messages: messages.map(m => ({
      role: m.role, content: m.content,
      sources: m.sources, timestamp: Date.now(),
    }))});
    const blob = new Blob([md], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url;
    a.download = `nexus-chat-${Date.now()}.md`; a.click();
    URL.revokeObjectURL(url);
  };

  // ── Copy ─────────────────────────────────────────────────────────
  const copyMsg = async (msg: Message) => {
    await navigator.clipboard.writeText(msg.content);
    setCopiedId(msg.id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const toggleSources = (id: number) => {
    setMessages(m => m.map(msg => msg.id === id ? {...msg, expandedSources: !msg.expandedSources} : msg));
  };

  const shortName = (id: string) => {
    const parts = id.split("_"); parts.pop();
    return parts.join(" ").replace(/_/g, " ") || id;
  };
  const isPdf = (id: string) => id.toLowerCase().includes("pdf");

  return (
    <div className="app">

      {/* ════ SIDEBAR ════ */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="sidebar-logo"><BookOpen size={15} color="white" /></div>
          <div style={{flex:1}}>
            <div className="sidebar-title">Nexus</div>
            <div className="sidebar-subtitle">Chat with your docs</div>
          </div>
          <button className="icon-btn" onClick={startNewChat} title="New chat"><Plus size={15}/></button>
        </div>

        {/* Tabs */}
        <div className="sidebar-tabs">
          <button className={`sidebar-tab ${tab==="docs"?"active":""}`} onClick={()=>setTab("docs")}>
            <Layers size={13}/> Docs
          </button>
          <button className={`sidebar-tab ${tab==="history"?"active":""}`} onClick={()=>setTab("history")}>
            <History size={13}/> History
          </button>
        </div>

        <div className="sidebar-body">

          {tab === "docs" && <>
            {/* Upload */}
            <div {...getRootProps()} className={`dropzone ${isDragActive?"active":""}`}>
              <input {...getInputProps()} />
              <div className="dropzone-icon">
                {uploading ? <Loader2 size={16} className="spin"/> : <Upload size={16}/>}
              </div>
              <p>{isDragActive ? "Release to upload" : "Upload document"}</p>
              <span>PDF or TXT · max 10 MB</span>
            </div>

            {uploadStatus && (
              <div className={`upload-status ${uploadStatus.type}`}>
                {uploadStatus.type==="ok" && <Check size={12}/>}
                {uploadStatus.type==="err" && <X size={12}/>}
                {uploadStatus.type==="loading" && <Loader2 size={12} className="spin"/>}
                <span>{uploadStatus.text}</span>
              </div>
            )}

            {/* Docs list */}
            <div className="section-label">
              <span>Documents · {documents.length}</span>
              {selectedDocs.size > 0 && <button onClick={clearDocs}>Clear</button>}
            </div>

            <div className="doc-list">
              {documents.length === 0
                ? <p className="doc-empty">No documents yet</p>
                : documents.map(d => (
                  <div key={d} className={`doc-item ${selectedDocs.has(d)?"active":""}`}
                    onClick={() => toggleDoc(d)}>
                    <div className={`doc-icon ${isPdf(d)?"pdf":"txt"}`}>
                      {isPdf(d) ? <FileType size={11}/> : <FileText size={11}/>}
                    </div>
                    <span className="doc-name" title={d}>{shortName(d)}</span>
                    <div className="doc-actions">
                      <button className="doc-action-btn" title="Summarize"
                        onClick={e=>{e.stopPropagation();handleSummarize(d);}}>
                        <FileSearch size={11}/>
                      </button>
                      <button className="doc-action-btn danger" title="Delete"
                        onClick={e=>{e.stopPropagation();deleteDocument(d).then(()=>listDocuments().then(setDocuments));setSelectedDocs(p=>{const n=new Set(p);n.delete(d);return n});}}>
                        <Trash2 size={11}/>
                      </button>
                    </div>
                  </div>
                ))
              }
            </div>

            {selectedDocs.size > 0 && (
              <div className="filter-pill">
                <Zap size={11}/>
                <span>{selectedDocs.size === 1 ? shortName([...selectedDocs][0]) : `${selectedDocs.size} docs selected`}</span>
                <button onClick={clearDocs}><X size={10}/></button>
              </div>
            )}
          </>}

          {tab === "history" && <>
            <div className="section-label"><span>Recent chats · {sessions.length}</span></div>
            <div className="history-list">
              {sessions.length === 0
                ? <p className="doc-empty">No history yet</p>
                : sessions.map(s => (
                  <div key={s.id} className={`history-item ${s.id===session.id?"active":""}`}
                    onClick={() => loadHistorySession(s)}>
                    <div className="history-title">{s.title}</div>
                    <div className="history-meta">
                      {new Date(s.updatedAt).toLocaleDateString()} · {s.messages.length} msgs
                    </div>
                    <button className="doc-action-btn danger" style={{marginLeft:"auto"}}
                      onClick={e=>{e.stopPropagation();deleteSession(s.id);setSessions(loadSessions());}}>
                      <Trash2 size={10}/>
                    </button>
                  </div>
                ))
              }
            </div>
          </>}
        </div>
      </aside>

      {/* ════ MAIN ════ */}
      <main className="chat">

        {/* Header */}
        <div className="chat-header">
          <div className="chat-header-left">
            <Sparkles size={15} color="#6366f1"/>
            <div>
              <div className="chat-header-title">
                {selectedDocs.size === 0 ? "All Documents"
                  : selectedDocs.size === 1 ? shortName([...selectedDocs][0])
                  : `${selectedDocs.size} documents`}
              </div>
              <div className="chat-header-sub">{documents.length} indexed · {messages.length} messages</div>
            </div>
          </div>
          <div style={{display:"flex",alignItems:"center",gap:8}}>
            {messages.length > 0 && (
              <button className="header-btn" onClick={exportChat} title="Export chat as Markdown">
                <Download size={13}/> Export
              </button>
            )}
            <div className="model-badge">
              <div className="model-dot"/>
              phi3:mini
            </div>
          </div>
        </div>

        {/* Messages */}
        <div className="messages">
          {messages.length === 0 ? (
            <div className="welcome">
              <div className="welcome-icon"><BookOpen size={26}/></div>
              <h2>Chat with your documents</h2>
              <p>Upload a file, select it from the sidebar, and ask anything about its content.</p>
              <div className="welcome-steps">
                {[["1","Upload","Drop a PDF or TXT"],["2","Select","Click docs to focus"],["3","Ask","Type your question"]].map(([n,t,d])=>(
                  <div className="step" key={n}>
                    <div className="step-num">{n}</div>
                    <strong style={{fontSize:"0.78rem",color:"var(--text-primary)"}}>{t}</strong>
                    <span style={{textAlign:"center",lineHeight:1.4,fontSize:"0.72rem"}}>{d}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : messages.filter(msg => !(msg.streaming && msg.content === "")).map(msg => (
            <div key={msg.id} className={`message-row ${msg.role}`}>
              <div className={`avatar ${msg.role==="assistant"?"ai":"user"}`}>
                {msg.role==="assistant" ? <Bot size={14} color="white"/> : <User size={13}/>}
              </div>
              <div className="bubble-wrap">
                <div className="bubble">
                  {msg.role==="assistant"
                    ? <><ReactMarkdown>{msg.content}</ReactMarkdown>{msg.streaming && <span className="cursor"/>}</>
                    : <p>{msg.content}</p>
                  }

                  {/* Source chunks (expandable) */}
                  {msg.sourceChunks && msg.sourceChunks.length > 0 && !msg.streaming && (
                    <div className="sources-section">
                      <button className="sources-toggle" onClick={()=>toggleSources(msg.id)}>
                        {msg.expandedSources ? <ChevronDown size={11}/> : <ChevronRight size={11}/>}
                        {[...new Set(msg.sources)].length} source{(msg.sources?.length??0)>1?"s":""}
                      </button>
                      {msg.expandedSources && (
                        <div className="source-chunks">
                          {[...new Set(msg.sourceChunks?.map(c=>c.doc_id))].map(docId => {
                            const chunk = msg.sourceChunks?.find(c=>c.doc_id===docId);
                            return chunk ? (
                              <div key={docId} className="source-chunk">
                                <div className="source-chunk-doc">
                                  <FileText size={10}/>{shortName(docId)}
                                </div>
                                <p className="source-chunk-text">"{chunk.text}…"</p>
                              </div>
                            ) : null;
                          })}
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {msg.role==="assistant" && !msg.streaming && (
                  <div className="bubble-actions">
                    <button className={`action-btn ${copiedId===msg.id?"copied":""}`} onClick={()=>copyMsg(msg)}>
                      {copiedId===msg.id ? <><Check size={11}/> Copied</> : <><Copy size={11}/> Copy</>}
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))}

          {thinking && messages[messages.length-1]?.streaming && messages[messages.length-1]?.content==="" && (
            <div className="thinking-row">
              <div className="avatar ai"><Bot size={14} color="white"/></div>
              <div className="thinking-dots"><span/><span/><span/></div>
            </div>
          )}
          <div ref={bottomRef}/>
        </div>

        {/* Input */}
        <div className="input-area">
          <div className="input-context">
            {selectedDocs.size > 0 && (
              <div className="context-chip">
                <Zap size={10}/>
                <span>{selectedDocs.size===1 ? shortName([...selectedDocs][0]) : `${selectedDocs.size} docs`}</span>
                <button onClick={clearDocs}><X size={10}/></button>
              </div>
            )}
          </div>
          <div className="input-box">
            <textarea ref={textareaRef} value={input} onChange={handleInput}
              onKeyDown={handleKeyDown} disabled={thinking} rows={1}
              placeholder={selectedDocs.size>0 ? `Ask about selected docs…` : "Ask anything about your documents…"}
            />
            <div className="input-toolbar">
              <div className="input-toolbar-left">
                <button className="toolbar-btn" title="Upload file"
                  onClick={()=>document.querySelector<HTMLInputElement>('.dropzone input')?.click()}>
                  <Paperclip size={14}/>
                </button>
                {input.length > 0 && <span className="char-count">{input.length}</span>}
              </div>
              <button className="send-btn" onClick={sendMessage} disabled={!input.trim()||thinking}>
                {thinking ? <><Loader2 size={13} className="spin"/> Thinking…</> : <><Send size={13}/> Send</>}
              </button>
            </div>
          </div>
          <div className="input-hint">Enter to send · Shift+Enter for new line</div>
        </div>
      </main>

      {/* ════ SUMMARY MODAL ════ */}
      {summaryDoc && (
        <div className="modal-overlay" onClick={()=>setSummaryDoc(null)}>
          <div className="modal" onClick={e=>e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-title">
                <FileSearch size={15} color="#6366f1"/>
                Summary — {shortName(summaryDoc)}
              </div>
              <button className="icon-btn" onClick={()=>setSummaryDoc(null)}><X size={14}/></button>
            </div>
            <div className="modal-body">
              {summaryLoading && !summaryText && (
                <div className="modal-loading"><Loader2 size={18} className="spin"/> Generating summary…</div>
              )}
              <ReactMarkdown>{summaryText}</ReactMarkdown>
              {summaryLoading && summaryText && <span className="cursor"/>}
            </div>
            {!summaryLoading && summaryText && (
              <div className="modal-footer">
                <button className="action-btn" onClick={()=>{
                  const blob = new Blob([summaryText],{type:"text/markdown"});
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement("a"); a.href=url;
                  a.download=`summary-${shortName(summaryDoc)}.md`; a.click();
                  URL.revokeObjectURL(url);
                }}>
                  <Download size={11}/> Save summary
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
