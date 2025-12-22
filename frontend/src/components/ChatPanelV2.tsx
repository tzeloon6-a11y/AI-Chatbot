import { useState, useRef, useEffect } from 'react';
import { Send, Paperclip, Filter } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { ScrollArea } from './ui/scroll-area';
import type { ChatMessage as ChatMessageType, ArchiveItem } from '../App';
import { ChatMessage } from './ChatMessage';
import { ChatFilters } from './ChatFilters';
import { QuickSearchButtons } from './QuickSearchButtons';
import { TypingIndicator } from './TypingIndicator';
import { toast } from 'sonner';
import { aiSearchArchives, type ArchiveResponse } from '../services/api';

// Helper function to normalize file URIs from Supabase
const normalizeFileUri = (uri: unknown): string | undefined => {
  if (!uri) {
    return undefined;
  }

  if (typeof uri === 'string') {
    // If it's a string, check if it's a full URL or relative path
    // Relative paths should not be used - they'll cause localhost URLs
    if (uri.startsWith('http://') || uri.startsWith('https://')) {
      return uri;
    }
    // If it's a relative path, skip it - we can't use it
    console.warn('Received relative path instead of full URL:', uri);
    return undefined;
  }

  if (typeof uri === 'object') {
    const maybeObject = uri as { publicUrl?: string; data?: { publicUrl?: string } };
    const extractedUrl = maybeObject.publicUrl ?? maybeObject.data?.publicUrl;
    // Recursively validate the extracted URL
    if (extractedUrl) {
      return normalizeFileUri(extractedUrl);
    }
  }

  return undefined;
};

type ChatPanelProps = {
  messages: ChatMessageType[];
  setMessages: React.Dispatch<React.SetStateAction<ChatMessageType[]>>;
  archives?: ArchiveItem[];
};

type FilterState = {
  dateFrom: string;
  dateTo: string;
  mediaType: string;
  keywords: string;
};

