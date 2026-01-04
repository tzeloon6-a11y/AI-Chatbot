import { useState, useMemo } from 'react';
import { Upload, Tag, TrendingUp, Clock, FileCheck, BarChart3, AlertCircle } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Badge } from './ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';
import { ScrollArea } from './ui/scroll-area';
import type { ArchiveItem } from '../App';
import { AddArchiveModal } from './AddArchiveModal';
import { ArchiveDetailModal } from './ArchiveDetailModal';
import { ArchiveCard } from './ArchiveCard';
import { toast } from 'sonner';
import { deleteArchive } from '../services/api';

type CuratorDashboardProps = {
  archives: ArchiveItem[];
  setArchives: (archives: ArchiveItem[]) => void;
};

export function CuratorDashboard({ archives, setArchives }: CuratorDashboardProps) {
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [selectedItem, setSelectedItem] = useState<ArchiveItem | null>(null);
  const [isEditMode, setIsEditMode] = useState(false);

  // Calculate statistics from actual data
  const stats = useMemo(() => {
    const now = new Date();
    const startOfMonth = new Date(now.getFullYear(), now.getMonth(), 1);
    
    const thisMonthCount = archives.filter(archive => {
      const createdDate = new Date(archive.date);
      return createdDate >= startOfMonth;
    }).length;

    return {
      totalItems: archives.length,
      thisMonth: thisMonthCount,
    };
  }, [archives]);

  // Get recent uploads sorted by date
  const recentUploads = useMemo(() => {
    return [...archives]
      .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime())
      .slice(0, 10);
  }, [archives]);

  // Calculate popular tags from actual data
  const popularTags = useMemo(() => {
    const tagCounts: Record<string, number> = {};
    
    archives.forEach(archive => {
      if (archive.tags && archive.tags.length > 0) {
        archive.tags.forEach(tag => {
          tagCounts[tag] = (tagCounts[tag] || 0) + 1;
        });
      }
    });

    return Object.entries(tagCounts)
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 10);
  }, [archives]);

  const handleBulkTagging = () => {
    toast.success('Bulk tagging interface coming soon');
  };

  const handleExport = () => {
    toast.success('Export started - you will receive an email when ready');
  };

  const handleDeleteArchive = async (id: string) => {
    try {
      await deleteArchive(id);
      setArchives(archives.filter((a) => a.id !== id));
      toast.success('Archive item deleted successfully');
    } catch (error) {
      console.error('Error deleting archive:', error);
      toast.error('Failed to delete archive item');
    }
  };

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-stone-800">Curator Dashboard</h1>
          <p className="text-stone-500">Manage your digital heritage collection</p>
        </div>
        <Button onClick={() => setIsAddModalOpen(true)} className="bg-forest hover:bg-forest">
          <Upload className="w-4 h-4 mr-2" />
          Upload New Item
        </Button>
      </div>

      {/* Statistics Cards */}
      <div className="flex gap-4 w-full">
        <Card className="flex-1">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm flex items-center justify-between">
              Total Archives
              <BarChart3 className="w-4 h-4 text-stone-500" />
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl text-stone-800">{stats.totalItems.toLocaleString()}</div>
            <p className="text-xs text-stone-500 mt-1">Across all categories</p>
          </CardContent>
        </Card>

        <Card className="flex-1">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm flex items-center justify-between">
              This Month
              <TrendingUp className="w-4 h-4 text-green-500" />
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl text-stone-800">{stats.thisMonth}</div>
            <p className="text-xs text-stone-500 mt-1">New items added this month</p>
          </CardContent>
        </Card>

        <Card className="flex-1">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm flex items-center justify-between">
              Total Tags
              <Tag className="w-4 h-4 text-blue-500" />
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl text-stone-800">{popularTags.length}</div>
            <p className="text-xs text-stone-500 mt-1">Unique tags in collection</p>
          </CardContent>
        </Card>
      </div>

      {/* Main Content */}
      <Tabs defaultValue="recent" className="space-y-4 w-full">
        <TabsList className="w-full flex justify-start gap-3 overflow-x-auto">
          <TabsTrigger value="recent" className="flex-1 min-w-[150px]">Recent Uploads</TabsTrigger>
          <TabsTrigger value="tags" className="flex-1 min-w-[150px]">Tag Management</TabsTrigger>
          {/* <TabsTrigger value="tools" className="flex-1 min-w-[150px]">Curator Tools</TabsTrigger> */}
        </TabsList>


        {/* Recent Uploads */}
        <TabsContent value="recent" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Clock className="w-5 h-5" />
                Recently Added Items
              </CardTitle>
              <CardDescription>Latest additions to the archive</CardDescription>
            </CardHeader>
            <CardContent>
              <ScrollArea className="h-[500px]">
                {recentUploads.length > 0 ? (
                  <div className="space-y-3">
                    {recentUploads.map((item) => (
                      <ArchiveCard
                        key={item.id}
                        item={item}
                        onView={(it) => { setSelectedItem(it); setIsEditMode(false); setDetailOpen(true); }}
                        onEdit={(it) => { setSelectedItem(it); setIsEditMode(true); setDetailOpen(true); }}
                        onDelete={handleDeleteArchive}
                        viewMode="list"
                      />
                    ))}
                  </div>
                ) : (
                  <div className="flex flex-col items-center justify-center h-[400px] text-stone-500">
                    <Clock className="w-12 h-12 mb-4 opacity-50" />
                    <p className="text-lg font-medium">No archives yet</p>
                    <p className="text-sm mt-2">Upload your first item to get started</p>
                  </div>
                )}
              </ScrollArea>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Tag Management */}
        <TabsContent value="tags" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Tag className="w-5 h-5" />
                Tag Management
              </CardTitle>
              <CardDescription>Manage tags and metadata across your collection</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {popularTags.length > 0 ? (
                <div>
                  <h3 className="text-stone-800 mb-3">Most Used Tags</h3>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                    {popularTags.map((tag) => (
                      <div
                        key={tag.name}
                        className="border border-stone-200 rounded-lg p-3 hover:border-forest cursor-pointer transition-colors"
                      >
                        <div className="flex items-center justify-between mb-1">
                          <Badge variant="outline">{tag.name}</Badge>
                        </div>
                        <p className="text-xs text-stone-500">{tag.count.toLocaleString()} {tag.count === 1 ? 'item' : 'items'}</p>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-12 text-stone-500">
                  <Tag className="w-12 h-12 mb-4 opacity-50" />
                  <p className="text-lg font-medium">No tags yet</p>
                  <p className="text-sm mt-2">Tags will appear here as you add them to archives</p>
                </div>
              )}

              <div className="flex gap-2">
                <Button variant="outline" className="flex-1" onClick={handleBulkTagging}>
                  <Tag className="w-4 h-4 mr-2" />
                  Bulk Tagging
                </Button>
                <Button variant="outline" className="flex-1" onClick={handleExport}>
                  <FileCheck className="w-4 h-4 mr-2" />
                  Export Data
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Curator Tools */}
        <TabsContent value="tools" className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Card className="cursor-pointer hover:shadow-lg transition-shadow" onClick={handleBulkTagging}>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Tag className="w-5 h-5 text-forest" />
                  Bulk Operations
                </CardTitle>
                <CardDescription>Edit multiple items at once</CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-stone-600">
                  Apply tags, update metadata, or move items to different collections in bulk.
                </p>
              </CardContent>
            </Card>

            <Card className="cursor-pointer hover:shadow-lg transition-shadow" onClick={handleExport}>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <FileCheck className="w-5 h-5 text-blue-600" />
                  Export Data
                </CardTitle>
                <CardDescription>Export collection data</CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-stone-600">
                  Generate CSV, JSON, or XML exports of your collection metadata.
                </p>
              </CardContent>
            </Card>

            <Card className="cursor-pointer hover:shadow-lg transition-shadow">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <TrendingUp className="w-5 h-5 text-green-600" />
                  Analytics
                </CardTitle>
                <CardDescription>Collection insights</CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-stone-600">
                  View detailed statistics and trends about your collection usage and growth.
                </p>
              </CardContent>
            </Card>

            <Card className="cursor-pointer hover:shadow-lg transition-shadow">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <AlertCircle className="w-5 h-5 text-red-600" />
                  Quality Check
                </CardTitle>
                <CardDescription>Data validation</CardDescription>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-stone-600">
                  Identify incomplete metadata, broken links, or duplicate items.
                </p>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>

      <AddArchiveModal
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        onAdd={(newItem) => setArchives([newItem, ...archives])}
      />
      <ArchiveDetailModal
        isOpen={detailOpen}
        item={selectedItem}
        onClose={() => setDetailOpen(false)}
        initialEditMode={isEditMode}
        onSave={(updated) => {
          setArchives(archives.map((a) => a.id === updated.id ? updated : a));
          setSelectedItem(updated);
        }}
      />
    </div>
  );
}
