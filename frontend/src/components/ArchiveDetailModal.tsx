import { useState, useEffect } from 'react';
import {
  X,
  Calendar,
  Tag,
  FileText,
  Video,
  Music,
  Edit,
  Save,
  Download,
  ExternalLink,
  ChevronDown,
  ChevronUp,
  Loader2,
} from 'lucide-react';
import type { ArchiveItem } from '../App';
import { Modal, ModalHeader, ModalTitle, ModalBody } from './ui/modal';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Textarea } from './ui/textarea';
import { Badge } from './ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { toast } from 'sonner';
import { updateArchive, getArchiveFileDownloadUrl } from '../services/api';

// Helper function to normalize file URIs from Supabase
const normalizeFileUri = (uri: unknown): string | undefined => {
  if (!uri) {
    return undefined;
  }

  if (typeof uri === 'string') {
    return uri;
  }

  if (typeof uri === 'object') {
    const maybeObject = uri as { publicUrl?: string; data?: { publicUrl?: string } };
    return maybeObject.publicUrl ?? maybeObject.data?.publicUrl;
  }

  return undefined;
};

type ArchiveDetailModalProps = {
  isOpen: boolean;
  item: ArchiveItem | null;
  onClose: () => void;
  initialEditMode?: boolean;
  onSave?: (item: ArchiveItem) => void;
};