export function ChatPanel({ messages, setMessages }: ChatPanelProps) {
  const [input, setInput] = useState('');
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [showFilters, setShowFilters] = useState(false);
  const [isTyping, setIsTyping] = useState(false);
  const [filters, setFilters] = useState<FilterState>({
    dateFrom: '',
    dateTo: '',
    mediaType: 'all',
    keywords: '',
  });
  const fileInputRef = useRef<HTMLInputElement>(null);
  const scrollAreaRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when messages or typing state changes
  const scrollToBottom = () => {
    const scrollViewport = scrollAreaRef.current?.querySelector('[data-radix-scroll-area-viewport]');
    if (scrollViewport) {
      // Use setTimeout to ensure DOM has updated
      setTimeout(() => {
        scrollViewport.scrollTop = scrollViewport.scrollHeight;
      }, 100);
    }
  };

  // Scroll on messages or typing state change
  useEffect(() => {
    scrollToBottom();
  }, [messages, isTyping]);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const files = Array.from(e.target.files);
      setSelectedFiles((prev) => [...prev, ...files]);
      toast.success(`${files.length} file(s) attached`);
    }
  };

  const handleSend = async () => {
    const queryText = input.trim();
    if (!queryText && selectedFiles.length === 0) return;

    // IMMEDIATE: Clear input and files
    setInput('');
    setSelectedFiles([]);

    // Create and add user message immediately
    const userMessage: ChatMessageType = {
      id: Date.now().toString(),
      role: 'user',
      content: queryText || 'Uploaded files for analysis',
      timestamp: new Date(),
      files: selectedFiles.map((file) => ({
        name: file.name,
        url: URL.createObjectURL(file),
        type: file.type,
      })),
    };

    setMessages((prev) => [...prev, userMessage]);
    setIsTyping(true);

    try {
      // Call backend API
      const result = await aiSearchArchives(queryText);
      
      // Check response type
      if (result.response_type === 'message') {
        // Non-search intent (UNCLEAR, UNRELATED, GREETING)
        const aiMessage: ChatMessageType = {
          id: (Date.now() + 1).toString(),
          role: 'assistant',
          content: result.message || 'I can help you search our heritage archive.',
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, aiMessage]);
      } else {
        // Search results (HERITAGE_SEARCH)
        // Convert to ArchiveItem format
        const searchResults: ArchiveItem[] = result.archives.map((archive: ArchiveResponse) => {
          // Normalize file URIs to extract proper URLs from Supabase objects
          const normalizedUris = (archive.file_uris || archive.storage_paths || []).map(normalizeFileUri).filter((uri): uri is string => !!uri);
          const fileUrl = normalizedUris[0] || 'https://via.placeholder.com/400';
          
          return {
            id: archive.id,
            title: archive.title,
            description: archive.description || '',
            type: archive.media_types[0] || 'image',
            date: archive.dates?.[0] || archive.created_at,
            tags: archive.tags || [],
            fileUrl: fileUrl,
            thumbnail: fileUrl,
            file_uris: normalizedUris,
          };
        });

        // Create assistant message with results
        const aiMessage: ChatMessageType = {
          id: (Date.now() + 1).toString(),
          role: 'assistant',
          content: result.message || '',  // Display message if no results
          timestamp: new Date(),
          archiveResults: searchResults.length > 0 ? searchResults : undefined,
        };
        
        setMessages((prev) => [...prev, aiMessage]);
        
        // User feedback
        if (searchResults.length > 0) {
          toast.success(`Found ${searchResults.length} matching archive(s)`);
        } else {
          toast.info(result.message || 'No matching archives found. Try different keywords.');
        }
      }
    } catch (error) {
      const errorMessage: ChatMessageType = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: `Sorry, search failed: ${error instanceof Error ? error.message : 'Unknown error'}. Please try again.`,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
      toast.error('Search failed. Please try again.');
    } finally {
      setIsTyping(false);
    }
  };

  // Handle Enter key
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="bg-white rounded-xl shadow-lg border border-stone-200 flex flex-col h-full">
      {/* Header */}
      <div className="p-4 border-b border-stone-200 flex items-center justify-between">
        <div>
          <h2 className="text-stone-800">AI Heritage Search</h2>
          <p className="text-sm text-stone-500">Ask questions about the collection</p>
        </div>
        <Button
          variant={showFilters ? 'default' : 'outline'}
          size="sm"
          onClick={() => setShowFilters(!showFilters)}
          className={showFilters ? 'bg-forest hover:bg-forest' : ''}
        >
          <Filter className="w-4 h-4 mr-2" />
          Filters
        </Button>
      </div>

      {/* Filters */}
      {showFilters && (
        <ChatFilters filters={filters} setFilters={setFilters} />
      )}

      {/* Messages */}
      <div className="flex-1 overflow-hidden">
        <ScrollArea className="h-full p-4" ref={scrollAreaRef}>
          <div className="space-y-4">
            <AnimatePresence>
              {messages.map((message) => (
                <ChatMessage key={message.id} message={message} />
              ))}
              {isTyping && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                >
                  <TypingIndicator />
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </ScrollArea>
      </div>

      {/* Input Area */}
      <div className="p-4 border-t border-stone-200">
        {selectedFiles.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-2">
            {selectedFiles.map((file, idx) => (
              <div
                key={idx}
                className="bg-stone-100 px-3 py-1 rounded-full text-xs text-stone-700 flex items-center gap-2"
              >
                {file.name}
                <button
                  onClick={() => setSelectedFiles(selectedFiles.filter((_, i) => i !== idx))}
                  className="text-stone-500 hover:text-stone-700"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        )}
        
        <div className="flex gap-2">
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileSelect}
            className="hidden"
            multiple
            accept="image/*,video/*,audio/*,.pdf,.doc,.docx"
          />
          
          <Button
            variant="outline"
            size="icon"
            onClick={() => fileInputRef.current?.click()}
            className="shrink-0"
          >
            <Paperclip className="w-4 h-4" />
          </Button>
          
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Search for heritage items..."
            className="flex-1"
            disabled={isTyping}
          />
          
          <Button
            onClick={handleSend}
            disabled={(!input.trim() && selectedFiles.length === 0) || isTyping}
            className="shrink-0 bg-forest hover:bg-forest"
          >
            <Send className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* Quick Search Buttons - show only when no messages yet */}
      {messages.length === 1 && (
        <QuickSearchButtons onSearch={async (query) => {
          // IMMEDIATE: Clear input and set query
          setInput('');
          
          // Create user message
          const userMessage: ChatMessageType = {
            id: Date.now().toString(),
            role: 'user',
            content: query,
            timestamp: new Date(),
          };

          setMessages((prev) => [...prev, userMessage]);
          setIsTyping(true);

          try {
            const result = await aiSearchArchives(query);
            
            // Check response type
            if (result.response_type === 'message') {
              // Non-search intent
              const aiMessage: ChatMessageType = {
                id: (Date.now() + 1).toString(),
                role: 'assistant',
                content: result.message || 'I can help you search our heritage archive.',
                timestamp: new Date(),
              };
              setMessages((prev) => [...prev, aiMessage]);
            } else {
              // Search results
              const searchResults: ArchiveItem[] = result.archives.map((archive: ArchiveResponse) => {
                // Normalize file URIs to extract proper URLs from Supabase objects
                const normalizedUris = (archive.file_uris || archive.storage_paths || []).map(normalizeFileUri).filter((uri): uri is string => !!uri);
                const fileUrl = normalizedUris[0] || 'https://via.placeholder.com/400';
                
                return {
                  id: archive.id,
                  title: archive.title,
                  description: archive.description || '',
                  type: archive.media_types[0] || 'image',
                  date: archive.dates?.[0] || archive.created_at,
                  tags: archive.tags || [],
                  fileUrl: fileUrl,
                  thumbnail: fileUrl,
                  file_uris: normalizedUris,
                };
              });

              const aiMessage: ChatMessageType = {
                id: (Date.now() + 1).toString(),
                role: 'assistant',
                content: result.message || '',
                timestamp: new Date(),
                archiveResults: searchResults.length > 0 ? searchResults : undefined,
              };
              
              setMessages((prev) => [...prev, aiMessage]);
              
              if (searchResults.length > 0) {
                toast.success(`Found ${searchResults.length} matching archive(s)`);
              } else {
                toast.info(result.message || 'No matching archives found. Try different keywords.');
              }
            }
          } catch (error) {
            const errorMessage: ChatMessageType = {
              id: (Date.now() + 1).toString(),
              role: 'assistant',
              content: `Sorry, search failed: ${error instanceof Error ? error.message : 'Unknown error'}. Please try again.`,
              timestamp: new Date(),
            };
            setMessages((prev) => [...prev, errorMessage]);
            toast.error('Search failed. Please try again.');
          } finally {
            setIsTyping(false);
          }
        }} />
      )}
    </div>
  );
}
