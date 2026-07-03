import { useState, useEffect, useRef } from 'react';
import api from '../api/client';
import toast from 'react-hot-toast';
import {
  Send,
  Plus,
  MessageSquare,
  Bot,
  User,
  Trash2,
  FileText,
  Loader2,
} from 'lucide-react';
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Card } from "@/components/ui/card";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";

export default function ChatPage() {
  const [conversations, setConversations] = useState([]);
  const [activeConvId, setActiveConvId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [selectedDocId, setSelectedDocId] = useState('');
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const messagesEndRef = useRef(null);

  // load conversations and documents on mount
  useEffect(() => {
    api.get('/chat/').then((r) => setConversations(r.data)).catch(() => {});
    api.get('/documents/').then((r) => {
      const ready = r.data.filter((d) => d.status === 'ready');
      setDocuments(ready);
    }).catch(() => {});
  }, []);

  // load messages when active conversation changes
  useEffect(() => {
    if (!activeConvId) {
      setMessages([]);
      return;
    }
    setLoadingMessages(true);
    api.get(`/chat/${activeConvId}/messages`)
      .then((r) => setMessages(r.data))
      .catch(() => toast.error('Failed to load messages'))
      .finally(() => setLoadingMessages(false));
  }, [activeConvId]);

  // scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, sending]);

  async function createConversation() {
    try {
      const res = await api.post('/chat/', {
        document_id: selectedDocId || null,
        title: 'New Chat',
      });
      setConversations((prev) => [res.data, ...prev]);
      setActiveConvId(res.data.id);
    } catch {
      toast.error('Failed to create conversation');
    }
  }

  async function sendMessage(e) {
    e.preventDefault();
    if (!input.trim() || sending) return;

    // auto-create a conversation if none is active
    let convId = activeConvId;
    if (!convId) {
      try {
        const res = await api.post('/chat/', {
          document_id: selectedDocId || null,
          title: input.slice(0, 100),
        });
        convId = res.data.id;
        setConversations((prev) => [res.data, ...prev]);
        setActiveConvId(convId);
      } catch {
        toast.error('Failed to create conversation');
        return;
      }
    }

    const userMessage = input;
    setInput('');
    setSending(true);

    setMessages((prev) => [
      ...prev,
      { id: 'temp', role: 'user', content: userMessage, created_at: new Date().toISOString() },
    ]);

    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/chat/${convId}/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ message: userMessage })
      });

      if (!response.ok) {
        throw new Error('Failed to stream response');
      }

      setSending(false); // Text is arriving, stop the bouncing dots

      // Remove temp user message, replace with final user message and empty stream message
      const streamMsgId = `asst-stream-${Date.now()}`;
      setMessages((prev) => {
        const withoutTemp = prev.filter((m) => m.id !== 'temp');
        return [
          ...withoutTemp,
          { id: `user-${Date.now()}`, role: 'user', content: userMessage, created_at: new Date().toISOString() },
          { id: streamMsgId, role: 'assistant', content: '', created_at: new Date().toISOString() },
        ];
      });

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let fullResponse = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        
        const chunk = decoder.decode(value, { stream: true });
        fullResponse += chunk;
        
        // Update UI incrementally
        setMessages((prev) => {
          const newMsgs = [...prev];
          const lastIdx = newMsgs.length - 1;
          if (newMsgs[lastIdx].id === streamMsgId) {
            newMsgs[lastIdx].content = fullResponse;
          }
          return newMsgs;
        });
      }

      // finalize id
      setMessages((prev) => {
        const newMsgs = [...prev];
        const lastIdx = newMsgs.length - 1;
        if (newMsgs[lastIdx].id === streamMsgId) {
          newMsgs[lastIdx].id = `asst-${Date.now()}`;
        }
        return newMsgs;
      });

      api.get('/chat/').then((r) => setConversations(r.data)).catch(() => {});
    } catch (err) {
      toast.error('Failed to get a response');
      setMessages((prev) => prev.filter((m) => m.id !== 'temp'));
      setSending(false);
    }
  }

  async function deleteConversation(id) {
    try {
      await api.delete(`/chat/${id}`);
      setConversations((prev) => prev.filter((c) => c.id !== id));
      if (activeConvId === id) {
        setActiveConvId(null);
        setMessages([]);
      }
    } catch {
      toast.error('Failed to delete conversation');
    }
  }

  return (
    <div className="flex h-[calc(100vh-4rem)] md:h-screen w-full overflow-hidden bg-background">
      {/* Sidebar / Conversation List */}
      <div className="hidden md:flex flex-col w-72 border-r bg-card shrink-0">
        <div className="flex h-16 shrink-0 items-center justify-between px-4 border-b">
          <h2 className="font-semibold text-lg tracking-tight">Conversations</h2>
          <Button variant="ghost" size="icon" onClick={createConversation} title="New chat">
            <Plus className="h-5 w-5" />
          </Button>
        </div>
        
        <div className="p-4 border-b bg-muted/20">
          <div className="relative">
            <FileText className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
            <select
              className="flex h-9 w-full items-center justify-between rounded-md border border-input bg-background pl-9 pr-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
              value={selectedDocId}
              onChange={(e) => setSelectedDocId(e.target.value)}
            >
              <option value="">Global Knowledge</option>
              {documents.map((d) => (
                <option key={d.id} value={d.id} className="truncate">{d.filename}</option>
              ))}
            </select>
          </div>
        </div>

        <ScrollArea className="flex-1 px-3 py-4">
          {conversations.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-10 text-center px-4">
              <MessageSquare className="h-10 w-10 text-muted-foreground/30 mb-3" />
              <p className="text-sm text-muted-foreground">No conversations yet</p>
            </div>
          ) : (
            <div className="space-y-1.5">
              {conversations.map((conv) => (
                <div
                  key={conv.id}
                  onClick={() => setActiveConvId(conv.id)}
                  className={`
                    group relative flex flex-col gap-1 p-3 rounded-lg cursor-pointer transition-colors border border-transparent
                    ${activeConvId === conv.id 
                      ? 'bg-primary/10 border-primary/20 text-foreground' 
                      : 'hover:bg-muted text-muted-foreground hover:text-foreground'
                    }
                  `}
                >
                  <span className="text-sm font-medium truncate pr-6">{conv.title}</span>
                  <span className="text-[11px] opacity-70">
                    {new Date(conv.created_at).toLocaleDateString()}
                  </span>
                  
                  <Button
                    variant="ghost"
                    size="icon"
                    className={`
                      absolute top-2 right-2 h-6 w-6 rounded-md opacity-0 group-hover:opacity-100 transition-opacity
                      ${activeConvId === conv.id ? 'opacity-100 text-destructive hover:bg-destructive/20' : 'text-muted-foreground hover:text-destructive hover:bg-destructive/10'}
                    `}
                    onClick={(e) => { e.stopPropagation(); deleteConversation(conv.id); }}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </ScrollArea>
      </div>

      {/* Main Chat Area */}
      <div className="flex flex-col flex-1 h-full min-w-0 bg-background relative">
        <ScrollArea className="flex-1 px-4 py-6 md:px-8">
          <div className="max-w-3xl mx-auto space-y-6 pb-20">
            {loadingMessages ? (
              <div className="flex items-center justify-center py-20">
                <Loader2 className="h-8 w-8 text-primary animate-spin" />
              </div>
            ) : messages.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-20 text-center animate-in fade-in zoom-in duration-500">
                <div className="h-20 w-20 bg-primary/10 rounded-full flex items-center justify-center mb-6 ring-8 ring-primary/5">
                  <Bot className="h-10 w-10 text-primary" />
                </div>
                <h2 className="text-2xl md:text-3xl font-bold tracking-tight mb-3">Ask me anything</h2>
                <p className="text-muted-foreground max-w-md text-base md:text-lg">
                  Upload a document and start chatting about it. I'll find the relevant parts and help you understand them.
                </p>
                {/* Mobile Document Selector */}
                <div className="mt-8 w-full max-w-xs md:hidden">
                  <div className="relative">
                    <FileText className="absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                    <select
                      className="flex h-10 w-full items-center justify-between rounded-md border border-input bg-background pl-9 pr-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
                      value={selectedDocId}
                      onChange={(e) => setSelectedDocId(e.target.value)}
                    >
                      <option value="">Global Knowledge</option>
                      {documents.map((d) => (
                         <option key={d.id} value={d.id}>{d.filename}</option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>
            ) : (
              messages.map((msg) => (
                <div 
                  key={msg.id} 
                  className={`flex gap-4 w-full animate-in fade-in slide-in-from-bottom-2 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  {msg.role === 'assistant' && (
                    <Avatar className="h-8 w-8 shrink-0 mt-0.5 border border-primary/20">
                      <AvatarFallback className="bg-primary/10 text-primary">
                        <Bot className="h-4 w-4" />
                      </AvatarFallback>
                    </Avatar>
                  )}
                  
                  <div className={`
                    flex flex-col gap-1 max-w-[85%] md:max-w-[75%]
                    ${msg.role === 'user' ? 'items-end' : 'items-start'}
                  `}>
                    <div className="flex items-center gap-2 px-1">
                      <span className="text-xs font-medium text-muted-foreground">
                        {msg.role === 'user' ? 'You' : 'StudyMate'}
                      </span>
                    </div>
                    <div className={`
                      rounded-2xl px-5 py-3.5 text-[15px] leading-relaxed shadow-sm whitespace-pre-wrap
                      ${msg.role === 'user' 
                        ? 'bg-primary text-primary-foreground rounded-tr-sm' 
                        : 'bg-card border text-card-foreground rounded-tl-sm'
                      }
                    `}>
                      {msg.content}
                    </div>
                  </div>

                  {msg.role === 'user' && (
                    <Avatar className="h-8 w-8 shrink-0 mt-0.5">
                      <AvatarFallback className="bg-muted text-muted-foreground">
                        <User className="h-4 w-4" />
                      </AvatarFallback>
                    </Avatar>
                  )}
                </div>
              ))
            )}

            {sending && (
              <div className="flex gap-4 w-full animate-in fade-in slide-in-from-bottom-2 justify-start">
                <Avatar className="h-8 w-8 shrink-0 mt-0.5 border border-primary/20">
                  <AvatarFallback className="bg-primary/10 text-primary">
                    <Bot className="h-4 w-4" />
                  </AvatarFallback>
                </Avatar>
                <div className="flex flex-col items-start gap-1 max-w-[75%]">
                  <span className="text-xs font-medium text-muted-foreground px-1">StudyMate</span>
                  <div className="rounded-2xl rounded-tl-sm bg-card border px-5 py-4 shadow-sm flex items-center gap-1.5">
                    <div className="w-2 h-2 bg-primary/40 rounded-full animate-bounce [animation-delay:-0.3s]"></div>
                    <div className="w-2 h-2 bg-primary/60 rounded-full animate-bounce [animation-delay:-0.15s]"></div>
                    <div className="w-2 h-2 bg-primary/80 rounded-full animate-bounce"></div>
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        </ScrollArea>

        {/* Input Bar */}
        <div className="absolute bottom-0 left-0 right-0 p-4 bg-background/80 backdrop-blur-xl border-t">
          <div className="max-w-3xl mx-auto relative">
            <form onSubmit={sendMessage} className="relative flex items-center shadow-sm">
              <Input
                type="text"
                placeholder="Ask about your notes..."
                className="pr-12 py-6 text-base rounded-full bg-card border-muted shadow-inner focus-visible:ring-primary/50"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                disabled={sending}
                autoFocus
              />
              <Button
                type="submit"
                size="icon"
                disabled={!input.trim() || sending}
                className="absolute right-1.5 h-9 w-9 rounded-full transition-transform active:scale-95"
              >
                <Send className="h-4 w-4" />
                <span className="sr-only">Send</span>
              </Button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