export function ArchiveDetailModal({
  isOpen,
  item,
  onClose,
  initialEditMode = false,
  onSave,
}: ArchiveDetailModalProps) {
  const [isEditMode, setIsEditMode] = useState(initialEditMode);
  const [editedItem, setEditedItem] = useState<ArchiveItem | null>(null);
  const [tagInput, setTagInput] = useState('');
  const [isDescriptionExpanded, setIsDescriptionExpanded] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    setIsEditMode(initialEditMode);
  }, [initialEditMode]);

  useEffect(() => {
    if (item) {
      setEditedItem({ ...item });
      // Reset expansion states when opening new item
      setIsDescriptionExpanded(false);
    }
  }, [item]);

  // Keep Modal mounted for exit animations, but render fallback content while waiting for item
  if (!item || !editedItem) {
    return (
      <Modal isOpen={isOpen} onClose={onClose} className="max-w-4xl">
        <ModalHeader onClose={onClose}>
          <ModalTitle>Loading...</ModalTitle>
        </ModalHeader>
      </Modal>
    );
  }

  const getTypeIcon = (type: string) => {
    switch (type) {
      case 'video':
        return Video;
      case 'audio':
        return Music;
      case 'document':
        return FileText;
      default:
        return FileText;
    }
  };

  const getTypeColor = (type: string) => {
    switch (type) {
      case 'image':
        return 'bg-blue-100 text-blue-700 border-blue-200';
      case 'video':
        return 'bg-purple-100 text-purple-700 border-purple-200';
      case 'audio':
        return 'bg-green-100 text-green-700 border-green-200';
      case 'document':
        return 'bg-forest text-white border-forest';
      default:
        return 'bg-stone-100 text-stone-700 border-stone-200';
    }
  };

  const Icon = getTypeIcon(editedItem.type);

  const handleSave = async () => {
    if (!editedItem.title.trim()) {
      toast.error('Title is required');
      return;
    }
    if (!editedItem.description.trim()) {
      toast.error('Description is required');
      return;
    }

    setIsSaving(true);

    try {
      // Call update API - this will regenerate the AI summary in the background
      const response = await updateArchive(editedItem.id, {
        title: editedItem.title,
        description: editedItem.description,
        tags: editedItem.tags,
        dates: [editedItem.date],
      });

      // Map response to ArchiveItem
      const normalizedUris = Array.isArray(response.file_uris)
        ? response.file_uris.filter((uri): uri is string => Boolean(uri))
        : [];

      const fileUrl = normalizedUris[0] ?? editedItem.fileUrl;
      const primaryType = response.media_types && response.media_types.length > 0
        ? response.media_types[0]
        : editedItem.type;

      const updatedItem: ArchiveItem = {
        id: response.id,
        title: response.title,
        type: primaryType,
        date: response.dates && response.dates.length > 0
          ? response.dates[0].split('T')[0]
          : editedItem.date,
        tags: response.tags || [],
        description: response.description || '',
        fileUrl: fileUrl,
        thumbnail: primaryType === 'image' ? fileUrl : editedItem.thumbnail,
        file_uris: normalizedUris,
      };

      setEditedItem(updatedItem);

      if (onSave) {
        onSave(updatedItem);
      }

      setIsEditMode(false);
      toast.success('Archive updated successfully! AI summary regenerated.');
    } catch (error) {
      console.error('Error updating archive:', error);
      toast.error(
        error instanceof Error
          ? error.message
          : 'Failed to update archive. Please try again.'
      );
    } finally {
      setIsSaving(false);
    }
  };

  const handleAddTag = () => {
    if (tagInput.trim() && !editedItem.tags.includes(tagInput.trim())) {
      setEditedItem({
        ...editedItem,
        tags: [...editedItem.tags, tagInput.trim()],
      });
      setTagInput('');
    }
  };

  const handleRemoveTag = (tag: string) => {
    setEditedItem({
      ...editedItem,
      tags: editedItem.tags.filter((t) => t !== tag),
    });
  };

  const handleCancel = () => {
    setEditedItem({ ...item });
    setIsEditMode(false);
  };

  const handleDownload = async () => {
    // If there are multiple files, download all of them
    if (editedItem.file_uris && editedItem.file_uris.length > 1) {
      toast.info(`Downloading ${editedItem.file_uris.length} files...`);

      for (let i = 0; i < editedItem.file_uris.length; i++) {
        await handleDownloadFile(i);
        // Add a small delay between downloads to avoid overwhelming the browser
        if (i < editedItem.file_uris.length - 1) {
          await new Promise(resolve => setTimeout(resolve, 500));
        }
      }

      toast.success('All files downloaded');
      return;
    }

    // Single file download
    await handleDownloadFile(0);
  };

  const handleDownloadFile = async (fileIndex: number) => {
    try {
      // First try to use the backend API endpoint
      try {
        const downloadData = await getArchiveFileDownloadUrl(editedItem.id, fileIndex);
        if (downloadData && downloadData.url) {
          const link = document.createElement('a');
          link.href = downloadData.url;
          link.download = `${editedItem.title}_file_${fileIndex + 1}`;
          link.target = '_blank';
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);

          if (editedItem.file_uris && editedItem.file_uris.length === 1) {
            toast.success('Download started...');
          }
          return;
        }
      } catch (apiError) {
        console.warn('Backend download API failed, falling back to direct URL:', apiError);
      }

      // Fallback: use direct URL from file_uris
      let fileUrl: string | undefined;
      if (editedItem.file_uris && editedItem.file_uris.length > fileIndex) {
        fileUrl = normalizeFileUri(editedItem.file_uris[fileIndex]);
      } else {
        fileUrl = normalizeFileUri(editedItem.fileUrl);
      }

      // Check if the URL is a GenAI URL (which requires API key)
      if (fileUrl && fileUrl.includes('generativelanguage.googleapis.com')) {
        toast.error('Direct download not available. This file requires API authentication.');
        return;
      }

      if (fileUrl) {
        // For Supabase URLs, create a download link
        const link = document.createElement('a');
        link.href = fileUrl;
        link.download = `${editedItem.title}_file_${fileIndex + 1}`;
        link.target = '_blank';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);

        if (editedItem.file_uris && editedItem.file_uris.length === 1) {
          toast.success('Download started...');
        }
      } else {
        toast.error('File URL is not available');
      }
    } catch (error) {
      console.error('Download error:', error);
      toast.error(`Failed to download file ${fileIndex + 1}`);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      className="max-w-4xl h-[90vh] min-h-0 flex flex-col overflow-hidden"
    >
      <ModalHeader onClose={onClose} className="sticky top-0 z-20 bg-white/95 backdrop-blur supports-[backdrop-filter]:bg-white/85">
        <div className="flex items-start justify-between pr-8">
          <div className="flex-1">
            <ModalTitle className="text-2xl text-stone-800">
              {isEditMode ? (
                <Input
                  value={editedItem.title}
                  onChange={(e) => setEditedItem({ ...editedItem, title: e.target.value })}
                  className="text-xl font-semibold"
                  placeholder="Archive title"
                />
              ) : (
                editedItem.title
              )}
            </ModalTitle>
            <div className="flex items-center gap-2 mt-2">
              <Badge className={getTypeColor(editedItem.type)}>
                <Icon className="w-3 h-3 mr-1" />
                {editedItem.type}
              </Badge>
              <span className="text-sm text-stone-500 flex items-center gap-1">
                <Calendar className="w-3 h-3" />
                {new Date(editedItem.date).toLocaleDateString('en-MY', {
                  year: 'numeric',
                  month: 'long',
                  day: 'numeric',
                })}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {isEditMode ? (
              <>
                <Button variant="outline" size="sm" onClick={handleCancel} disabled={isSaving}>
                  Cancel
                </Button>
                <Button size="sm" onClick={handleSave} className="bg-forest hover:bg-forest" disabled={isSaving}>
                  {isSaving ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-1 animate-spin" />
                      Saving...
                    </>
                  ) : (
                    <>
                      <Save className="w-4 h-4 mr-1" />
                      Save
                    </>
                  )}
                </Button>
              </>
            ) : (
              <>
                <Button variant="outline" size="sm" onClick={() => setIsEditMode(true)}>
                  <Edit className="w-4 h-4 mr-1" />
                  Edit
                </Button>
                <Button variant="outline" size="sm" onClick={handleDownload}>
                  <Download className="w-4 h-4 mr-1" />
                  Download
                </Button>
              </>
            )}
          </div>
        </div>
      </ModalHeader>

      <ModalBody className="p-0 flex-1 min-h-0 flex flex-col overflow-auto">
        <div className="p-6 space-y-6 flex-1 min-h-0">
          {/* Description */}
          <div>
            <h3 className="text-sm font-medium text-stone-700 mb-2">Description</h3>
            {isEditMode ? (
              <Textarea
                value={editedItem.description}
                onChange={(e) => setEditedItem({ ...editedItem, description: e.target.value })}
                placeholder="Enter description"
                rows={4}
                className="resize-none"
              />
            ) : (
              <div className="space-y-2">
                <div
                  className={`text-stone-600 whitespace-pre-wrap break-words max-w-full overflow-hidden transition-all ${isDescriptionExpanded ? 'max-h-none' : 'max-h-32'
                    }`}
                >
                  {editedItem.description}
                </div>
                {editedItem.description.length > 200 && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setIsDescriptionExpanded(!isDescriptionExpanded)}
                    className="text-forest hover:text-forest/80 p-0 h-auto font-normal flex items-center gap-1"
                  >
                    {isDescriptionExpanded ? (
                      <>
                        Show Less <ChevronUp className="w-3 h-3" />
                      </>
                    ) : (
                      <>
                        Show More <ChevronDown className="w-3 h-3" />
                      </>
                    )}
                  </Button>
                )}
              </div>
            )}
          </div>

          {/* Type */}
          {isEditMode && (
            <div>
              <h3 className="text-sm font-medium text-stone-700 mb-2">Type</h3>
              <Select
                value={editedItem.type}
                onValueChange={(value: 'image' | 'video' | 'document' | 'audio') =>
                  setEditedItem({ ...editedItem, type: value })
                }
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="image">
                    <div className="flex items-center gap-2">
                      <FileText className="w-4 h-4" />
                      Image
                    </div>
                  </SelectItem>
                  <SelectItem value="video">
                    <div className="flex items-center gap-2">
                      <Video className="w-4 h-4" />
                      Video
                    </div>
                  </SelectItem>
                  <SelectItem value="audio">
                    <div className="flex items-center gap-2">
                      <Music className="w-4 h-4" />
                      Audio
                    </div>
                  </SelectItem>
                  <SelectItem value="document">
                    <div className="flex items-center gap-2">
                      <FileText className="w-4 h-4" />
                      Document
                    </div>
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
          )}

          {/* File URL */}
          <div>
            <h3 className="text-sm font-medium text-stone-700 mb-2">File URL</h3>
            {isEditMode ? (
              <Input
                value={editedItem.fileUrl}
                onChange={(e) => setEditedItem({ ...editedItem, fileUrl: e.target.value })}
                placeholder="https://example.com/file.pdf"
                disabled
              />
            ) : (
              <>
                {(() => {
                  const url = normalizeFileUri(editedItem.fileUrl) || editedItem.fileUrl;
                  const isGenAIUrl = url && url.includes('generativelanguage.googleapis.com');

                  if (isGenAIUrl) {
                    return (
                      <div className="flex items-start gap-2">
                        <p className="text-sm text-stone-600 break-all flex-1 font-mono">
                          {url}
                        </p>
                        <span className="text-xs text-amber-600 bg-amber-50 px-2 py-1 rounded border border-amber-200 shrink-0">
                          API Access Only
                        </span>
                      </div>
                    );
                  }

                  return (
                    <a
                      href={url || '#'}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-forest hover:underline flex items-center gap-1 break-all"
                      onClick={(e) => {
                        if (!url) {
                          e.preventDefault();
                          toast.error('File URL is not available');
                        }
                      }}
                    >
                      {url}
                      <ExternalLink className="w-3 h-3 shrink-0" />
                    </a>
                  );
                })()}
              </>
            )}
          </div>

          {/* Additional File URIs */}
          {editedItem.file_uris && editedItem.file_uris.length > 0 && (
            <div>
              <h3 className="text-sm font-medium text-stone-700 mb-2">
                Additional Files ({editedItem.file_uris.length})
              </h3>
              <div className="space-y-2">
                {editedItem.file_uris.map((uri, index) => {
                  const normalizedUrl = normalizeFileUri(uri);
                  const isGenAIUrl = normalizedUrl && normalizedUrl.includes('generativelanguage.googleapis.com');

                  if (isGenAIUrl) {
                    return (
                      <div key={index} className="flex items-center gap-2 text-sm">
                        <FileText className="w-3 h-3 shrink-0 text-stone-400" />
                        <span className="text-stone-600">File {index + 1}</span>
                        <span className="text-xs text-amber-600 bg-amber-50 px-2 py-1 rounded border border-amber-200">
                          API Access Only
                        </span>
                      </div>
                    );
                  }

                  return (
                    <div key={index} className="flex items-center gap-2 text-sm">
                      <FileText className="w-3 h-3 shrink-0 text-stone-600" />
                      <a
                        href={normalizedUrl || '#'}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-forest hover:underline flex items-center gap-1 break-all flex-1"
                        onClick={(e) => {
                          if (!normalizedUrl) {
                            e.preventDefault();
                            toast.error('File URL is not available');
                          }
                        }}
                      >
                        {normalizedUrl ? `File ${index + 1}` : `File ${index + 1} (unavailable)`}
                        <ExternalLink className="w-3 h-3 shrink-0" />
                      </a>
                      {normalizedUrl && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleDownloadFile(index)}
                          className="h-7 px-2"
                          title="Download this file"
                        >
                          <Download className="w-3 h-3" />
                        </Button>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Tags */}
          <div>
            <h3 className="text-sm font-medium text-stone-700 mb-2 flex items-center gap-1">
              <Tag className="w-4 h-4" />
              Tags
            </h3>
            <div className="flex flex-wrap gap-2 mb-2">
              {editedItem.tags.map((tag) => (
                <Badge key={tag} variant="outline" className="text-sm">
                  {tag}
                  {isEditMode && (
                    <button
                      onClick={() => handleRemoveTag(tag)}
                      className="ml-1 hover:text-red-600"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  )}
                </Badge>
              ))}
              {editedItem.tags.length === 0 && !isEditMode && (
                <span className="text-sm text-stone-400">No tags</span>
              )}
            </div>
            {isEditMode && (
              <div className="flex gap-2">
                <Input
                  value={tagInput}
                  onChange={(e) => setTagInput(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), handleAddTag())}
                  placeholder="Add a tag"
                  className="flex-1"
                />
                <Button onClick={handleAddTag} variant="outline" size="sm">
                  Add
                </Button>
              </div>
            )}
          </div>

          {/* Metadata */}
          <div className="pt-4 border-t border-stone-200">
            <h3 className="text-sm font-medium text-stone-700 mb-2">Metadata</h3>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-stone-500">Item ID:</span>
                <p className="text-stone-800 font-mono text-xs mt-1">{editedItem.id}</p>
              </div>
              <div>
                <span className="text-stone-500">Date Added:</span>
                <p className="text-stone-800 mt-1">
                  {new Date(editedItem.date).toLocaleString('en-MY')}
                </p>
              </div>
            </div>
          </div>
        </div>
      </ModalBody>
    </Modal>
  );
}
