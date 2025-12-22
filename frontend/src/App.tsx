import { useState, useEffect } from 'react';
import { Sidebar } from './components/Sidebar';
import { TopBar } from './components/TopBar';
import { ChatPanel } from './components/ChatPanelV2';
import { CuratorDashboard } from './components/CuratorDashboard';
import { SettingsPanel } from './components/SettingsPanel';
import { Toaster } from './components/ui/sonner';
import { getArchives } from './services/api';
import { toast } from 'sonner';

export type ArchiveItem = {
  id: string;
  title: string;
  type: 'image' | 'video' | 'document' | 'audio';
  date: string;
  tags: string[];
  description: string;
  fileUrl: string;
  thumbnail?: string;
  file_uris?: string[]; // Multiple file URIs
};

export type ChatMessage = {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  files?: { name: string; url: string; type: string }[];
  archiveResults?: ArchiveItem[];
};

export type ViewMode = 'chat' | 'dashboard' | 'settings';

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

function App() {
  const [currentView, setCurrentView] = useState<ViewMode>('chat');
  const [archives, setArchives] = useState<ArchiveItem[]>([]);

  // Fetch archives from backend on mount
  useEffect(() => {
    const fetchArchives = async () => {
      try {
        const response = await getArchives();
        
        // Map backend response to frontend ArchiveItem format
        const mappedArchives: ArchiveItem[] = response.map((archive) => {
          const normalizedUris = Array.isArray(archive.file_uris)
            ? archive.file_uris
                .map((uri) => normalizeFileUri(uri))
                .filter((uri): uri is string => Boolean(uri))
            : [];

          // Use first file URI as fileUrl
          const fileUrl = normalizedUris[0] ?? 'https://via.placeholder.com/400';
          
          // Use first media type
          const primaryType = archive.media_types && archive.media_types.length > 0
            ? archive.media_types[0]
            : 'document';

          // Use first date or created_at
          const date = archive.dates && archive.dates.length > 0
            ? archive.dates[0].split('T')[0]
            : archive.created_at.split('T')[0];

          const description = archive.description || 'Description not available.';

          return {
            id: archive.id,
            title: archive.title,
            type: primaryType,
            date: date,
            tags: archive.tags || [],
            description,
            fileUrl: fileUrl,
            thumbnail: primaryType === 'image' ? fileUrl : undefined,
            file_uris: normalizedUris,
          };
        });

        setArchives(mappedArchives);
        console.log('Loaded archives:', mappedArchives);
      } catch (error) {
        console.error('Error fetching archives:', error);
        toast.error('Failed to load archives. Please refresh the page.');
      }
    };

    fetchArchives();
  }, []);

  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: '1',
      role: 'assistant',
      content: `Selamat datang! Welcome to the Badan Warisan Digital Archive. 

I can help you search through our collection of heritage items. Try asking me:
• "Find batik patterns from Kelantan"
• "Show me traditional architecture photos"
• "Search for oral history interviews about crafts"

You can also upload files for AI-assisted tagging and metadata enrichment.`,
      timestamp: new Date(),
    },
  ]);

  return (
    <div className="flex h-screen bg-stone-50">
      <Sidebar currentView={currentView} onViewChange={setCurrentView} />
      
      <div className="flex flex-col flex-1">
        <TopBar />
        
        <main className="flex-1 overflow-hidden">
          {currentView === 'chat' && (
            <div className="h-full p-6">
              <ChatPanel 
                messages={messages} 
                setMessages={setMessages}
                archives={archives}
              />
            </div>
          )}
          
          {currentView === 'dashboard' && (
            <div className="h-full overflow-auto">
              <CuratorDashboard 
                archives={archives}
                setArchives={setArchives}
              />
            </div>
          )}
          
          {currentView === 'settings' && (
            <div className="h-full overflow-auto">
              <SettingsPanel />
            </div>
          )}
        </main>
      </div>
      
      <Toaster />
    </div>
  );
}

export default App;